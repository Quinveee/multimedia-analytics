"""Shared test helper for building a small frozen-base kg_subset.db."""

import json
import sqlite3
from pathlib import Path


def make_base_db(path, nodes, edges):
    """Build a base DB matching the offline schema (no provenance columns).

    nodes: (id, label, abstract, types(list), image). edges: (s, p, o, p_label).
    """
    path = Path(path)
    path.unlink(missing_ok=True)
    con = sqlite3.connect(str(path))
    try:
        con.execute("CREATE TABLE nodes (id TEXT PRIMARY KEY, label TEXT, "
                    "abstract TEXT, types TEXT, image TEXT)")
        con.execute("CREATE TABLE edges (subject TEXT, predicate TEXT, "
                    "object TEXT, predicate_label TEXT)")
        con.executemany(
            "INSERT INTO nodes VALUES (?, ?, ?, ?, ?)",
            [(i, lab, ab, json.dumps(ty or []), img) for (i, lab, ab, ty, img) in nodes])
        con.executemany("INSERT INTO edges VALUES (?, ?, ?, ?)", edges)
        con.execute("CREATE INDEX idx_edges_subject ON edges(subject)")
        con.execute("CREATE INDEX idx_edges_object ON edges(object)")
        con.commit()
    finally:
        con.close()
    return path
