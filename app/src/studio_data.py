"""Data provider for the KG Grounding Studio UI.

The UI never talks to the pipeline directly. It consumes a single normalised
"view model" (see ``build_view_model``) so the layout/callbacks are identical
whether the data comes from the live pipeline or canned demo data.

Resolution order for ``get_result``:
  1. MOCK env / mock=True            -> canned Marie-Curie data
  2. live ``run_pipeline``           -> mapped to the view model
  3. any failure (KG / Spotlight /   -> canned data (so the UI always renders)
     LLM not reachable yet)
"""

from __future__ import annotations

import os
import re

# ── kind → palette key (mirrors the design's `pal`/`stColor`) ──────────────────
KIND_COLORS = {
    "person": ("#4263eb", "#748ffc"),
    "element": ("#0c8599", "#3bc9db"),
    "award": ("#e8590c", "#f59f00"),
    "place": ("#2f9e44", "#69db7c"),
    "org": ("#7048e8", "#b197fc"),
    "concept": ("#868e96", "#ced4da"),
}
NODE_BORDER = {k: v[0] for k, v in KIND_COLORS.items()}


# ══════════════════════════════════════════════════════════════════════════════
#  Real-pipeline → view model mapping
# ══════════════════════════════════════════════════════════════════════════════
_CITE_RE = re.compile(r"\s*\[T\d+\]?")


def _kind_of(types: list[str]) -> str:
    """Best-effort DBpedia type list → a palette kind."""
    blob = " ".join(types).lower()
    if "person" in blob or "agent" in blob:
        return "person"
    if "place" in blob or "location" in blob or "settlement" in blob or "country" in blob or "city" in blob:
        return "place"
    if "award" in blob or "prize" in blob:
        return "award"
    if "element" in blob or "chemical" in blob or "substance" in blob:
        return "element"
    if "organisation" in blob or "organization" in blob or "company" in blob or "university" in blob:
        return "org"
    return "concept"


