import bz2
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data"
DUMPS_DIR = HERE.parent / "dumps"

OBJECT_RE = re.compile(r"^<([^>]+)>\s+<([^>]+)>\s+<([^>]+)>\s+\.")
LITERAL_RE = re.compile(r'^<([^>]+)>\s+<[^>]+>\s+"(.+)"@en\s+\.')


def load_nodes_and_edges():
    triples = json.loads((DATA_DIR / "triples.json").read_text(encoding="utf-8"))
    nodes = set()
    edges = []
    for t in triples:
        nodes.add(t["s"])
        if t["o"].startswith("http://dbpedia.org/"):
            nodes.add(t["o"])
        edges.append({
            "subject": shorten(t["s"]),
            "predicate": shorten(t["p"]),
            "object": shorten(t["o"]),
            "predicate_label": t["p"].rsplit("/", 1)[-1],
        })
    return nodes, edges


def shorten(uri: str) -> str:
    return (uri
            .replace("http://dbpedia.org/resource/", "dbr:")
            .replace("http://dbpedia.org/ontology/", "dbo:")
            .replace("http://dbpedia.org/property/", "dbp:"))


def stream_literals(dump_path: Path, targets: set[str]) -> dict[str, str]:
    out = {}
    with bz2.open(dump_path, "rt", encoding="utf-8") as f:
        for line in f:
            m = LITERAL_RE.match(line.strip())
            if m and m.group(1) in targets:
                out[m.group(1)] = m.group(2)
    return out


def stream_types(dump_path: Path, targets: set[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    with bz2.open(dump_path, "rt", encoding="utf-8") as f:
        for line in f:
            m = OBJECT_RE.match(line.strip())
            if m and m.group(1) in targets:
                local = m.group(3).rsplit("/", 1)[-1]
                out.setdefault(m.group(1), []).append(local)
    return out


# Downloads: http://downloads.dbpedia.org/2016-04/core-i18n/en/
#   labels_en.ttl.bz2          (174M)
#   short_abstracts_en.ttl.bz2 (503M)
#   instance_types_en.ttl.bz2  (41M)
def run() -> None:
    print("loading triples...")
    nodes, edges = load_nodes_and_edges()
    print(f"  {len(nodes)} nodes, {len(edges)} edges")

    labels, abstracts, types = {}, {}, {}

    path = DUMPS_DIR / "labels_en.ttl.bz2"
    if path.exists():
        print("streaming labels...")
        labels = stream_literals(path, nodes)
        print(f"  {len(labels)} labels found")

    path = DUMPS_DIR / "short_abstracts_en.ttl.bz2"
    if path.exists():
        print("streaming abstracts...")
        abstracts = stream_literals(path, nodes)
        print(f"  {len(abstracts)} abstracts found")

    path = DUMPS_DIR / "instance_types_en.ttl.bz2"
    if path.exists():
        print("streaming types...")
        types = stream_types(path, nodes)
        print(f"  {len(types)} entities with types")

    node_list = []
    for uri in sorted(nodes):
        label = labels.get(uri) or uri.rsplit("/", 1)[-1].replace("_", " ")
        node_list.append({
            "id": shorten(uri),
            "label": label,
            "abstract": abstracts.get(uri, ""),
            "types": types.get(uri, []),
            "image": None,
        })

    out = {"nodes": node_list, "edges": edges}
    (DATA_DIR / "kg_subset.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"written: {DATA_DIR / 'kg_subset.json'}")
    print(f"  {len(node_list)} nodes, {len(edges)} edges")


if __name__ == "__main__":
    run()
