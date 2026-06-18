import bz2
import json
import re
from pathlib import Path

from rdflib import RDF, URIRef
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.parserutils import CompValue
from rdflib.term import Variable
from tqdm import tqdm

from uri_norm import canonical_uri

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data"
DUMPS_DIR = HERE.parent / "dumps"
QA_DIR = HERE.parent / "qa_dataset"

TYPES_DUMP = "instance_types_en.ttl.bz2"
TYPE_IRI = str(RDF.type)
TRIPLE_RE = re.compile(r"^<([^>]+)>\s+<([^>]+)>\s+<([^>]+)>\s+\.")

# An index is a pair of dicts over canonical URI strings:
#   sp_to_o[(s, p)] -> {o, ...}   (forward lookups + membership; includes rdf:type)
#   po_to_s[(p, o)] -> {s, ...}   (backward lookups; relations only — types never anchor)
Index = tuple[dict, dict]


def shorten(uri: str) -> str:
    """Compact full IRIs to the frontend prefixes (mirrors enrich.shorten, plus rdf:)."""
    return (uri
            .replace("http://dbpedia.org/resource/", "dbr:")
            .replace("http://dbpedia.org/ontology/", "dbo:")
            .replace("http://dbpedia.org/property/", "dbp:")
            .replace("http://www.w3.org/1999/02/22-rdf-syntax-ns#", "rdf:"))


def _u(uri: str) -> URIRef:
    """URIRef in canonical form, so query terms compare equal to index keys."""
    return URIRef(canonical_uri(uri))


def build_index() -> Index:
    """triples.json + rdf:type triples for the subset nodes, all canonicalized."""
    triples = json.loads((DATA_DIR / "triples.json").read_text(encoding="utf-8"))
    sp_to_o: dict[tuple, set] = {}
    po_to_s: dict[tuple, set] = {}
    nodes: set[str] = set()
    for t in triples:
        s, p, o = canonical_uri(t["s"]), canonical_uri(t["p"]), canonical_uri(t["o"])
        sp_to_o.setdefault((s, p), set()).add(o)
        po_to_s.setdefault((p, o), set()).add(s)
        nodes.add(s)
        nodes.add(o)
    print(f"  index: {len(triples)} relation triples, {len(nodes)} nodes")

    type_path = DUMPS_DIR / TYPES_DUMP
    if type_path.exists():
        added = 0
        with bz2.open(type_path, "rt", encoding="utf-8") as f:
            for line in f:
                m = TRIPLE_RE.match(line.strip())
                if not m:
                    continue
                cs = canonical_uri(m.group(1))
                if cs in nodes:
                    sp_to_o.setdefault((cs, TYPE_IRI), set()).add(canonical_uri(m.group(3)))
                    added += 1
        print(f"  index: +{added} rdf:type triples")
    else:
        print(f"  WARNING: {TYPES_DUMP} missing — rdf:type constraints will fail")
    return sp_to_o, po_to_s


def _collect_bgp(node, acc: list) -> None:
    """Recursively gather all BGP triple patterns from a parsed query's algebra."""
    if isinstance(node, CompValue):
        if node.name == "BGP":
            acc.extend(node["triples"])
        for v in node.values():
            _collect_bgp(v, acc)
    elif isinstance(node, (list, tuple)):
        for v in node:
            _collect_bgp(v, acc)


def _to_select_star(query_string: str) -> str:
    """Rewrite any SELECT/COUNT/ASK head to ``SELECT * WHERE { ... }``.

    LC-QuAD's COUNT form (``SELECT DISTINCT COUNT(?uri)``) is non-standard SPARQL
    that rdflib's parser rejects, and ASK has no projection — but we only need
    the WHERE patterns. Assumes no PREFIX header, which holds for LC-QuAD."""
    brace = query_string.find("{")
    return query_string if brace == -1 else "SELECT * WHERE " + query_string[brace:]


def extract_bgp(query_string: str) -> list[tuple]:
    """BGP triple patterns (s, p, o) with URIRefs canonicalized; [] if unparseable."""
    try:
        q = prepareQuery(_to_select_star(query_string))
    except Exception:
        return []
    raw: list = []
    _collect_bgp(q.algebra, raw)
    return [tuple(_u(str(t)) if isinstance(t, URIRef) else t for t in (s, p, o))
            for s, p, o in raw]


