from src import config
import requests

_SPOTLIGHT_URL = config.SPOTLIGHT_URL


def link_entities(question: str) -> list[dict]:
    """Call DBpedia Spotlight to extract entities from a question.

    Returns a list of dicts, e.g.:
    [{"uri": "dbr:Marie_Curie", "surface_form": "Marie Curie", "start": 7, "end": 18}]

    start/end are character offsets into the original question string, ready for frontend
    highlighting. Spotlight only gives @offset (start); end is derived as start + len(surface_form).

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
