"""Offline pipeline orchestrator.

Runs the full preprocessing pipeline end to end:

  1. extract_uris   — seeds & predicates from each gold SPARQL  -> data/uris.json
  2. neighbourhood  — bidirectional hop-1 over the dumps        -> data/triples.json
  3. enrich         — labels/abstracts/types + shortened graph  -> data/kg_subset.json
  4. validate       — re-run gold queries, keep non-empty       -> data/validated_questions.json

Before running, it verifies the DBpedia 2016-04 dump archives are present in
dumps/ and downloads any that are missing. Each phase is logged with timing.

Usage (from offline/):  python main.py
"""
import importlib
import logging
import sys
import time
from pathlib import Path

import requests
from tqdm import tqdm

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE / "scripts"
DUMPS_DIR = HERE / "dumps"

# DBpedia 2016-04 English dumps. Pinned version: LC-QuAD 1.0
DUMP_BASE = "http://downloads.dbpedia.org/2016-04/core-i18n/en/"
REQUIRED_DUMPS = [
    "mappingbased_objects_en.ttl.bz2",   # 2: object relations
    "infobox_properties_en.ttl.bz2",     # 2: infobox relations
    "labels_en.ttl.bz2",                 # 3: rdfs:label
    "short_abstracts_en.ttl.bz2",        # 3: abstracts
    "instance_types_en.ttl.bz2",         # 3 + 4: rdf:type
]

STAGES = [
    ("extract_uris", "extract URIs from gold SPARQL"),
    ("neighbourhood", "build bidirectional hop-1 neighbourhood"),
    ("enrich", "enrich nodes (labels / abstracts / types)"),
    ("validate", "validate against gold queries"),
    ("images", "attach MMpedia thumbnails + coverage.csv"),
]

log = logging.getLogger("pipeline")


def _download(fname: str) -> None:
    url = DUMP_BASE + fname
    dest = DUMPS_DIR / fname
    tmp = dest.with_name(dest.name + ".part")
    log.info("downloading %s", url)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        with open(tmp, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, desc=fname
        ) as bar:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                bar.update(len(chunk))
    tmp.replace(dest)
    log.info("saved %s (%.0f MB)", fname, dest.stat().st_size / 1e6)


def ensure_dumps() -> None:
    """Download any required dump archive that is missing or empty."""
    DUMPS_DIR.mkdir(parents=True, exist_ok=True)
    missing = [f for f in REQUIRED_DUMPS
               if not (DUMPS_DIR / f).exists() or (DUMPS_DIR / f).stat().st_size == 0]
    if not missing:
        log.info("all %d dump archives present in %s", len(REQUIRED_DUMPS), DUMPS_DIR)
        return
    log.info("%d dump archive(s) missing: %s", len(missing), ", ".join(missing))
    for fname in missing:
        _download(fname)


def run_pipeline() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    log.info("=== offline pipeline start ===")
    started = time.time()

    log.info("--- phase 0/%d: verify dump archives ---", len(STAGES))
    ensure_dumps()

    sys.path.insert(0, str(SCRIPTS))  # stage modules import each other by bare name
    for i, (module_name, label) in enumerate(STAGES, 1):
        log.info("--- phase %d/%d: %s ---", i, len(STAGES), label)
        phase_started = time.time()
        importlib.import_module(module_name).run()
        log.info("phase %d/%d done in %.1fs", i, len(STAGES), time.time() - phase_started)

    log.info("=== pipeline complete in %.1fs ===", time.time() - started)


if __name__ == "__main__":
    run_pipeline()
