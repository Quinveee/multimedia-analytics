# Stage 2 of the pipeline.
# Reads the big DBpedia relation dumps and keeps a triple whenever one of our
# seed entities is the subject or the object, so we also grab the answer
# entities around each seed (one hop out). Writes data/triples.json.

import bz2
import json
import re
from pathlib import Path

from uri_norm import canonical_uri

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data"
DUMPS_DIR = HERE.parent / "dumps"

TRIPLE_RE = re.compile(r"^<([^>]+)>\s+<([^>]+)>\s+<([^>]+)>\s+\.")

# Downloads: http://downloads.dbpedia.org/2016-04/core-i18n/en/
#   mappingbased_objects_en.ttl.bz2  (159M)
#   infobox_properties_en.ttl.bz2    (271M)
# Hop-1 is bidirectional (subject OR object in seeds). 1-hop by design: it
# already retains 88% of gold questions; 2-hop was dropped.
DUMP_FILES = [
    "mappingbased_objects_en.ttl.bz2",
    "infobox_properties_en.ttl.bz2",
]


def load_seeds() -> set[str]:
    uris = json.loads((DATA_DIR / "uris.json").read_text(encoding="utf-8"))
    return {canonical_uri(e) for e in uris["entities"]}


def stream_triples(dump_path: Path, seeds: set[str]) -> list[dict]:
    triples = []
    with bz2.open(dump_path, "rt", encoding="utf-8") as f:
        for line in f:
            m = TRIPLE_RE.match(line.strip())
            if not m:
                continue
            s, p, o = m.group(1), m.group(2), m.group(3)
            if canonical_uri(s) in seeds or canonical_uri(o) in seeds:
                triples.append({"s": s, "p": p, "o": o})
    return triples


def run() -> None:
    seeds = load_seeds()
    print(f"seed entities: {len(seeds)}")

    all_triples = []
    for fname in DUMP_FILES:
        path = DUMPS_DIR / fname
        if not path.exists():
            print(f"missing: {fname} — skip")
            continue
        print(f"streaming {fname}...")
        triples = stream_triples(path, seeds)
        print(f"  {len(triples)} triples matched")
        all_triples.extend(triples)

    out = DATA_DIR / "triples.json"
    out.write_text(json.dumps(all_triples, indent=2), encoding="utf-8")
    print(f"total: {len(all_triples)} triples -> {out}")


if __name__ == "__main__":
    run()
