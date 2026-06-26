import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from src import config
from src.services.user_kg import ensure_user_db

_STOPWORDS_FILE = Path(__file__).parent.parent / "stopwords.txt"
_STOPWORDS = set(_STOPWORDS_FILE.read_text().split(","))


class KnowledgeGraph:
    """SQLite-backed KG that queries on demand, never loading the full graph.

    The frozen base is opened read-only and never written; user additions live
    in a side DB attached as ``userkg`` and are merged into existence checks and
    neighborhood queries. Connects lazily on first use.
    """

    def __init__(self, path: Path = None, user_path: Path = None):
        self.base_path = Path(path or config.KG_PATH)
        self.user_path = Path(user_path or config.USER_KG_PATH)
        self.con: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        """Open the base read-only and attach the user DB, once."""
        if self.con is not None:
            return self.con
        ensure_user_db(self.user_path)
        print(f"[kg] Connecting to KG at {self.base_path} (read-only, + user additions) ...")
        con = sqlite3.connect(f"file:{self.base_path}?mode=ro", uri=True, check_same_thread=False)
        con.execute("ATTACH DATABASE ? AS userkg", (str(self.user_path),))
        self.con = con
        n_nodes = con.execute(
            "SELECT (SELECT COUNT(*) FROM nodes) + (SELECT COUNT(*) FROM userkg.nodes)").fetchone()[0]
        n_edges = con.execute(
            "SELECT (SELECT COUNT(*) FROM edges) + (SELECT COUNT(*) FROM userkg.edges)").fetchone()[0]
        print(f"[kg] {n_nodes:,} nodes, {n_edges:,} edges (base + user).")
        return con

    def attach_user(self) -> None:
        """Re-attach the user DB after a reset swapped the file."""
        if self.con is not None:
            try:
                self.con.execute("ATTACH DATABASE ? AS userkg", (str(self.user_path),))
            except sqlite3.OperationalError:
                pass

    def detach_user(self) -> None:
        """Detach the user DB so its file can be replaced."""
        if self.con is not None:
            try:
                self.con.execute("DETACH DATABASE userkg")
            except sqlite3.OperationalError:
                pass

    def close(self) -> None:
        if self.con is not None:
            self.con.close()
            self.con = None

    def existing_nodes(self, ids: list[str]) -> set[str]:
        """Subset of ids present in the base or the user DB."""
        ids = [i for i in ids if i]
        if not ids:
            return set()
        con = self._connect()
        ph = ",".join("?" * len(ids))
        rows = con.execute(
            f"SELECT id FROM nodes WHERE id IN ({ph}) "
            f"UNION SELECT id FROM userkg.nodes WHERE id IN ({ph})",
            ids + ids,
        ).fetchall()
        return {r[0] for r in rows}

    def has_edge(self, subject: str, predicate: str, object: str) -> bool:
        """Whether the exact triple already exists in either DB."""
        con = self._connect()
        row = con.execute(
            "SELECT 1 FROM edges WHERE subject=? AND predicate=? AND object=? "
            "UNION ALL "
            "SELECT 1 FROM userkg.edges WHERE subject=? AND predicate=? AND object=? "
            "LIMIT 1",
            (subject, predicate, object, subject, predicate, object),
        ).fetchone()
        return row is not None

    def predicates(self) -> list[dict]:
        """Distinct predicates across both DBs, for the add-triple autocomplete."""
        con = self._connect()
        rows = con.execute(
            "SELECT DISTINCT predicate, predicate_label FROM edges "
            "UNION SELECT DISTINCT predicate, predicate_label FROM userkg.edges"
        ).fetchall()
        return [{"predicate": p, "predicate_label": pl} for p, pl in rows]

    def get_subgraph(self, entity_uris: list[str], k: int = 1) -> dict:
        """BFS from seed entities up to k hops over base + user edges.

        Nodes carry '_depth' for ranking later.
        """
        if not entity_uris:
            return {"nodes": [], "edges": []}

        con = self._connect()
        frontier = self.existing_nodes(entity_uris)
        if not frontier:
            return {"nodes": [], "edges": []}

        depth: dict[str, int] = {uri: 0 for uri in frontier}
        visited_nodes = set(frontier)
        # keyed by (subject, predicate, object) to dedup the subject/object
        # double-match and any base/user overlap.
        collected: dict[tuple, dict] = {}

        for hop in range(k):
            if not frontier:
                break
            fl = list(frontier)
            ph = ",".join("?" * len(fl))
            cur = con.execute(
                f"SELECT subject, predicate, object, predicate_label FROM edges "
                f"WHERE subject IN ({ph}) OR object IN ({ph}) "
                f"UNION ALL "
                f"SELECT subject, predicate, object, predicate_label FROM userkg.edges "
                f"WHERE subject IN ({ph}) OR object IN ({ph})",
                fl + fl + fl + fl,
            )
            next_frontier: set[str] = set()
            for subj, pred, obj, pred_label in cur.fetchall():
                collected.setdefault((subj, pred, obj), {
                    "subject": subj, "predicate": pred, "object": obj,
                    "predicate_label": pred_label,
                })
                for neighbor in (subj, obj):
                    if neighbor not in visited_nodes:
                        next_frontier.add(neighbor)
                        depth[neighbor] = hop + 1
            visited_nodes |= next_frontier
            frontier = next_frontier

        # base wins on id collision; user nodes fill in the rest.
        vl = list(visited_nodes)
        ph = ",".join("?" * len(vl))
        nodes_by_id: dict[str, dict] = {}
        for table in ("nodes", "userkg.nodes"):
            cur = con.execute(
                f"SELECT id, label, types, image FROM {table} WHERE id IN ({ph})", vl)
            for nid, label, types, image in cur.fetchall():
                if nid in nodes_by_id:
                    continue
                nodes_by_id[nid] = {
                    "id": nid,
                    "label": label or nid,
                    "types": json.loads(types) if types else [],
                    "image": image,
                    "_depth": depth.get(nid, k),
                }

        return {"nodes": list(nodes_by_id.values()), "edges": list(collected.values())}


def rank_triples(
    subgraph: dict,
    question: str,
    k: int = None,
    max_triples: int = None,
) -> list[dict]:
    """
    Rank triples by proximity to seed entities + predicate overlap with the question.
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

    result = []
    for subj_id in seen_subjects:
        for e in groups[subj_id]:
            result.append(
                {
                    "subject": e["subject"],
                    "subject_label": node_label.get(e["subject"], e["subject"]),
                    "predicate": e["predicate"],
                    "predicate_label": e["predicate_label"],
                    "object": e["object"],
                    "object_label": node_label.get(e["object"], e["object"]),
                }
            )
    return result


def verbalise_triples(
    subgraph: dict, question: str, k: int = None, max_triples: int = None
) -> str:
    """
    Format ranked triples as [T1], [T2], ... text for the LLM prompt.
    """
    triples = rank_triples(subgraph, question, k, max_triples)
    return "\n".join(
        f"[T{i + 1}] {t['subject_label']} {t['predicate_label']} {t['object_label']}"
        for i, t in enumerate(triples)
    )


def triples_as_text(subgraph: dict) -> str:
    """
    Flat serialization of a subgraph, no ranking or numbering.
    """
    node_label = {n["id"]: n["label"] for n in subgraph["nodes"]}
    lines = []
    for e in subgraph["edges"]:
        s = node_label.get(e["subject"], e["subject"])
        p = e["predicate_label"]
        o = node_label.get(e["object"], e["object"])
        lines.append(f"{s} {p} {o}")
    return "\n".join(lines)


KG = KnowledgeGraph()
