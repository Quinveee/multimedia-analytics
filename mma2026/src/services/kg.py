import json
from pathlib import Path

_DEFAULT_KG = Path(__file__).resolve().parents[3] / "offline" / "mock_kg.json"


def load_kg(path: Path = _DEFAULT_KG) -> dict:
    return json.loads(path.read_text())


def get_subgraph(question: str, kg: dict) -> dict:
    q_lower = question.lower()
    matched = {
        n["id"] for n in kg["nodes"]
        if n["label"].lower() in q_lower
    }

    if not matched:
        return {"nodes": [], "edges": []}

    edges = [
        e for e in kg["edges"]
        if e["subject"] in matched or e["object"] in matched
    ]

    node_ids = {e["subject"] for e in edges} | {e["object"] for e in edges} | matched
    nodes = [n for n in kg["nodes"] if n["id"] in node_ids]

    return {"nodes": nodes, "edges": edges}


def triples_as_text(subgraph: dict) -> str:
    lines = []
    node_label = {n["id"]: n["label"] for n in subgraph["nodes"]}
    for e in subgraph["edges"]:
        s = node_label.get(e["subject"], e["subject"])
        p = e["predicate_label"]
        o = node_label.get(e["object"], e["object"])
        lines.append(f"{s} {p} {o}")
    return "\n".join(lines)
