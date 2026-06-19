import requests

from src import config

_SPOTLIGHT_URL = config.SPOTLIGHT_URL


def link_entities(question: str) -> list[dict]:
    """
    Call DBpedia Spotlight to link entities in the question.

    Returns list of dicts with uri (dbr: prefix), surface_form, and start/end char offsets.
    end is derived as start + len(surface_form) since Spotlight only returns @offset.

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
