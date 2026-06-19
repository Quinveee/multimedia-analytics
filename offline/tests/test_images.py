"""Unit tests for stage 05 (images) — uses a tiny synthetic MMpedia fixture
(entity2image.json + a generated image + a generated tar). No network, no real
MMpedia. Run from offline/: python -m unittest discover -s tests
"""
import csv
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import scripts.images as images
from scripts.images import (_archive_rel, _ensure_archive, archive_of,
                            fetch_thumbnails, load_focus_entities, match_entities,
                            node_key, run, slug, thumbnail)


def _make_png(path: Path, size=(800, 600)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (120, 200, 60)).save(path, "PNG")


class TestPureHelpers(unittest.TestCase):
    def test_node_key_strips_prefix_and_canonicalizes(self):
        self.assertEqual(node_key("dbr:Bart_Tanski"), "Bart_Tanski")
        self.assertEqual(node_key("dbr:Ain't_I_a_Woman%3F_(book)"),
                         "Ain't_I_a_Woman?_(book)")

    def test_archive_of(self):
        self.assertEqual(archive_of("MMpedia/Entlist141/Bart Tanski/Bart Tanski+1.jpg"),
                         "Entlist141.tar")
        self.assertIsNone(archive_of("no/entlist/path.jpg"))

    def test_archive_rel_strips_mmpedia_prefix(self):
        self.assertEqual(_archive_rel("MMpedia/Entlist008/Jean Taylor/Jean Taylor+1.jpg"),
                         "Entlist008/Jean Taylor/Jean Taylor+1.jpg")
        self.assertEqual(_archive_rel("Entlist008/x/x+1.jpg"), "Entlist008/x/x+1.jpg")

    def test_slug_is_filesystem_safe(self):
        self.assertEqual(slug("dbr:Bart_Tanski"), "Bart_Tanski.jpg")
        self.assertNotIn("/", slug("dbr:AC/DC"))

    def test_match_entities_normalizes_both_sides(self):
        nodes = ["dbr:Marie_Curie", "dbr:Unknown", "dbr:Ain't_I_a_Woman%3F_(book)"]
        e2i = {
            "Marie_Curie": ["Entlist001/Marie Curie/Marie Curie+1.jpg"],
            "Ain't_I_a_Woman?_(book)": ["Entlist009/x/x+1.jpg"],  # raw '?' vs node %3F
        }
        matched = match_entities(nodes, e2i)
        self.assertEqual(set(matched), {"dbr:Marie_Curie", "dbr:Ain't_I_a_Woman%3F_(book)"})


class TestFocusEntities(unittest.TestCase):
    def test_collects_dbr_seeds_and_evidence_only(self):
        with tempfile.TemporaryDirectory() as d:
            vp = Path(d) / "validated_questions.json"
            vp.write_text(json.dumps([{
                "seed_uris": ["dbr:Stanley_Kubrick"],
                "evidence_triples": [
                    {"subject": "dbr:A_Clockwork_Orange", "predicate": "dbo:director",
                     "object": "dbr:Stanley_Kubrick"},
                    {"subject": "dbr:Pittsburgh", "predicate": "rdf:type",
                     "object": "dbo:City"},  # dbo:/rdf: must be excluded
                ],
            }]), encoding="utf-8")
            focus = load_focus_entities(vp)
            self.assertEqual(focus, {"dbr:Stanley_Kubrick", "dbr:A_Clockwork_Orange",
                                     "dbr:Pittsburgh"})

    def test_missing_file_is_empty(self):
        self.assertEqual(load_focus_entities(Path("nope/validated.json")), set())


