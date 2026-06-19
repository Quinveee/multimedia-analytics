import json
import re
from collections import defaultdict
from pathlib import Path

from src import config

_STOPWORDS_FILE = Path(__file__).parent.parent / "stopwords.txt"
_STOPWORDS = set(_STOPWORDS_FILE.read_text().split(","))


class KnowledgeGraph:
    """
    KG loaded once at startup with an adjacency index for fast k-hop traversal.
    """

    def __init__(self, path: Path = None):
        path = Path(path or config.KG_PATH)
        print(f"[kg] Loading KG from {path} ...")
        data = json.loads(path.read_text())
        self.nodes: dict[str, dict] = {n["id"]: n for n in data["nodes"]}
        self.edges: list[dict] = data["edges"]
        self._adj: dict[str, list[dict]] = defaultdict(list)
        for e in self.edges:
            self._adj[e["subject"]].append(e)
            self._adj[e["object"]].append(e)
        print(f"[kg] Loaded {len(self.nodes):,} nodes, {len(self.edges):,} edges.")

    def get_subgraph(self, entity_uris: list[str], k: int = 1) -> dict:
        """BFS from seed entities up to k hops. Nodes carry '_depth' for ranking later."""
        frontier = {uri for uri in entity_uris if uri in self.nodes}

        if not frontier:
            return {"nodes": [], "edges": []}

        depth: dict[str, int] = {uri: 0 for uri in frontier}
        visited_nodes = set(frontier)
        collected_edges: list[dict] = []
        seen_edges: set[int] = set()

        for hop in range(k):
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
                        depth[neighbor] = hop + 1
            visited_nodes |= next_frontier
            frontier = next_frontier

        nodes = [{**self.nodes[nid], "_depth": depth[nid]} for nid in visited_nodes]
        return {"nodes": nodes, "edges": collected_edges}


def verbalise_triples(
    subgraph: dict,
    question: str,
    seed_uris: list[str],
    k: int = None,
    max_triples: int = None,
) -> str:
    """
    Rank triples by proximity to seed entities + predicate overlap with the question,
    cap at max_triples, and return them as numbered [T1], [T2], ... lines for the LLM.
    """
    if k is None:
        k = config.KG_HOP
    if max_triples is None:
        max_triples = config.KG_MAX_TRIPLES

    node_label = {n["id"]: n["label"] for n in subgraph["nodes"]}
    node_depth = {n["id"]: n["_depth"] for n in subgraph["nodes"]}

    question_words = {
        w for w in re.findall(r"[a-z]+", question.lower()) if w not in _STOPWORDS
    }

    def score(e: dict) -> float:
        d = min(node_depth.get(e["subject"], k), node_depth.get(e["object"], k))
        proximity = k - d + 1
        pred_words = set(re.findall(r"[a-z]+", e["predicate_label"].lower()))
        predicate_match = len(pred_words & question_words)
        return proximity + predicate_match

    ranked = sorted(subgraph["edges"], key=score, reverse=True)[:max_triples]

    # group by subject label, preserving rank order within each group
    groups: dict[str, list[dict]] = defaultdict(list)
    seen_subjects: list[str] = []
    for e in ranked:
        s = e["subject"]
        if s not in groups:
            seen_subjects.append(s)
        groups[s].append(e)

    lines = []
    for subj_id in seen_subjects:
        for e in groups[subj_id]:
            s = node_label.get(e["subject"], e["subject"])
            p = e["predicate_label"]
            o = node_label.get(e["object"], e["object"])
            lines.append(f"{s} {p} {o}")

    return "\n".join(f"[T{i + 1}] {line}" for i, line in enumerate(lines))


def triples_as_text(subgraph: dict) -> str:
    """Flat serialization of a subgraph, no ranking or numbering. Useful for debugging."""
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
