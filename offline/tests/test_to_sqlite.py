"""Unit tests for stage 07 (to_sqlite) — table contents, indexes, neighborhood
query. Run from offline/: python -m unittest discover -s tests
"""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.to_sqlite import run

KG = {
    "nodes": [
        {"id": "dbr:Marie_Curie", "label": "Marie Curie", "abstract": "physicist",
         "types": ["Person", "Scientist"], "image": "images/Marie_Curie.jpg"},
        {"id": "dbr:Polonium", "label": "Polonium", "abstract": "", "types": [],
         "image": None},
    ],
    "edges": [
        {"subject": "dbr:Marie_Curie", "predicate": "dbo:knownFor",
         "object": "dbr:Polonium", "predicate_label": "knownFor"},
    ],
}


class TestToSqlite(unittest.TestCase):
    def _build(self, d):
        kgp = Path(d) / "kg_subset.json"
        dbp = Path(d) / "kg_subset.db"
        kgp.write_text(json.dumps(KG), encoding="utf-8")
        run(kg_path=kgp, db_path=dbp)
        return dbp

    def test_tables_populated_and_types_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            con = sqlite3.connect(self._build(d))
            self.assertEqual(con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0], 2)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM edges").fetchone()[0], 1)
            types, image = con.execute(
                "SELECT types, image FROM nodes WHERE id='dbr:Marie_Curie'").fetchone()
            self.assertEqual(json.loads(types), ["Person", "Scientist"])
            self.assertEqual(image, "images/Marie_Curie.jpg")
            self.assertIsNone(
                con.execute("SELECT image FROM nodes WHERE id='dbr:Polonium'").fetchone()[0])
            con.close()

    def test_neighborhood_query_and_indexes(self):
        with tempfile.TemporaryDirectory() as d:
            con = sqlite3.connect(self._build(d))
            rows = con.execute(
                "SELECT subject, predicate, object FROM edges WHERE subject=? OR object=?",
                ("dbr:Polonium", "dbr:Polonium")).fetchall()
            self.assertEqual(rows, [("dbr:Marie_Curie", "dbo:knownFor", "dbr:Polonium")])
            idx = {r[1] for r in con.execute("PRAGMA index_list('edges')")}
            self.assertEqual(idx, {"idx_edges_subject", "idx_edges_object"})
            con.close()

    def test_rebuild_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            dbp = self._build(d)
            self._build(d)  # run again -> should not error or duplicate
            con = sqlite3.connect(dbp)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0], 2)
            con.close()


if __name__ == "__main__":
    unittest.main()
