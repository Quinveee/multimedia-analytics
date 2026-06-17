"""Unit tests for stage 04 (validate) — query forms, type constraints, evidence.

Builds a tiny in-memory index (no dumps needed) and exercises validate_question
directly. Run from offline/: python -m unittest discover -s tests
"""
import unittest

from rdflib import RDF

from scripts.uri_norm import canonical_uri
from scripts.validate import extract_bgp, validate_question

R = "http://dbpedia.org/resource/"
O = "http://dbpedia.org/ontology/"
TYPE = str(RDF.type)


def _build_index():
    """Mirror validate.build_index: relations in both dicts, rdf:type in sp_to_o only."""
    sp_to_o, po_to_s = {}, {}

    def add_rel(s, p, o):
        s, p, o = canonical_uri(s), canonical_uri(p), canonical_uri(o)
        sp_to_o.setdefault((s, p), set()).add(o)
        po_to_s.setdefault((p, o), set()).add(s)

    def add_type(s, cls):
        sp_to_o.setdefault((canonical_uri(s), TYPE), set()).add(canonical_uri(cls))

    for s, p, o in [
        (R + "A_Clockwork_Orange", O + "director", R + "Stanley_Kubrick"),
        (R + "2001_A_Space_Odyssey", O + "director", R + "Stanley_Kubrick"),
        (R + "Pittsburgh", O + "founder", R + "John_Forbes_(British_Army_officer)"),
        # index stores the %3F-encoded spelling decoded, as build_index would
        (R + "Ain't_I_a_Woman%3F_(book)", O + "author", R + "Bell_hooks"),
    ]:
        add_rel(s, p, o)
    add_type(R + "A_Clockwork_Orange", O + "Film")
    add_type(R + "Pittsburgh", O + "City")
    return sp_to_o, po_to_s


class TestValidate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = _build_index()

    def test_count_returns_all_evidence_triples(self):
        q = f"SELECT DISTINCT COUNT(?uri) WHERE {{ ?uri <{O}director> <{R}Stanley_Kubrick> }}"
        ev = validate_question(self.index, q)
        self.assertIsNotNone(ev)
        self.assertEqual(len(ev), 2)  # both films are evidence
        for e in ev:
            self.assertEqual(e["predicate"], "dbo:director")
            self.assertEqual(e["object"], "dbr:Stanley_Kubrick")

    def test_ask_true_is_retained(self):
        q = f"ASK WHERE {{ <{R}A_Clockwork_Orange> <{O}director> <{R}Stanley_Kubrick> }}"
        ev = validate_question(self.index, q)
        self.assertEqual(ev, [{"subject": "dbr:A_Clockwork_Orange",
                               "predicate": "dbo:director",
                               "object": "dbr:Stanley_Kubrick"}])

    def test_empty_select_is_dropped(self):
        q = f"SELECT DISTINCT ?uri WHERE {{ ?uri <{O}director> <{R}Nobody> }}"
        self.assertIsNone(validate_question(self.index, q))

    def test_type_constraint_and_intermediate_evidence(self):
        q = (f"SELECT DISTINCT ?uri WHERE {{ ?uri <{O}founder> "
             f"<{R}John_Forbes_(British_Army_officer)> . ?uri <{TYPE}> <{O}City> }}")
        ev = validate_question(self.index, q)
        self.assertIsNotNone(ev)
        preds = {(e["predicate"], e["object"]) for e in ev}
        self.assertIn(("dbo:founder", "dbr:John_Forbes_(British_Army_officer)"), preds)
        self.assertIn(("rdf:type", "dbo:City"), preds)  # type pattern is evidence too

    def test_type_constraint_filters_out_nonmatching(self):
        # A_Clockwork_Orange has director Kubrick but is a Film, not a City.
        q = (f"SELECT DISTINCT ?uri WHERE {{ ?uri <{O}director> <{R}Stanley_Kubrick> "
             f". ?uri <{TYPE}> <{O}City> }}")
        self.assertIsNone(validate_question(self.index, q))

    def test_encoding_mismatch_matches(self):
        # query uses the raw '?' spelling; index stored '%3F' — must still match
        q = f"ASK WHERE {{ <{R}Ain't_I_a_Woman?_(book)> <{O}author> <{R}Bell_hooks> }}"
        self.assertIsNotNone(validate_question(self.index, q))

    def test_unparseable_query_is_none(self):
        self.assertEqual(extract_bgp("this is not sparql"), [])
        self.assertIsNone(validate_question(self.index, "this is not sparql"))


if __name__ == "__main__":
    unittest.main()
