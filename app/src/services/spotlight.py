import requests

from src import config

_SPOTLIGHT_URL = config.SPOTLIGHT_URL


def _spotlight_entities(question: str) -> list[dict]:
    resp = requests.post(
        _SPOTLIGHT_URL,
        data={"text": question, "confidence": 0.5},
        headers={"Accept": "application/json"},
        timeout=10,
    )
    resp.raise_for_status()
    resources = resp.json().get("Resources", [])
    return [
        {
            "uri": r["@URI"].replace("http://dbpedia.org/resource/", "dbr:"),
            "surface_form": r["@surfaceForm"],
            "start": int(r["@offset"]),
            "end": int(r["@offset"]) + len(r["@surfaceForm"]),
        }
        for r in resources
    ]


def _llm_entities(question: str) -> list[dict]:
    """
    Ask the LLM to extract DBpedia entities from the question.
    """
    from src.services.llm import _chat

    prompt = (
        "Extract the named entities from the question and return their DBpedia URIs "
        "in the format dbr:Entity_Name (use underscores, capitalize as in DBpedia). "
        "Return one URI per line, nothing else.\n\n"
        "Example:\n"
        "Question: Where was Marie Curie born?\n"
        "dbr:Marie_Curie\n\n"
        "Question: What is the river whose mouth is in deadsea?\n"
        "dbr:Dead_Sea\n\n"
        "Question: Who did Albert Einstein collaborate with at Princeton?\n"
        "dbr:Albert_Einstein\n"
        "dbr:Princeton_University\n\n"
        f"Question: {question}"
    )
    raw = _chat([{"role": "user", "content": prompt}], model=config.CLAIMS_MODEL)
    results = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("dbr:"):
            results.append(
                {
                    "uri": line,
                    "surface_form": line[4:].replace("_", " "),
                    "start": 0,
                    "end": 0,
                }
            )
    return results


def link_entities(question: str) -> list[dict]:
    """
    Link entities in the question using DBpedia Spotlight + LLM fallback.

    Returns the union of both, deduplicated by URI. Spotlight results are preferred
    (they carry real char offsets); LLM-only results have start=end=0.

    Example Spotlight resource entry:
    {
        "@URI": "http://dbpedia.org/resource/Marie_Curie",
        "@support": "1492",
        "@types": "Schema:Person,DBpedia:Scientist,...",
        "@surfaceForm": "Marie Curie",
        "@offset": "7",
        "@similarityScore": "0.9999999457690777",
        "@percentageOfSecondRank": "4.597547250611574E-8"
    }
    """
    spotlight = _spotlight_entities(question)
    llm = _llm_entities(question)

    seen = {e["uri"] for e in spotlight}
    merged = spotlight + [e for e in llm if e["uri"] not in seen]
    print(
        f"[link_entities] spotlight={len(spotlight)} llm={len(llm)} merged={len(merged)}"
    )
    return merged
