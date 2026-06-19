# Stage 6 of the pipeline. Runs after enrich and before images.
# The infobox dump adds a lot of junk relations, so here we keep only the
# ontology relations (dbo:) and the property relations (dbp:) that questions
# actually ask about, and throw the rest away. We also drop edges that point to
# a missing node and nodes that end up with no edges. It will not run if that
# would delete a node that already has an image. Edits data/kg_subset.json in place.

import json
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data"
KG_PATH = DATA_DIR / "kg_subset.json"
URIS_PATH = DATA_DIR / "uris.json"


def _shorten(uri: str) -> str:
    return (uri
            .replace("http://dbpedia.org/ontology/", "dbo:")
            .replace("http://dbpedia.org/property/", "dbp:")
            .replace("http://dbpedia.org/resource/", "dbr:"))


def question_predicates(uris_path: Path) -> set[str]:
    preds = json.loads(uris_path.read_text(encoding="utf-8"))["predicates"]
    return {_shorten(p) for p in preds}


def clean(kg: dict, qpreds: set[str]) -> tuple[dict, dict]:
    """Return (cleaned_kg, stats). Keeps dbo: + question dbp: edges with both
    endpoints present; keeps only nodes that still have an edge."""
    nodes, edges = kg["nodes"], kg["edges"]
    node_ids = {n["id"] for n in nodes}

    def keep(e):
        p = e["predicate"]
        return ((p.startswith("dbo:") or p in qpreds)
                and e["subject"] in node_ids and e["object"] in node_ids)

    kept_edges = [e for e in edges if keep(e)]
    live = set()
    for e in kept_edges:
        live.add(e["subject"])
        live.add(e["object"])
    kept_nodes = [n for n in nodes if n["id"] in live]

    stats = {
        "nodes_before": len(nodes), "nodes_after": len(kept_nodes),
        "edges_before": len(edges), "edges_after": len(kept_edges),
        "images_before": sum(1 for n in nodes if n.get("image")),
        "images_after": sum(1 for n in kept_nodes if n.get("image")),
    }
    return {"nodes": kept_nodes, "edges": kept_edges}, stats


def run(kg_path: Optional[Path] = None, uris_path: Optional[Path] = None) -> None:
    kg_path = kg_path or KG_PATH
    uris_path = uris_path or URIS_PATH
    print("loading kg_subset...")
    kg = json.loads(kg_path.read_text(encoding="utf-8"))
    cleaned, s = clean(kg, question_predicates(uris_path))

    if s["images_after"] != s["images_before"]:
        raise RuntimeError(
            f"ABORT: would drop {s['images_before'] - s['images_after']} nodes "
            "with an image — refusing to write")

    tmp = kg_path.with_name(kg_path.name + ".tmp")
    tmp.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
    tmp.replace(kg_path)

    d_nodes = s["nodes_before"] - s["nodes_after"]
    d_edges = s["edges_before"] - s["edges_after"]
    print(f"  nodes {s['nodes_before']:,} -> {s['nodes_after']:,}  (-{d_nodes:,})")
    print(f"  edges {s['edges_before']:,} -> {s['edges_after']:,}  "
          f"(-{d_edges:,}, {100 * d_edges / s['edges_before']:.1f}%)")
    print(f"  images preserved: {s['images_after']:,}")


if __name__ == "__main__":
    run()
