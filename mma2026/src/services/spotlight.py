import requests
import config


_SPOTLIGHT_URL = config.SPOTLIGHT_URL


def link_entities(question: str) -> list[str]:
    try:
        resp = requests.post(
            _SPOTLIGHT_URL,
            data={"text": question, "confidence": 0.5},
            headers={"Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        resources = resp.json().get("Resources", [])
        return [r["@URI"].replace("http://dbpedia.org/resource/", "dbr:") for r in resources]
    except Exception:
        return []
