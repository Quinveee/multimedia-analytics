import unittest
from scripts.uri_norm import canonical_uri

R = "http://dbpedia.org/resource/"


class TestCanonicalUri(unittest.TestCase):
    def test_decodes_chars_the_dump_percent_encodes(self):
        # Verified dump spellings: " -> %22, ? -> %3F, ` -> %60
        self.assertEqual(canonical_uri(R + "Joe_%22Peps%22"), R + 'Joe_"Peps"')
        self.assertEqual(canonical_uri(R + "Ain't_I_a_Woman%3F_(book)"),
                         R + "Ain't_I_a_Woman?_(book)")
        self.assertEqual(canonical_uri(R + "%60Abdu'l-Bahá"),
                         R + "`Abdu'l-Bahá")

    def test_decodes_utf8_percent_sequences(self):
        self.assertEqual(canonical_uri(R + "Caf%C3%A9"), R + "Café")

    def test_raw_chars_pass_through_unchanged(self):
        # The dump leaves these raw; so do the seeds — must stay untouched.
        for local in ("A&M_Records", "AT&T_Corporation", "Illinois's_7th_district",
                      "John_Forbes_(British_Army_officer)", "'03_Bonnie_&_Clyde"):
            self.assertEqual(canonical_uri(R + local), R + local)

    def test_dump_and_query_spellings_collapse(self):
        # The whole point: encoded (dump) and raw (query) forms must compare equal.
        dump_form = R + "Ain't_I_a_Woman%3F_(book)"
        query_form = R + "Ain't_I_a_Woman?_(book)"
        self.assertEqual(canonical_uri(dump_form), canonical_uri(query_form))

    def test_idempotent_on_single_encoded_uris(self):
        for u in (R + "Stanley_Kubrick", R + "Joe_%22Peps%22", R + "A&M_Records"):
            self.assertEqual(canonical_uri(canonical_uri(u)), canonical_uri(u))

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(canonical_uri("  " + R + "Stanley_Kubrick  "),
                         R + "Stanley_Kubrick")


if __name__ == "__main__":
    unittest.main()