def _val(term, binding: dict):
    """Canonical string for a constant/bound term, or None for an unbound variable."""
    if isinstance(term, Variable):
        return binding.get(term)
    return str(term)


def _order(bgp: list[tuple]) -> list[tuple]:
    """Most-anchored patterns first (more bound endpoints), rdf:type patterns last,
    so we start from a seed (few matches) and use type constraints as filters."""
    def rank(pattern):
        s, p, o = pattern
        n_const = sum(isinstance(t, URIRef) for t in (s, o))
        return -n_const, str(p) == TYPE_IRI
    return sorted(bgp, key=rank)


def _apply(pattern: tuple, bindings: list[dict], index: Index) -> list[dict]:
    sp_to_o, po_to_s = index
    s, p, o = pattern
    if isinstance(p, Variable):  # predicate variables don't occur in LC-QuAD
        return []
    pv = str(p)
    out: list[dict] = []
    for b in bindings:
        sv, ov = _val(s, b), _val(o, b)
        if sv is not None and ov is not None:           # fully bound -> membership
            if ov in sp_to_o.get((sv, pv), ()):
                out.append(b)
        elif sv is not None:                            # object is the open variable
            for c in sp_to_o.get((sv, pv), ()):
                out.append({**b, o: c})
        elif ov is not None:                            # subject is the open variable
            for c in po_to_s.get((pv, ov), ()):
                out.append({**b, s: c})
        # both open: unanchored under this ordering -> contributes nothing
    return out


def _solve(bgp: list[tuple], index: Index) -> list[dict]:
    bindings = [{}]
    for pattern in _order(bgp):
        bindings = _apply(pattern, bindings, index)
        if not bindings:
            return []
    return bindings


def _evidence(bgp: list[tuple], solutions: list[dict]) -> list[dict]:
    evidence, seen = [], set()
    for b in solutions:
        for s, p, o in bgp:
            triple = tuple(shorten(_val(t, b) or str(t)) for t in (s, p, o))
            if triple not in seen:
                seen.add(triple)
                evidence.append({"subject": triple[0],
                                 "predicate": triple[1],
                                 "object": triple[2]})
    return evidence


def validate_question(index: Index, query_string: str) -> list[dict] | None:
    """Return evidence triples (shortened) if the query is non-empty, else None."""
    bgp = extract_bgp(query_string)
    if not bgp:
        return None
    solutions = _solve(bgp, index)
    return _evidence(bgp, solutions) if solutions else None


def _load_questions() -> list[dict]:
    out = []
    for fname in ("train-data.json", "test-data.json"):
        out.extend(json.loads((QA_DIR / fname).read_text(encoding="utf-8")))
    return out


def run() -> None:
    print("building triple index...")
    index = build_index()

    seeds_by_id = json.loads((DATA_DIR / "uris.json").read_text(encoding="utf-8"))["per_question"]
    questions = _load_questions()
    print(f"validating {len(questions)} gold queries...")

    validated, unparseable = [], 0
    for q in tqdm(questions, unit="q"):
        qid, gold = q["_id"], q.get("sparql_query", "")
        bgp = extract_bgp(gold)
        if not bgp:
            unparseable += 1
            continue
        solutions = _solve(bgp, index)
        if not solutions:
            continue
        seeds = seeds_by_id.get(qid, {}).get("entities", [])
        validated.append({
            "id": qid,
            "question": q.get("corrected_question", ""),
            "gold_sparql": gold,
            "seed_uris": [shorten(s) for s in seeds],
            "evidence_triples": _evidence(bgp, solutions),
        })

    out = DATA_DIR / "validated_questions.json"
    out.write_text(json.dumps(validated, indent=2), encoding="utf-8")

    total = len(questions)
    print(f"\nretained {len(validated)} / {total} "
          f"({100 * len(validated) / total:.1f}%); {unparseable} unparseable queries")
    print(f"written: {out}")
    print("\n--- 3 sample validated entries ---")
    for entry in validated[:3]:
        print(json.dumps(entry, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    run()
