import json
from collections import defaultdict
from pathlib import Path

import config


class KnowledgeGraph:
    """KG loaded once at startup with an adjacency index for fast k-hop traversal."""

    def __init__(self, path: Path = None):
        path = Path(path or config.KG_PATH)
        print(f"[kg] Loading KG from {path} ...")
        data = json.loads(path.read_text())
        self.nodes: dict[str, dict] = {n["id"]: n for n in data["nodes"]}
        self.edges: list[dict] = data["edges"]
        # adjacency index: node_id → list of edges touching it
        self._adj: dict[str, list[dict]] = defaultdict(list)
        for e in self.edges:
            self._adj[e["subject"]].append(e)
            self._adj[e["object"]].append(e)
        print(f"[kg] Loaded {len(self.nodes):,} nodes, {len(self.edges):,} edges.")

    def get_subgraph(self, entity_uris: list[str], k: int = 1) -> dict:
        """Return a k-hop subgraph reachable from the given entity URIs."""
        frontier = {uri for uri in entity_uris if uri in self.nodes}

        if not frontier:
            return {"nodes": [], "edges": []}

        visited_nodes = set(frontier)
        collected_edges: list[dict] = []
        seen_edges: set[int] = set()

        for _ in range(k):
            next_frontier = set()
            for node_id in frontier:
                for e in self._adj[node_id]:
                    eid = id(e)
                    if eid not in seen_edges:
                        seen_edges.add(eid)
                        collected_edges.append(e)
                    neighbor = e["object"] if e["subject"] == node_id else e["subject"]
                    if neighbor not in visited_nodes:
                        next_frontier.add(neighbor)
            visited_nodes |= next_frontier
            frontier = next_frontier

        nodes = [self.nodes[nid] for nid in visited_nodes]
        return {"nodes": nodes, "edges": collected_edges}


def triples_as_text(subgraph: dict) -> str:
    """Serialize a subgraph as a newline-separated list of 'subject predicate object' triples."""
    node_label = {n["id"]: n["label"] for n in subgraph["nodes"]}
    lines = []
    for e in subgraph["edges"]:
        s = node_label.get(e["subject"], e["subject"])
        p = e["predicate_label"]
        o = node_label.get(e["object"], e["object"])
        lines.append(f"{s} {p} {o}")
    return "\n".join(lines)


# singleton loaded at import time
KG = KnowledgeGraph()
