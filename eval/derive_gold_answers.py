#!/usr/bin/env python3
"""Derive gold answers for the validated questions (eval step 1).

`validated_questions.json` stores each question's gold SPARQL and the
`evidence_triples` that satisfy it, but NOT the answer itself — `validate.py`
discards the solution bindings. The correctness metric needs the answer, so we
recover it here, fully offline: re-solve the gold query's basic graph pattern
over the question's own `evidence_triples` and read off the binding of the
answer variable (`?uri`).

This needs no DBpedia dumps and no redirect table — the evidence triples already
include any rdf:type constraints, and URIs are matched with the same
shorten(unquote(...)) rule the offline pipeline used.

Writes offline/data/validated_questions_gold.json (a superset of the input):
adds per question:
  answer_type   "select" | "count" | "ask"
  answer_var    projection variable name (usually "uri"), or null for ASK
  gold_answers  [{uri, label}, ...]   (entities bound to the answer variable)
  gold_count    int                   (count questions: number of distinct answers)
  gold_boolean  true                  (ask questions: validated ⇒ a solution exists)
"""
import json
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
VQ = ROOT / "offline" / "data" / "validated_questions.json"
KG = ROOT / "offline" / "data" / "kg_subset.db"
OUT = ROOT / "offline" / "data" / "validated_questions_gold.json"

PREFIXES = [
    ("http://dbpedia.org/resource/", "dbr:"),
    ("http://dbpedia.org/ontology/", "dbo:"),
    ("http://dbpedia.org/property/", "dbp:"),
    ("http://www.w3.org/1999/02/22-rdf-syntax-ns#", "rdf:"),
]

_TERM = r"(<[^>]+>|\?\w+)"
_TRIPLE = re.compile(_TERM + r"\s+" + _TERM + r"\s+" + _TERM)


def shorten(uri: str) -> str:
    u = unquote(uri.strip())
    for full, pre in PREFIXES:
        u = u.replace(full, pre)
    return u


def parse_term(tok: str):
    """('uri', shortened) for <...>, ('var', name) for ?x."""
    if tok.startswith("?"):
        return ("var", tok[1:])
    return ("uri", shorten(tok[1:-1]))


def query_type_and_var(sparql: str):
    """(answer_type, answer_var) — answer_var is None for ASK."""
    if sparql.lstrip().upper().startswith("ASK"):
        return "ask", None
    m = re.search(r"SELECT\s+(?:DISTINCT\s+)?(COUNT\s*\(\s*)?\??(\w+)", sparql, re.I)
    var = m.group(2) if m else "uri"
    return ("count" if (m and m.group(1)) else "select"), var


def extract_bgp(sparql: str):
    brace = sparql.find("{")
    where = sparql[brace:] if brace != -1 else sparql
    return [(parse_term(s), parse_term(p), parse_term(o)) for s, p, o in _TRIPLE.findall(where)]


def _bind(term, b):
    """Resolve a ('var', name) term to ('uri', value) if already bound."""
    kind, x = term
    return ("uri", b[x]) if (kind == "var" and x in b) else term


def solve(patterns, evidence):
    """All variable bindings satisfying every pattern against the evidence.

    Indexed + constraint-ordered so it stays linear even when one predicate has
    tens of thousands of evidence triples: patterns with the most constants run
    first (binding the shared variable early), a fully-ground pattern is then an
    O(1) set-membership test, and a partially-ground pattern only scans the
    triples sharing its predicate (predicates are always constants in LC-QuAD).
    """
    from collections import defaultdict

    ev_set = set(evidence)
    by_pred = defaultdict(list)
    for t in evidence:
        by_pred[t[1]].append(t)

    patterns = sorted(patterns, key=lambda pat: sum(t[0] == "uri" for t in pat), reverse=True)

    solutions = [{}]
    for s, p, o in patterns:
        nxt = []
        for b in solutions:
            gs, gp, go = _bind(s, b), _bind(p, b), _bind(o, b)
            if gs[0] == gp[0] == go[0] == "uri":  # fully ground -> O(1) membership
                if (gs[1], gp[1], go[1]) in ev_set:
                    nxt.append(b)
                continue
            cands = by_pred.get(gp[1], ()) if gp[0] == "uri" else evidence
            for triple in cands:
                nb, ok = dict(b), True
                for (kind, x), val in zip((gs, gp, go), triple):
                    if kind == "uri":
                        if x != val:
                            ok = False
                            break
                    elif x in nb:
                        if nb[x] != val:
                            ok = False
                            break
                    else:
                        nb[x] = val
                if ok:
                    nxt.append(nb)
        solutions = nxt
        if not solutions:
            break
    return solutions