def _glyph_of(label: str) -> str:
    parts = [p for p in re.split(r"[\s_]+", label.strip()) if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def _short_uri(uri: str) -> str:
    return uri.split(":")[-1].split("/")[-1]


def real_view_model(result: dict, model_label: str) -> dict:
    """Map a ``run_pipeline`` result dict onto the UI view model."""
    sub = result.get("subgraph", {"nodes": [], "edges": []})
    triples = result.get("triples", [])

    # nodes: order by retrieval depth so the trace reveals seeds first
    raw_nodes = sorted(sub["nodes"], key=lambda n: n.get("_depth", 99))
    nodes = []
    for n in raw_nodes:
        nodes.append({
            "id": n["id"],
            "label": n.get("label") or n["id"],
            "kind": _kind_of(n.get("types") or []),
            "glyph": _glyph_of(n.get("label") or n["id"]),
            "has_image": bool(n.get("image")),
            "image": n.get("image"),  # relative path under offline/data
            "big": n.get("_depth", 99) == 0,
        })
    edges = [
        {"source": e["subject"], "target": e["object"], "label": e.get("predicate_label") or e["predicate"]}
        for e in sub["edges"]
    ]

    # grounded answer → tokens + citation map, driven by claim char-spans.
    # A sentence may draw on several facts ("... Ann Lewis [T1][T12].") — emit one
    # citation chip per cited triple so every fact is shown and individually
    # inspectable, not just the first. (The parser collects all [T#] per sentence;
    # the mapping below must not collapse them back to one.)
    answer = result.get("answer_grounded", "")
    claims = sorted(result.get("claims_grounded", []), key=lambda c: c.get("start") or 0)
    tokens: list[dict] = []
    citations: dict = {}
    cursor = 0
    cite_i = 0      # unique id counter across all citation chips
    n_claims = 0    # grounded (cited) claims — drives the "grounded N claims" summary
    for c in claims:
        s, e = c.get("start"), c.get("end")
        if s is None or e is None:
            continue
        if s > cursor:
            tokens.append({"t": answer[cursor:s]})
        text = _CITE_RE.sub("", answer[s:e]).strip()
        cited = c.get("cited_triples") or []
        label = c.get("label", "supported")
        if cited and text:
            n_claims += 1
            cids = []
            for t_idx in cited:
                cite_i += 1
                cid = f"C{cite_i}"
                t = triples[t_idx - 1] if 1 <= t_idx <= len(triples) else None
                # point the citation at the object node and remember the backing edge
                obj = t["object"] if t else (nodes[0]["id"] if nodes else "")
                citations[cid] = {
                    "num": t_idx,   # the [T#] shown as the citation marker
                    "node": obj,
                    "triple": (f"{t['subject_label']} — {t['predicate_label']} — {t['object_label']}"
                               if t else text),
                    # subject —predicate→ object, for the evidence card's arrow form
                    "s_label": t["subject_label"] if t else "",
                    "p_label": t["predicate_label"] if t else "",
                    "o_label": t["object_label"] if t else text,
                    "src": "Knowledge graph",
                    "edges": [(t["subject"], t["object"])] if t else [],
                    "label": label,
                }
                cids.append(cid)
            tokens.append({"t": text, "cites": cids})
        elif text:
            tokens.append({"t": text})
        cursor = e
    if cursor < len(answer):
        tokens.append({"t": answer[cursor:]})

    # entity-linking chips
    link_chips = [
        {"label": ent.get("surface_form", ""), "qid": _short_uri(ent.get("uri", ""))}
        for ent in result.get("entities", [])
    ]

    def claim_row(c):
        label = c.get("label", "unverifiable")
        row = {"t": c.get("claim", ""), "label": label, "ok": label == "supported"}
        if label != "supported":
            row["why"] = f"{label} — not directly supported by a KG triple"
        return row

    closed = [claim_row(c) for c in result.get("claims_closed", [])]
    grounded = []
    gi = 0
    for c in claims:
        label = c.get("label", "unverifiable")
        row = {"t": c.get("claim", ""), "label": label, "ok": label == "supported"}
        if c.get("cited_triples"):
            gi += 1
            row["c"] = f"C{gi}"
        grounded.append(row)

    return {
        "question": result.get("question", ""),
        "model_label": model_label,
        "source": "live",
        # no retrieved triples → the answer could not be grounded
        "has_triples": bool(result.get("triples")),
        "abstained": bool(result.get("abstained")),
        "link_chips": link_chips,
        "retrieved": [n["id"] for n in nodes],
        "nodes": nodes,
        "edges": edges,
        "tokens": tokens or [{"t": answer}],
        "citations": citations,
        "closed_claims": closed,
        "grounded_claims": grounded,
        "counts": {
            "entities": len(nodes),
            "mentions": len(link_chips),
            "claims": n_claims,
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Canned demo (MOCK=true) — renders the full grounded-answer UI with no backend,
#  so the citation/evidence frontend can be inspected without Spotlight + LLM.
# ══════════════════════════════════════════════════════════════════════════════
def _demo_result() -> dict:
    """A canned pipeline result that exercises the citation rendering: a
    multi-fact supported sentence ([T1][T12]), a second multi-fact sentence, and
    a single-fact *inferred* sentence — so every evidence-cluster state shows."""
    def node(nid, label, types, depth):
        return {"id": nid, "label": label, "types": types, "image": None, "_depth": depth}

    nodes = [
        node("billclinton", "Bill Clinton", ["Person", "OfficeHolder"], 0),
        node("algore_camp", "Al Gore presidential campaign, 2000", ["Organisation"], 1),
        node("algore", "Al Gore", ["Person", "OfficeHolder"], 1),
        node("annlewis", "Ann Lewis", ["Person"], 1),
        node("demparty", "Democratic Party (United States)", ["Organisation", "PoliticalParty"], 2),
        node("barneyfrank", "Barney Frank", ["Person"], 2),
        node("whcomms", "White House Communications Director", ["Office"], 2),
        node("lieberman", "Joe Lieberman", ["Person"], 2),
    ]

    def tr(s, sl, pl, o, ol):
        return {"subject": s, "subject_label": sl, "predicate": pl.replace(" ", ""),
                "predicate_label": pl, "object": o, "object_label": ol}

    # T1..T12 — the answer cites T1, T3, T5, T9, T12; the rest flesh out the graph
    triples = [
        tr("algore_camp", "Al Gore presidential campaign, 2000", "incumbent", "billclinton", "Bill Clinton"),       # T1
        tr("algore_camp", "Al Gore presidential campaign, 2000", "running mate", "lieberman", "Joe Lieberman"),     # T2
        tr("algore_camp", "Al Gore presidential campaign, 2000", "candidate", "algore", "Al Gore"),                 # T3
        tr("algore_camp", "Al Gore presidential campaign, 2000", "party", "demparty", "Democratic Party (United States)"),  # T4
        tr("algore", "Al Gore", "party", "demparty", "Democratic Party (United States)"),                           # T5
        tr("algore", "Al Gore", "office", "billclinton", "Bill Clinton"),                                           # T6
        tr("billclinton", "Bill Clinton", "party", "demparty", "Democratic Party (United States)"),                 # T7
        tr("lieberman", "Joe Lieberman", "party", "demparty", "Democratic Party (United States)"),                  # T8
        tr("annlewis", "Ann Lewis", "relative", "barneyfrank", "Barney Frank"),                                     # T9
        tr("annlewis", "Ann Lewis", "office", "whcomms", "White House Communications Director"),                    # T10
        tr("billclinton", "Bill Clinton", "running mate", "algore", "Al Gore"),                                     # T11
        tr("annlewis", "Ann Lewis", "president", "billclinton", "Bill Clinton"),                                    # T12
    ]

    edges = [{"subject": t["subject"], "object": t["object"],
              "predicate": t["predicate"], "predicate_label": t["predicate_label"]} for t in triples]

    answer = (
        "Bill Clinton was the incumbent during Al Gore's 2000 presidential campaign, "
        "and Ann Lewis served under him in the White House [T1][T12]. "
        "Al Gore ran as the candidate of the Democratic Party in that election [T3][T5]. "
        "Ann Lewis is also reported to be a relative of Barney Frank [T9]."
    )
    # spans + cited_triples come from the real parser; we only attach labels
    from src.services.llm import parse_claims
    parsed = parse_claims(answer)
    labels = ["supported", "supported", "inferred"]
    claims_grounded = [{**c, "label": labels[i] if i < len(labels) else "supported"}
                       for i, c in enumerate(parsed)]

    claims_closed = [
        {"claim": "Bill Clinton was the incumbent during Al Gore's 2000 campaign.", "label": "supported"},
        {"claim": "Al Gore won the 2000 presidential election.", "label": "unverifiable"},
        {"claim": "Ann Lewis served as White House Press Secretary.", "label": "inferred"},
    ]
    entities = [
        {"surface_form": "Al Gore presidential campaign, 2000", "uri": "dbr:Al_Gore_presidential_campaign,_2000"},
        {"surface_form": "Ann Lewis", "uri": "dbr:Ann_Lewis"},
        {"surface_form": "Bill Clinton", "uri": "dbr:Bill_Clinton"},
    ]
    return {
        "question": "Who was the incumbent of the Al Gore presidential campaign, 2000, "
                    "and who was the president associated with Ann Lewis?",
        "answer_model": "openai/gpt-5 (demo)",
        "answer_grounded": answer,
        "abstained": False,
        "triples": triples,
        "subgraph": {"nodes": nodes, "edges": edges},
        "claims_grounded": claims_grounded,
        "claims_closed": claims_closed,
        "entities": entities,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Public entry point
# ══════════════════════════════════════════════════════════════════════════════
async def get_result(question: str, model: str, dataset: str = "Wikidata-MM",
                     verifier: str = None, subgraph: dict = None) -> dict:
    """Return a view model for ``question`` from the live pipeline. ``model`` is
    an OpenRouter model id (e.g. "openai/gpt-4o"). ``verifier`` is "llm"|"nli".
    ``subgraph`` (if given) re-runs against a pre-filtered subgraph (masking).

    With ``MOCK=true`` a canned demo result is returned instead, so the UI (and
    in particular the citation/evidence rendering) can be inspected with no KG /
    Spotlight / LLM backend. Otherwise: no fallback — if the pipeline fails the
    exception propagates and the request fails loudly.
    """
    from src import config

    if config.MOCK:
        vm = real_view_model(_demo_result(), f"{model} · {dataset}")
        vm["context"] = {"question": question, "model": model, "dataset": dataset,
                         "verifier": verifier, "subgraph": vm.get("_raw_subgraph")}
        return vm

    from src.pipeline import run_pipeline

    result = await run_pipeline(question, answer_model=model, subgraph=subgraph, verifier=verifier)
    vm = real_view_model(result, f"{result.get('answer_model', model)} · {dataset}")
    # context for re-runs (masking): keep the raw subgraph + the call params
    vm["context"] = {
        "question": question, "model": model, "dataset": dataset, "verifier": verifier,
        "subgraph": result.get("subgraph"),
    }
    return vm


# ── OpenRouter model catalogue (for the searchable dropdown) ───────────────────
import json
import urllib.request

_MODELS_CACHE = None


def _accepts_text_and_image(m: dict) -> bool:
    """True if the model's input modalities include both text and image (vision)."""
    mods = (m.get("architecture") or {}).get("input_modalities") or []
    return "text" in mods and "image" in mods


def fetch_models() -> list[dict]:
    """OpenRouter model catalogue as Dash dropdown options ({label, value}),
    sorted by name. Restricted to multimodal models (input modalities ⊇
    {text, image}) since the pipeline sends entity images. Cached. No fallback:
    a fetch failure (or an empty filtered list) raises."""
    global _MODELS_CACHE
    if _MODELS_CACHE is not None:
        return _MODELS_CACHE
    key = os.getenv("OPENROUTER_API_KEY", "")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {key}"} if key else {},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        models = json.loads(r.read())["data"]
    options = sorted(
        ({"label": m.get("name") or m["id"], "value": m["id"]}
         for m in models if _accepts_text_and_image(m)),
        key=lambda o: o["label"].lower(),
    )
    if not options:
        raise ValueError("OpenRouter returned no text+image models")
    print(f"[studio] loaded {len(options)} multimodal (text+image) OpenRouter models")
    _MODELS_CACHE = options
    return options
