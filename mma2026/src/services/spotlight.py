import config
import requests

_SPOTLIGHT_URL = config.SPOTLIGHT_URL


def link_entities(question: str) -> list[dict]:
    """Call DBpedia Spotlight to extract entities from a question.

    Returns a list of dicts, e.g.:
    [{"uri": "dbr:Marie_Curie", "surface_form": "Marie Curie", "offset": 7}]

    surface_form can be used by the frontend to highlight the matched span in the question.
    offset is the character position in the original question string (for precision if needed).

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
            "offset": int(r["@offset"]),
        }
        for r in resources
    ]
