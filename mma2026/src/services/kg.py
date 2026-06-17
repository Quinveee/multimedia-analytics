import json
from pathlib import Path

import config


def load_kg(path: Path = None) -> dict:
    return json.loads(Path(path or config.KG_PATH).read_text())


def get_subgraph(entity_uris: list[str], kg: dict) -> dict:
    matched = {n["id"] for n in kg["nodes"] if n["id"] in entity_uris}

    if not matched:
        return {"nodes": [], "edges": []}

    edges = [
        e for e in kg["edges"] if e["subject"] in matched or e["object"] in matched
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
