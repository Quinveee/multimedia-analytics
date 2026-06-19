import bz2
import tempfile
import unittest
from pathlib import Path
from scripts.uri_norm import canonical_uri
from scripts.neighbourhood import stream_triples

R = "http://dbpedia.org/resource/"
O = "http://dbpedia.org/ontology/"

# Synthetic dump: comment, seed-as-subject, seed-as-object, unrelated,
# encoding-mismatch (dump %3F vs raw-? seed), and a literal-object line.
FIXTURE_LINES = [
    "# started 2016-07-09T14:49:53Z",
    f"<{R}Stanley_Kubrick> <{O}child> <{R}Vivian_Kubrick> .",  # subj seed -> keep
    f"<{R}A_Clockwork_Orange> <{O}director> <{R}Stanley_Kubrick> .",  # obj seed  -> keep (the bug)
    f"<{R}Unrelated_Thing> <{O}foo> <{R}Other_Thing> .",  # neither   -> drop
    f"<{R}Ain't_I_a_Woman%3F_(book)> <{O}author> <{R}Bell_Hooks> .",  # %3F subj  -> keep via norm
    f'<{R}Stanley_Kubrick> <{O}birthName> "Stanley Kubrick"@en .',  # literal   -> drop (regex)
]


class TestBidirectionalHop1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dump = Path(cls.tmp.name) / "mini.ttl.bz2"
        with bz2.open(cls.dump, "wt", encoding="utf-8") as f:
            f.write("\n".join(FIXTURE_LINES) + "\n")
        # Seeds are canonical, exactly as load_seeds() would produce them.
        # Note the seed is the RAW spelling; the dump uses the %3F spelling.
        cls.seeds = {
            canonical_uri(R + "Stanley_Kubrick"),
            canonical_uri(R + "Ain't_I_a_Woman?_(book)"),
        }
        cls.triples = stream_triples(cls.dump, cls.seeds)

    def test_keeps_subject_and_object_seed_triples(self):
        objects = {(t["s"], t["o"]) for t in self.triples}
        # seed as subject
        self.assertIn((R + "Stanley_Kubrick", R + "Vivian_Kubrick"), objects)
        # seed as OBJECT — the bidirectional case that was previously dropped
        self.assertIn((R + "A_Clockwork_Orange", R + "Stanley_Kubrick"), objects)

    def test_drops_unrelated_triple(self):
        for t in self.triples:
            self.assertNotEqual(t["s"], R + "Unrelated_Thing")

    def test_drops_literal_object_line(self):
        for t in self.triples:
            self.assertNotIn("birthName", t["p"])

    def test_encoding_mismatch_is_matched_but_original_spelling_preserved(self):
        encoded = R + "Ain't_I_a_Woman%3F_(book)"
        kept = [t for t in self.triples if t["s"] == encoded]
        self.assertEqual(len(kept), 1, "seed with %3F should match the raw-? seed")
        # output keeps the dump's original spelling (full IRI for SPARQL validation)
        self.assertEqual(kept[0]["s"], encoded)

    def test_exact_kept_count(self):
        self.assertEqual(len(self.triples), 3)


if __name__ == "__main__":
    unittest.main()
