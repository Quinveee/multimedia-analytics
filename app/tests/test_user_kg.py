"""Unit tests for the user-KG write layer. Run from app/: python -m unittest discover -s tests"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.services import user_kg
from src.services.kg import KnowledgeGraph
from tests._kgfix import make_base_db

# Frozen base for these tests: only Marie Curie and Polonium exist.
BASE_NODES = [
    ("dbr:Marie_Curie", "Marie Curie", "physicist", ["Person", "Scientist"], "images/Marie_Curie.jpg"),
    ("dbr:Polonium", "Polonium", "an element", ["ChemicalElement"], None),
]
BASE_EDGES = [("dbr:Marie_Curie", "dbo:knownFor", "dbr:Polonium", "knownFor")]


class TestIds(unittest.TestCase):
    def test_label_to_dbr(self):
        self.assertEqual(user_kg.canonical_id("Marie Curie"), "dbr:Marie_Curie")
        self.assertEqual(user_kg.canonical_id("Dead Sea"), "dbr:Dead_Sea")

    def test_full_uri_shortened(self):
        self.assertEqual(
            user_kg.canonical_id("http://dbpedia.org/resource/Alan_Turing"),
            "dbr:Alan_Turing")

    def test_prefixed_passthrough(self):
        self.assertEqual(user_kg.canonical_id("dbr:Alan_Turing"), "dbr:Alan_Turing")

    def test_percent_decoded_via_canonical_uri(self):
        # canonical_uri must percent-decode (the dump encodes " as %22)
        self.assertEqual(user_kg.canonical_id('dbr:A%22B'), 'dbr:A"B')

    def test_predicate_freetext_defaults_to_dbp(self):
        self.assertEqual(user_kg.canonical_id("collaborated with", predicate=True),
                         "dbp:collaborated_with")

    def test_predicate_prefixed_honored(self):
        self.assertEqual(user_kg.canonical_id("dbo:knownFor", predicate=True), "dbo:knownFor")


class TestImageSave(unittest.TestCase):
    def test_slug_matches_offline_convention(self):
        # real base example: dbr:'03_Bonnie_&_Clyde is stored as images/03_Bonnie___Clyde.jpg
        self.assertEqual(user_kg.image_slug("dbr:'03_Bonnie_&_Clyde"), "03_Bonnie___Clyde.jpg")

    def test_save_writes_file_and_returns_rel_path(self):
        with tempfile.TemporaryDirectory() as d:
            rel = user_kg.save_user_image(b"\xff\xd8\xffJPEGBYTES", "dbr:Radioactivity",
                                          images_dir=Path(d) / "user_images")
            self.assertEqual(rel, "user_images/Radioactivity.jpg")
            self.assertTrue((Path(d) / "user_images" / "Radioactivity.jpg").is_file())


class TestWriteLayer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.base = make_base_db(d / "kg_subset.db", BASE_NODES, BASE_EDGES)
        self.user = d / "user_kg.db"
        self.images = d / "user_images"
        self.kg = KnowledgeGraph(path=self.base, user_path=self.user)

    def tearDown(self):
        self.kg.close()
        self.tmp.cleanup()

    def _add(self, **kw):
        kw.setdefault("kg", self.kg)
        kw.setdefault("user_path", self.user)
        kw.setdefault("images_dir", self.images)
        return user_kg.add_triple(**kw)

    def test_new_node_attached_to_existing(self):
        res = self._add(subject="dbr:Marie_Curie", predicate="dbo:award",
                        object="Nobel Prize in Physics", predicate_label="award",
                        object_node={"label": "Nobel Prize in Physics", "types": ["Award"]})
        self.assertEqual(res["object"], "dbr:Nobel_Prize_in_Physics")
        self.assertEqual([n["id"] for n in res["created_nodes"]], ["dbr:Nobel_Prize_in_Physics"])

    def test_edge_between_two_existing_nodes(self):
        res = self._add(subject="dbr:Polonium", predicate="dbo:discoverer",
                        object="dbr:Marie_Curie", predicate_label="discoverer")
        self.assertEqual(res["created_nodes"], [])  # both already exist

    def test_two_new_nodes_rejected(self):
        with self.assertRaises(ValueError) as cm:
            self._add(subject="Some New Thing", predicate="dbp:relatedTo",
                      object="Another New Thing")
        self.assertIn("must", str(cm.exception).lower())

    def test_self_loop_rejected(self):
        with self.assertRaises(ValueError):
            self._add(subject="dbr:Marie_Curie", predicate="dbp:sameAs",
                      object="dbr:Marie_Curie")

    def test_duplicate_triple_rejected(self):
        # the exact triple already exists in the base
        with self.assertRaises(ValueError):
            self._add(subject="dbr:Marie_Curie", predicate="dbo:knownFor",
                      object="dbr:Polonium", predicate_label="knownFor")

    def test_provenance_tagged_in_user_db(self):
        self._add(subject="dbr:Marie_Curie", predicate="dbo:field",
                  object="Radioactivity", predicate_label="field",
                  object_node={"label": "Radioactivity"})
        con = sqlite3.connect(str(self.user))
        try:
            e_src, e_at = con.execute(
                "SELECT source, created_at FROM edges WHERE object='dbr:Radioactivity'").fetchone()
            n_src, n_at = con.execute(
                "SELECT source, created_at FROM nodes WHERE id='dbr:Radioactivity'").fetchone()
        finally:
            con.close()
        self.assertEqual(e_src, "user")
        self.assertEqual(n_src, "user")
        self.assertTrue(e_at and n_at)  # timestamps present

    def test_node_fields_persisted(self):
        self._add(subject="dbr:Marie_Curie", predicate="dbo:field",
                  object="Radioactivity",
                  object_node={"label": "Radioactivity", "abstract": "the study of decay",
                               "types": "Concept, Field"})
        con = sqlite3.connect(str(self.user))
        try:
            label, abstract, types = con.execute(
                "SELECT label, abstract, types FROM nodes WHERE id='dbr:Radioactivity'").fetchone()
        finally:
            con.close()
        self.assertEqual(label, "Radioactivity")
        self.assertEqual(abstract, "the study of decay")
        self.assertEqual(json.loads(types), ["Concept", "Field"])


if __name__ == "__main__":
    unittest.main()