class TestThumbnail(unittest.TestCase):
    def test_resizes_to_at_most_256_and_is_jpeg(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src.png"
            _make_png(src, (1000, 400))
            dest = Path(d) / "out.jpg"
            thumbnail(src, dest, size=256)
            with Image.open(dest) as im:
                self.assertLessEqual(max(im.size), 256)
                self.assertEqual(im.format, "JPEG")


class TestFetchThumbnails(unittest.TestCase):
    def test_from_already_extracted_file(self):
        with tempfile.TemporaryDirectory() as d:
            mm = Path(d) / "mmpedia"
            # entity2image path has the 'MMpedia/' prefix; extracted file does not
            _make_png(mm / "Entlist001/Marie Curie/Marie Curie+1.jpg")
            out = Path(d) / "images"
            thumbs = fetch_thumbnails(
                {"dbr:Marie_Curie": ["MMpedia/Entlist001/Marie Curie/Marie Curie+1.jpg"]},
                mm, out, auto_download=False)
            self.assertEqual(thumbs, {"dbr:Marie_Curie": "images/Marie_Curie.jpg"})
            self.assertTrue((out / "Marie_Curie.jpg").exists())

    def test_from_local_tar_then_deletes_archive(self):
        images.KEEP_ARCHIVES = False  # deterministic regardless of env
        with tempfile.TemporaryDirectory() as d:
            mm = Path(d) / "mmpedia"
            mm.mkdir(parents=True)
            member = "Entlist002/Pierre Curie/Pierre Curie+1.jpg"  # tar root, no MMpedia/
            png = Path(d) / "tmp.png"
            _make_png(png)
            tar_path = mm / "Entlist002.tar"
            with tarfile.open(tar_path, "w") as tar:
                tar.add(png, arcname=member)
            out = Path(d) / "images"
            # entity2image path carries the 'MMpedia/' prefix the tar member lacks
            thumbs = fetch_thumbnails(
                {"dbr:Pierre_Curie": ["MMpedia/" + member]}, mm, out, auto_download=False)
            self.assertEqual(thumbs, {"dbr:Pierre_Curie": "images/Pierre_Curie.jpg"})
            self.assertTrue((out / "Pierre_Curie.jpg").exists())
            self.assertFalse(tar_path.exists())  # ~3 GB tar dropped after extraction

    def test_resume_skip_existing_thumbnail_avoids_archive(self):
        with tempfile.TemporaryDirectory() as d:
            mm = Path(d) / "mmpedia"
            mm.mkdir(parents=True)
            out = Path(d) / "images"
            _make_png(out / slug("dbr:Z"), (10, 10))  # pretend a previous run made it
            # Only an archive path, no local file, no tar, no download allowed:
            # without resume-skip this would be skipped; with it, returned as-is.
            thumbs = fetch_thumbnails(
                {"dbr:Z": ["Entlist003/Z/Z+1.jpg"]}, mm, out, auto_download=False)
            self.assertEqual(thumbs, {"dbr:Z": "images/Z.jpg"})

    def test_missing_archive_and_no_download_skips(self):
        with tempfile.TemporaryDirectory() as d:
            mm = Path(d) / "mmpedia"
            mm.mkdir(parents=True)
            thumbs = fetch_thumbnails(
                {"dbr:X": ["Entlist003/X/X+1.jpg"]}, mm, Path(d) / "images", auto_download=False)
            self.assertEqual(thumbs, {})


class TestEnsureArchive(unittest.TestCase):
    def setUp(self):
        self._dl, self._dm = images._download, images._drive_manifest
        images._drive_manifest = lambda *a, **k: {}  # no Drive fallback / no network

    def tearDown(self):
        images._download, images._drive_manifest = self._dl, self._dm

    def test_local_archive_used_without_download(self):
        with tempfile.TemporaryDirectory() as d:
            mm = Path(d) / "mmpedia"
            mm.mkdir(parents=True)
            (mm / "Entlist005.tar").write_text("x")
            self.assertEqual(_ensure_archive("Entlist005.tar", mm, {}),
                             mm / "Entlist005.tar")

    def test_zenodo_download_uses_mapped_record(self):
        def fake(url, dest):
            self.assertIn("zenodo.org/records/7855010/files/Entlist096.tar", url)
            dest.write_text("tar")
        images._download = fake
        with tempfile.TemporaryDirectory() as d:
            mm = Path(d) / "mmpedia"
            mm.mkdir(parents=True)
            self.assertEqual(
                _ensure_archive("Entlist096.tar", mm, {"Entlist096.tar": "7855010"}),
                mm / "Entlist096.tar")

    def test_no_source_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            mm = Path(d) / "mmpedia"
            mm.mkdir(parents=True)
            self.assertIsNone(_ensure_archive("Entlist017.tar", mm, {}))

    def test_zenodo_failure_is_non_fatal(self):
        def boom(url, dest):
            raise RuntimeError("HTTP 503 — throttled")  # must skip, not raise
        images._download = boom
        with tempfile.TemporaryDirectory() as d:
            mm = Path(d) / "mmpedia"
            mm.mkdir(parents=True)
            self.assertIsNone(
                _ensure_archive("Entlist096.tar", mm, {"Entlist096.tar": "7855010"}))
            self.assertFalse((mm / "Entlist096.tar.part").exists())


class TestRun(unittest.TestCase):
    def _fixture(self, d: Path, with_mmpedia: bool):
        data = d / "data"
        data.mkdir(parents=True)
        kg = {
            "nodes": [
                {"id": "dbr:Marie_Curie", "label": "Marie Curie",
                 "abstract": "Polish-French physicist.", "types": ["Person", "Scientist"],
                 "image": None},
                {"id": "dbr:Pierre_Curie", "label": "Pierre Curie", "abstract": "x",
                 "types": ["Person"], "image": None},  # available but NOT in focus
                {"id": "dbr:Polonium", "label": "Polonium", "abstract": "",
                 "types": ["ChemicalElement"], "image": None},  # focus but NOT available
            ],
            "edges": [
                {"subject": "dbr:Marie_Curie", "predicate": "dbo:knownFor",
                 "object": "dbr:Polonium", "predicate_label": "knownFor"},
                {"subject": "dbr:Marie_Curie", "predicate": "dbo:spouse",
                 "object": "dbr:Pierre_Curie", "predicate_label": "spouse"},
            ],
        }
        (data / "kg_subset.json").write_text(json.dumps(kg), encoding="utf-8")
        # validated set references Marie (seed) and Polonium (evidence object)
        (data / "validated_questions.json").write_text(json.dumps([{
            "seed_uris": ["dbr:Marie_Curie"],
            "evidence_triples": [{"subject": "dbr:Marie_Curie",
                                  "predicate": "dbo:knownFor", "object": "dbr:Polonium"}],
        }]), encoding="utf-8")
        mm = d / "mmpedia"
        if with_mmpedia:
            _make_png(mm / "Entlist001/Marie Curie/Marie Curie+1.jpg")  # extracted on disk
            (mm / "entity2image.json").write_text(json.dumps({
                "Marie_Curie": ["MMpedia/Entlist001/Marie Curie/Marie Curie+1.jpg"],
                "Pierre_Curie": ["MMpedia/Entlist001/Pierre Curie/Pierre Curie+1.jpg"],
            }), encoding="utf-8")
        else:
            mm.mkdir(parents=True)
        return {"kg_path": data / "kg_subset.json", "mmpedia_dir": mm,
                "images_out": data / "images", "coverage_path": data / "coverage.csv",
                "validated_path": data / "validated_questions.json"}

    def _coverage_rows(self, path: Path):
        with open(path, newline="", encoding="utf-8") as f:
            return {r["entity"]: r for r in csv.DictReader(f)}

    def test_run_fetches_only_focus_but_covers_all(self):
        with tempfile.TemporaryDirectory() as d:
            paths = self._fixture(Path(d), with_mmpedia=True)
            run(auto_download=False, **paths)

            kg = json.loads(paths["kg_path"].read_text(encoding="utf-8"))
            by_id = {n["id"]: n for n in kg["nodes"]}
            # Marie: focus + available -> thumbnail filled
            self.assertEqual(by_id["dbr:Marie_Curie"]["image"], "images/Marie_Curie.jpg")
            # Pierre: available but NOT focus -> not fetched
            self.assertIsNone(by_id["dbr:Pierre_Curie"]["image"])
            # Polonium: focus but NOT available -> nothing
            self.assertIsNone(by_id["dbr:Polonium"]["image"])

            rows = self._coverage_rows(paths["coverage_path"])
            # has_image = MMpedia availability (all nodes), independent of fetch scope
            self.assertEqual(rows["dbr:Marie_Curie"]["has_image"], "True")
            self.assertEqual(rows["dbr:Pierre_Curie"]["has_image"], "True")  # available
            self.assertEqual(rows["dbr:Polonium"]["has_image"], "False")
            self.assertEqual(rows["dbr:Marie_Curie"]["degree"], "2")
            self.assertEqual(rows["dbr:Pierre_Curie"]["n_images"], "1")
            self.assertEqual(rows["dbr:Polonium"]["abstract_len"], "0")

    def test_run_fetch_all_includes_non_focus(self):
        with tempfile.TemporaryDirectory() as d:
            paths = self._fixture(Path(d), with_mmpedia=True)
            # Pierre is available but not in focus; put his image on disk too
            _make_png(paths["mmpedia_dir"] / "Entlist001/Pierre Curie/Pierre Curie+1.jpg")
            run(auto_download=False, fetch_all=True, **paths)

            by_id = {n["id"]: n for n in
                     json.loads(paths["kg_path"].read_text(encoding="utf-8"))["nodes"]}
            self.assertEqual(by_id["dbr:Marie_Curie"]["image"], "images/Marie_Curie.jpg")
            self.assertEqual(by_id["dbr:Pierre_Curie"]["image"], "images/Pierre_Curie.jpg")

    def test_run_skips_gracefully_without_mmpedia(self):
        with tempfile.TemporaryDirectory() as d:
            paths = self._fixture(Path(d), with_mmpedia=False)
            run(auto_download=False, **paths)

            kg = json.loads(paths["kg_path"].read_text(encoding="utf-8"))
            self.assertTrue(all(n["image"] is None for n in kg["nodes"]))
            rows = self._coverage_rows(paths["coverage_path"])
            self.assertTrue(all(r["has_image"] == "False" for r in rows.values()))
            self.assertEqual(len(rows), 3)


if __name__ == "__main__":
    unittest.main()
