"""Unit tests for stage 06 (clean_graph) — predicate-noise + dangling/isolated
cleanup, and the image-safety guard. Run from offline/:
python -m unittest discover -s tests
"""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.clean_graph import clean, run

QPREDS = {"dbp:residence"}


def _kg():
    # A: kept via dbo: edge + question dbp: edge, has an image
    # B, E: kept (endpoints of kept edges)
    # C: isolated (no edges) -> dropped
    # D: only a dangling edge -> edge dropped -> D isolated -> dropped
    return {
        "nodes": [
            {"id": "dbr:A", "label": "A", "abstract": "", "types": ["Person"],
             "image": "images/A.jpg"},
            {"id": "dbr:B", "label": "B", "abstract": "", "types": [], "image": None},
            {"id": "dbr:E", "label": "E", "abstract": "", "types": [], "image": None},
            {"id": "dbr:C", "label": "C", "abstract": "", "types": [], "image": None},
            {"id": "dbr:D", "label": "D", "abstract": "", "types": [], "image": None},
        ],
        "edges": [
            {"subject": "dbr:A", "predicate": "dbo:director", "object": "dbr:B",
             "predicate_label": "director"},                              # dbo: -> keep
            {"subject": "dbr:A", "predicate": "dbp:residence", "object": "dbr:E",
             "predicate_label": "residence"},                            # question dbp: -> keep
            {"subject": "dbr:A", "predicate": "dbp:wikiPageUsesTemplate",
             "object": "dbr:B", "predicate_label": "x"},                 # noise dbp: -> drop
            {"subject": "dbr:A", "predicate": "http://x/foo", "object": "dbr:B",
             "predicate_label": "x"},                                    # non-dbpedia -> drop
            {"subject": "dbr:D", "predicate": "dbo:foo", "object": "dbr:GONE",
             "predicate_label": "foo"},                                  # dangling -> drop
        ],
    }


class TestCleanGraph(unittest.TestCase):
    def test_clean_keeps_dbo_and_question_dbp_only(self):
        cleaned, s = clean(_kg(), QPREDS)
        preds = {(e["subject"], e["predicate"], e["object"]) for e in cleaned["edges"]}
        self.assertEqual(preds, {("dbr:A", "dbo:director", "dbr:B"),
                                 ("dbr:A", "dbp:residence", "dbr:E")})
        self.assertEqual({n["id"] for n in cleaned["nodes"]}, {"dbr:A", "dbr:B", "dbr:E"})

    def test_stats_and_image_preserved(self):
        _, s = clean(_kg(), QPREDS)
        self.assertEqual((s["edges_before"], s["edges_after"]), (5, 2))
        self.assertEqual((s["nodes_before"], s["nodes_after"]), (5, 3))
        self.assertEqual(s["images_before"], s["images_after"])  # A's image survives
        self.assertEqual(s["images_after"], 1)

    def test_run_writes_in_place_preserving_images(self):
        with tempfile.TemporaryDirectory() as d:
            kgp = Path(d) / "kg_subset.json"
            urisp = Path(d) / "uris.json"
            kgp.write_text(json.dumps(_kg()), encoding="utf-8")
            urisp.write_text(json.dumps(
                {"predicates": ["http://dbpedia.org/property/residence"]}), encoding="utf-8")
            run(kg_path=kgp, uris_path=urisp)
            out = json.loads(kgp.read_text(encoding="utf-8"))
            self.assertEqual(len(out["edges"]), 2)
            self.assertEqual(next(n["image"] for n in out["nodes"] if n["id"] == "dbr:A"),
                             "images/A.jpg")

    def test_run_aborts_if_an_image_node_would_be_dropped(self):
        # X has an image but only a noise edge -> would become isolated -> must abort
        kg = {"nodes": [{"id": "dbr:X", "image": "images/X.jpg", "types": [], "abstract": ""}],
              "edges": [{"subject": "dbr:X", "predicate": "dbp:noise", "object": "dbr:Y",
                         "predicate_label": "n"}]}
        with tempfile.TemporaryDirectory() as d:
            kgp = Path(d) / "kg_subset.json"
            urisp = Path(d) / "uris.json"
            kgp.write_text(json.dumps(kg), encoding="utf-8")
            urisp.write_text(json.dumps({"predicates": []}), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                run(kg_path=kgp, uris_path=urisp)


if __name__ == "__main__":
    unittest.main()
