"""End-to-end test of the user-KG addition lifecycle.

Confirms a user-added triple is written to the side DB, appears through the
merged read layer, is retrievable for regeneration, survives a base re-run, and
is removed by reset. Run from app/: python -m unittest discover -s tests
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.services import user_kg
from src.services.kg import KnowledgeGraph, rank_triples, verbalise_triples
from tests._kgfix import make_base_db

QUESTION = "What did Marie Curie work on?"
SEED = "dbr:Marie_Curie"

# Frozen base: Marie Curie exists, but has no link to "Radioactivity".
BASE_NODES = [
    ("dbr:Marie_Curie", "Marie Curie", "physicist", ["Person", "Scientist"], "images/Marie_Curie.jpg"),
    ("dbr:Polonium", "Polonium", "an element", ["ChemicalElement"], None),
]
BASE_EDGES = [("dbr:Marie_Curie", "dbo:knownFor", "dbr:Polonium", "knownFor")]


def _triple_in(subgraph, s, p, o):
    return any(e["subject"] == s and e["predicate"] == p and e["object"] == o
               for e in subgraph["edges"])


class TestUserKgLifecycle(unittest.TestCase):
    def test_full_lifecycle(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            base = make_base_db(d / "kg_subset.db", BASE_NODES, BASE_EDGES)
            user = d / "user_kg.db"
            images = d / "user_images"

            kg = KnowledgeGraph(path=base, user_path=user)

            # attach a new node (with an uploaded image) to the existing seed
            res = user_kg.add_triple(
                subject=SEED, predicate="dbo:field", object="Radioactivity",
                predicate_label="field",
                object_node={"label": "Radioactivity", "abstract": "study of decay",
                             "types": ["Concept"], "image_bytes": b"\xff\xd8\xffIMG"},
                kg=kg, user_path=user, images_dir=images)
            new_obj = res["object"]
            self.assertEqual(new_obj, "dbr:Radioactivity")

            # written to the user DB, base left untouched
            ucon = sqlite3.connect(str(user))
            try:
                self.assertEqual(
                    ucon.execute("SELECT source FROM edges WHERE object=?", (new_obj,)).fetchone()[0],
                    "user")
            finally:
                ucon.close()
            bcon = sqlite3.connect(str(base))
            try:
                self.assertEqual(bcon.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
                                 len(BASE_EDGES))
                self.assertIsNone(
                    bcon.execute("SELECT 1 FROM nodes WHERE id=?", (new_obj,)).fetchone())
            finally:
                bcon.close()

            # appears in the seed's neighborhood through the merged read layer
            sub = kg.get_subgraph([SEED], k=1)
            self.assertTrue(_triple_in(sub, SEED, "dbo:field", new_obj))
            new_node = next(n for n in sub["nodes"] if n["id"] == new_obj)
            self.assertEqual(new_node["image"], "user_images/Radioactivity.jpg")
            self.assertTrue((images / "Radioactivity.jpg").is_file())

            # retrievable for regeneration
            ranked = rank_triples(sub, QUESTION)
            self.assertTrue(any(t["object"] == new_obj for t in ranked))
            self.assertIn("Radioactivity", verbalise_triples(sub, QUESTION))

            # survives a base re-run that rebuilds kg_subset.db
            kg.close()
            make_base_db(base, BASE_NODES, BASE_EDGES)
            kg2 = KnowledgeGraph(path=base, user_path=user)
            sub2 = kg2.get_subgraph([SEED], k=1)
            self.assertTrue(_triple_in(sub2, SEED, "dbo:field", new_obj),
                            "user addition must survive a base re-run")

            # removed by reset
            out = user_kg.reset(kg=kg2, user_path=user, images_dir=images)
            self.assertEqual(out["images_removed"], 1)
            sub3 = kg2.get_subgraph([SEED], k=1)
            self.assertFalse(_triple_in(sub3, SEED, "dbo:field", new_obj))
            self.assertFalse((images / "Radioactivity.jpg").exists())
            kg2.close()


if __name__ == "__main__":
    unittest.main()
