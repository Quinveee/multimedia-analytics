"""Tests for the popup form parsing, including image-upload decoding.

Imports the Dash popup module, so run under the app venv. From app/:
python -m unittest discover -s tests
"""

import base64
import unittest

from src import studio_add_triple as t


class TestParseForm(unittest.TestCase):
    def test_custom_predicate_overrides_dropdown(self):
        kw = t.parse_form("dbr:A", "dbo:fromDropdown", "dbo:custom", "custom", "dbr:B",
                          "", "", "")
        self.assertEqual(kw["predicate"], "dbo:custom")

    def test_missing_predicate_raises(self):
        with self.assertRaises(ValueError):
            t.parse_form("dbr:A", None, "", "label", "dbr:B", "", "", "")

    def test_missing_endpoint_raises(self):
        with self.assertRaises(ValueError):
            t.parse_form("", "dbo:p", None, "p", "dbr:B", "", "", "")

    def test_node_fields_collected(self):
        kw = t.parse_form("dbr:Marie_Curie", "dbo:field", None, "field", "Radioactivity",
                          "Radioactivity", "study of decay", "Concept, Field")
        self.assertEqual(kw["object_node"]["label"], "Radioactivity")
        self.assertEqual(kw["object_node"]["abstract"], "study of decay")
        self.assertEqual(kw["object_node"]["types"], "Concept, Field")

    def test_image_upload_decoded(self):
        raw = b"\x89PNG\r\n\x1a\nFAKEIMG"
        contents = "data:image/png;base64," + base64.b64encode(raw).decode()
        kw = t.parse_form("dbr:Marie_Curie", "dbo:field", None, "field", "Radioactivity",
                          "Radioactivity", "", "", contents)
        self.assertEqual(kw["object_node"]["image_bytes"], raw)

    def test_no_image_means_no_image_bytes(self):
        kw = t.parse_form("dbr:Marie_Curie", "dbo:field", None, "field", "Radioactivity",
                          "Radioactivity", "", "")
        self.assertNotIn("image_bytes", kw["object_node"])


if __name__ == "__main__":
    unittest.main()
