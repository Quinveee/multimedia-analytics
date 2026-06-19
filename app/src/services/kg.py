import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from src import config

_STOPWORDS_FILE = Path(__file__).parent.parent / "stopwords.txt"
_STOPWORDS = set(_STOPWORDS_FILE.read_text().split(","))


class KnowledgeGraph:
    """SQLite-backed KG. Queries on demand — never loads the full graph into memory."""

    def __init__(self, path: Path = None):
        path = Path(path or config.KG_PATH)
        print(f"[kg] Connecting to KG at {path} ...")
        self.con = sqlite3.connect(str(path), check_same_thread=False)
        cur = self.con.execute("SELECT COUNT(*) FROM nodes")
        n_nodes = cur.fetchone()[0]
        cur = self.con.execute("SELECT COUNT(*) FROM edges")
        n_edges = cur.fetchone()[0]
        print(f"[kg] {n_nodes:,} nodes, {n_edges:,} edges.")

    def get_subgraph(self, entity_uris: list[str], k: int = 1) -> dict:
        """BFS from seed entities up to k hops. Nodes carry '_depth' for ranking later."""
        cur = self.con.execute(
            f"SELECT id FROM nodes WHERE id IN ({','.join('?' * len(entity_uris))})",
            entity_uris,
        )
        frontier = {row[0] for row in cur.fetchall()}

        if not frontier:
            return {"nodes": [], "edges": []}

        depth: dict[str, int] = {uri: 0 for uri in frontier}
        visited_nodes = set(frontier)
        collected_edges: list[dict] = []
        seen_rowids: set[int] = set()

        for hop in range(k):
            if not frontier:
                break
            fl = list(frontier)
            ph = ",".join("?" * len(fl))
            cur = self.con.execute(
                f"SELECT rowid, subject, predicate, object, predicate_label FROM edges "
                f"WHERE subject IN ({ph}) OR object IN ({ph})",
                fl + fl,
            )
            next_frontier: set[str] = set()
            for rowid, subj, pred, obj, pred_label in cur.fetchall():
                if rowid not in seen_rowids:
                    seen_rowids.add(rowid)
                    collected_edges.append({
                        "subject": subj,
                        "predicate": pred,
                        "object": obj,
                        "predicate_label": pred_label,
                    })
                for neighbor in (subj, obj):
                    if neighbor not in visited_nodes:
                        next_frontier.add(neighbor)
                        depth[neighbor] = hop + 1
            visited_nodes |= next_frontier
            frontier = next_frontier

        vl = list(visited_nodes)
        cur = self.con.execute(
            f"SELECT id, label, types, image FROM nodes WHERE id IN ({','.join('?' * len(vl))})",
            vl,
        )
        nodes = [
            {
                "id": row[0],
                "label": row[1] or row[0],
                "types": json.loads(row[2]) if row[2] else [],
                "image": row[3],
                "_depth": depth.get(row[0], k),
            }
            for row in cur.fetchall()
        ]

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


KG = KnowledgeGraph()
