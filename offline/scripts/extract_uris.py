# Stage 1 of the pipeline.
# Goes through every gold SPARQL query and pulls out the DBpedia entities and
# predicates it uses. The entities become the seeds we build the graph around.
# Writes data/uris.json.

import json
import re
from pathlib import Path

from uri_norm import canonical_uri

HERE = Path(__file__).resolve().parent
QA_DIR = HERE.parent / "qa_dataset"
OUT_DIR = HERE.parent / "data"

URI_RE = re.compile(r"<(http://dbpedia\.org/[^>]+)>")


def classify(uri: str) -> str | None:
    if "/resource/" in uri:
        return "entity"
    local = uri.rsplit("/", 1)[-1]
    if "/property/" in uri:
        return "predicate"
    if "/ontology/" in uri and not local[:1].isupper():
        return "predicate"
    return None


def run() -> None:
    entities: set[str] = set()
    predicates: set[str] = set()
    per_question: dict[str, dict[str, list[str]]] = {}

    for fname in ("train-data.json", "test-data.json"):
        for q in json.loads((QA_DIR / fname).read_text(encoding="utf-8")):
            q_ents, q_preds = set(), set()
            for uri in URI_RE.findall(q.get("sparql_query", "")):
                uri = canonical_uri(uri)
                kind = classify(uri)
                if kind == "entity":
                    entities.add(uri)
                    q_ents.add(uri)
                elif kind == "predicate":
                    predicates.add(uri)
                    q_preds.add(uri)
            per_question[q["_id"]] = {
                "entities": sorted(q_ents),
                "predicates": sorted(q_preds),
            }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "entities": sorted(entities),
        "predicates": sorted(predicates),
        "per_question": per_question,
    }
    (OUT_DIR / "uris.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"entities   : {len(entities)}")
    print(f"predicates : {len(predicates)}")
    print(f"questions  : {len(per_question)}")
    print(f"written    : {OUT_DIR / 'uris.json'}")


if __name__ == "__main__":
    run()
