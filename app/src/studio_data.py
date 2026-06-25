"""Data provider for the KG Grounding Studio UI.

The UI never talks to the pipeline directly. It consumes a single normalised
"view model" (see ``real_view_model``) so the layout and callbacks stay
decoupled from the pipeline. ``get_result`` runs the live ``run_pipeline`` and
maps its result onto the view model; on failure the exception propagates (no
fallback).
"""

from __future__ import annotations

import os
import re

from src.pipeline import run_pipeline

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
#  Public entry point
# ══════════════════════════════════════════════════════════════════════════════
async def get_result(question: str, model: str, dataset: str = "DBpedia",
                     verifier: str = None, subgraph: dict = None) -> dict:
    """Return a view model for ``question`` from the live pipeline. ``model`` is
    an OpenRouter model id (e.g. "openai/gpt-4o"). ``verifier`` is "llm"|"nli".
    ``subgraph`` (if given) re-runs against a pre-filtered subgraph (masking).

    No fallback: if the pipeline fails (KG / Spotlight / LLM unavailable, or any
    runtime error) the exception propagates and the request fails loudly.
    """
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
