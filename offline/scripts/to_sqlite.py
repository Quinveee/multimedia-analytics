# Stage 7 of the pipeline.
# Loads kg_subset.json into a small SQLite database so the backend can look up
# parts of the graph quickly, without reading the whole big json into memory.
#
# Tables:
#   nodes(id, label, abstract, types, image)
#       id is the primary key, so fetching one node by its id is instant.
#       types is stored as a json string, image is the path or NULL.
#   edges(subject, predicate, object, predicate_label)
#
# Indexes:
#   one index on edges.subject and one on edges.object.
#   Those two are what make "give me everything connected to node X" fast:
#       SELECT * FROM edges WHERE subject = ? OR object = ?
#   Looking a node up by id is already fast because id is the primary key.
#
# Writes data/kg_subset.db.

import json
import sqlite3
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data"
KG_PATH = DATA_DIR / "kg_subset.json"
DB_PATH = DATA_DIR / "kg_subset.db"


def build(kg: dict, db_path: Path) -> tuple[int, int]:
    db_path.unlink(missing_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("CREATE TABLE nodes (id TEXT PRIMARY KEY, label TEXT, "
                    "abstract TEXT, types TEXT, image TEXT)")
        con.execute("CREATE TABLE edges (subject TEXT, predicate TEXT, "
                    "object TEXT, predicate_label TEXT)")
        con.executemany(
            "INSERT OR REPLACE INTO nodes VALUES (?, ?, ?, ?, ?)",
            ((n["id"], n.get("label"), n.get("abstract"),
              json.dumps(n.get("types") or []), n.get("image")) for n in kg["nodes"]))
        con.executemany(
            "INSERT INTO edges VALUES (?, ?, ?, ?)",
            ((e["subject"], e["predicate"], e["object"], e.get("predicate_label"))
             for e in kg["edges"]))
        con.execute("CREATE INDEX idx_edges_subject ON edges(subject)")
        con.execute("CREATE INDEX idx_edges_object ON edges(object)")
        con.commit()
        n = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        e = con.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    finally:
        con.close()
    return n, e


def run(kg_path: Optional[Path] = None, db_path: Optional[Path] = None) -> None:
    kg_path = kg_path or KG_PATH
    db_path = db_path or DB_PATH
    print("loading kg_subset...")
    kg = json.loads(kg_path.read_text(encoding="utf-8"))
    n, e = build(kg, db_path)
    print(f"  kg_subset.db: {n:,} nodes, {e:,} edges "
          f"(indexes on edges.subject, edges.object)")
    print(f"  size: {db_path.stat().st_size / 1e6:.0f} MB -> {db_path}")


if __name__ == "__main__":
    run()