def local_name(uri: str) -> str:
    return uri.split(":", 1)[-1].replace("_", " ")


def load_labels(uris: set[str]) -> dict:
    if not uris or not KG.exists():
        return {}
    con = sqlite3.connect(str(KG))
    labels = {}
    uris = list(uris)
    for i in range(0, len(uris), 900):
        chunk = uris[i : i + 900]
        q = f"SELECT id, label FROM nodes WHERE id IN ({','.join('?' * len(chunk))})"
        labels.update({r[0]: r[1] for r in con.execute(q, chunk) if r[1]})
    con.close()
    return labels


def main():
    questions = json.loads(VQ.read_text())
    print(f"deriving gold answers for {len(questions)} questions ...")

    derived = []
    all_uris = set()
    for i, q in enumerate(questions):
        if i and i % 1000 == 0:
            print(f"  ... {i}/{len(questions)}")
        atype, var = query_type_and_var(q["gold_sparql"])
        entry = {**q, "answer_type": atype, "answer_var": var}
        if atype == "ask":
            entry["gold_boolean"] = True
            entry["gold_answers"] = []
        else:
            evidence = [
                (t["subject"], t["predicate"], t["object"]) for t in q["evidence_triples"]
            ]
            sols = solve(extract_bgp(q["gold_sparql"]), evidence)
            answers = sorted({b[var] for b in sols if var in b})
            all_uris.update(answers)
            entry["gold_answers"] = [{"uri": a} for a in answers]
            if atype == "count":
                entry["gold_count"] = len(answers)
        derived.append(entry)

    # attach human-readable labels (KG label, else URI local name)
    labels = load_labels(all_uris)
    for e in derived:
        for a in e["gold_answers"]:
            a["label"] = labels.get(a["uri"]) or local_name(a["uri"])

    OUT.write_text(json.dumps(derived, indent=2, ensure_ascii=False))

    # ── report ──
    from collections import Counter

    by_type = Counter(e["answer_type"] for e in derived)
    sel = [e for e in derived if e["answer_type"] in ("select", "count")]
    got = [e for e in sel if e["gold_answers"]]
    multi = [e for e in sel if len(e["gold_answers"]) > 1]
    print(f"\nby type: {dict(by_type)}")
    print(
        f"select/count with >=1 gold answer: {len(got)}/{len(sel)} "
        f"({100 * len(got) / max(len(sel),1):.1f}%); multi-answer: {len(multi)}"
    )
    miss = [e for e in sel if not e["gold_answers"]]
    print(f"select/count with NO derived answer: {len(miss)}")
    print(f"\nwritten: {OUT}")
    print("\n--- samples ---")
    for e in derived[:6]:
        ga = e["gold_answers"]
        show = ", ".join(a["label"] for a in ga[:4]) + (" …" if len(ga) > 4 else "")
        extra = f" count={e.get('gold_count')}" if e["answer_type"] == "count" else ""
        print(f"[{e['id']}] ({e['answer_type']}{extra}) {e['question']}")
        print(f"      gold: {show or '(none)'}")


if __name__ == "__main__":
    main()
