import bz2
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data"
DUMPS_DIR = HERE.parent / "dumps"

TRIPLE_RE = re.compile(r"^<([^>]+)>\s+<([^>]+)>\s+<([^>]+)>\s+\.")

# Downloads: http://downloads.dbpedia.org/2016-04/core-i18n/en/
#   mappingbased_objects_en.ttl.bz2  (159M)
#   infobox_properties_en.ttl.bz2    (271M)
# TODO: currently 1-hop only (subject in seeds). Needs 2-hop pass for full LC-QuAD coverage.
DUMP_FILES = [
    "mappingbased_objects_en.ttl.bz2",
    "infobox_properties_en.ttl.bz2",
]


def load_entities() -> set[str]:
    uris = json.loads((DATA_DIR / "uris.json").read_text())
    return set(uris["entities"])


def stream_triples(dump_path: Path, entities: set[str]) -> list[dict]:
    triples = []
    with bz2.open(dump_path, "rt", encoding="utf-8") as f:
        for line in f:
            m = TRIPLE_RE.match(line.strip())
            if not m:
                continue
            s, p, o = m.group(1), m.group(2), m.group(3)
            if s in entities:
                triples.append({"s": s, "p": p, "o": o})
    return triples


def main() -> None:
    entities = load_entities()
    print(f"seed entities: {len(entities)}")

    all_triples = []
    for fname in DUMP_FILES:
        path = DUMPS_DIR / fname
        if not path.exists():
            print(f"missing: {fname} — skip")
            continue
        print(f"streaming {fname}...")
        triples = stream_triples(path, entities)
        print(f"  {len(triples)} triples matched")
        all_triples.extend(triples)

    out = DATA_DIR / "triples.json"
    out.write_text(json.dumps(all_triples, indent=2))
    print(f"total: {len(all_triples)} triples → {out}")


if __name__ == "__main__":
    main()
