#!/usr/bin/env python3
"""Quantitative evaluation: grounded vs. closed-book (eval step 2).

For each validated question we generate a closed-book and a KG-grounded answer
with the same model and identical retrieved context (only the grounding differs),
then score both. Entity linking is bypassed: the context is built from the gold
`seed_uris`, so we measure grounding in isolation, not the entity linker. The
generation / parsing / verification use the exact same functions as the live
pipeline.

Metrics per (question, model):
  correctness        does the answer contain the gold answer? (select/count)
  hallucination H    share of claims the verifier marks unverifiable
  ΔH                 H_closed - H_grounded (the headline)
  abstention         did the grounded answer decline (and was that correct)?
  citation precision share of cited grounded claims the verifier confirms
  evidence recall@k  share of gold relational evidence in the retrieved [T#] list
  R+                 was any gold evidence retrieved (the key stratifier)

Outputs (eval/results/):
  raw.jsonl          one row per (question, model), both conditions, all counts
  summary.csv        aggregates per (model, condition) + paired deltas
  by_stratum.csv     metrics split by R+ / R-

Needs OPENROUTER_API_KEY in .env (config routes models through OpenRouter).
Usage:
  python3 eval/run_eval.py --n 30
  python3 eval/run_eval.py --ids 2653 93 485 --models openai/gpt-5-nano
"""
import argparse
import asyncio
import csv
import json
import os
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("KG_PATH", str(ROOT / "offline" / "data" / "kg_subset.db"))

from src import config  # noqa: E402
from src.services.kg import KG, rank_triples, verbalise_triples  # noqa: E402
from src.services.llm import (  # noqa: E402
    answer_closed,
    answer_grounded,
    parse_claims,
    parse_sentences,
)
from src.services.verifier import verify_claims  # noqa: E402
from src.pipeline import ABSTAIN_MARKER  # noqa: E402

GOLD = ROOT / "offline" / "data" / "validated_questions_gold.json"
RESULTS = ROOT / "eval" / "results"

# locked study config
LOCKED_MODELS = [
    "qwen/qwen3-8b", "qwen/qwen3-14b", "qwen/qwen3-32b",   # all-dense Qwen3 size sweep
    "openai/gpt-5-mini", "google/gemini-2.5-flash",        # frontier (table only)
]
MODEL_PARAMS = {  # billions; for the Qwen size-axis plot (frontier excluded)
    "qwen/qwen3-8b": 8, "qwen/qwen3-14b": 14, "qwen/qwen3-32b": 32,
}


# ── text normalisation + correctness ─────────────────────────────────────────
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _local(uri: str) -> str:
    return uri.split(":", 1)[-1].replace("_", " ")


def gold_surfaces(entry: dict) -> set[str]:
    surf = set()
    for a in entry["gold_answers"]:
        for cand in (a.get("label"), _local(a["uri"])):
            n = norm(cand or "")
            # strip a trailing parenthetical qualifier, e.g. "A Clockwork Orange (film)"
            n2 = norm(re.sub(r"\(.*?\)", "", cand or ""))
            surf.update(x for x in (n, n2) if x)
    return surf


def _contains(answer_norm: str, surface: str) -> bool:
    return re.search(rf"(?:^| ){re.escape(surface)}(?:$| )", answer_norm) is not None


def correctness(answer: str, entry: dict):
    """1/0 for select (>=1 gold surface present) or count (gold number present); None for ask."""
    at = entry["answer_type"]
    if at == "ask":
        return None
    if at == "count":
        gc = entry.get("gold_count")
        return int(bool(re.search(rf"(?<!\d){gc}(?!\d)", answer))) if gc is not None else None
    na = norm(answer)
    surfs = gold_surfaces(entry)
    return int(any(_contains(na, s) for s in surfs))


# ── claim / citation / retrieval metrics ─────────────────────────────────────
def claim_stats(claims: list[dict]) -> dict:
    n = len(claims)
    c = Counter(x["label"] for x in claims)
    nu = c.get("unverifiable", 0)
    return {
        "n": n,
        "supported": c.get("supported", 0),
        "inferred": c.get("inferred", 0),
        "unverifiable": nu,
        "H": (nu / n) if n else 0.0,
        "any_halluc": int(nu > 0),
    }


def citation_precision(claims: list[dict]):
    cited = [x for x in claims if x.get("cited_triples")]
    if not cited:
        return None, 0
    return sum(x["label"] == "supported" for x in cited) / len(cited), len(cited)


def evidence_recall(entry: dict, ranked: list[dict]):
    """(recall@k, R+) over gold *relational* evidence (rdf:type constraints excluded:
    types live in the nodes table, not as retrievable edges)."""
    gold = {
        (t["subject"], t["predicate"], t["object"])
        for t in entry["evidence_triples"]
        if t["predicate"] != "rdf:type"
    }
    if not gold:
        return None, None
    got = {(t["subject"], t["predicate"], t["object"]) for t in ranked}
    hit = len(gold & got)
    return hit / len(gold), int(hit > 0)


GOLD_CAP = 60  # max gold evidence triples in the verifier prompt; larger sets are flagged


def _pretty(uri: str) -> str:
    local = uri.split(":", 1)[-1] if ":" in uri else uri
    return local.replace("_", " ").strip()


def verbalise_gold(evidence_triples: list[dict]) -> str:
    """Gold evidence as numbered [T#] lines, mirroring the retrieved-triple format
    so the verifier prompt is identical — only the reference corpus differs."""
    return "\n".join(
        f"[T{i + 1}] {_pretty(t['subject'])} {_pretty(t['predicate'])} {_pretty(t['object'])}"
        for i, t in enumerate(evidence_triples)
    )


# ── per-question evaluation (pipeline core, seeded from gold, Spotlight skipped) ─
async def eval_question(entry: dict, model: str, verifier: str, sem: asyncio.Semaphore,
                        images: bool = False) -> dict:
    async with sem:
        q = entry["question"]
        subgraph = KG.get_subgraph(entry["seed_uris"], k=config.KG_HOP)
        triples = rank_triples(subgraph, q)
        triples_prompt = verbalise_triples(subgraph, q)

        image_paths = []
        if images:
            kg_dir = config.KG_PATH.parent.resolve()
            seeds = set(entry["seed_uris"])
            image_paths = [
                str(kg_dir / n["image"])
                for n in subgraph["nodes"]
                if n.get("image") and n["id"] in seeds
            ]

        # closed + grounded answers (same model, only context differs)
        tasks = [answer_closed(q, model)]
        if triples_prompt:
            tasks.append(answer_grounded(q, triples_prompt, model, image_paths or None))
        answers = await asyncio.gather(*tasks)
        closed = answers[0]
        grounded = answers[1] if triples_prompt else closed
        if not closed.strip() or not grounded.strip():
            raise ValueError("empty model response (likely content filter)")
        abstained = bool(triples_prompt) and ABSTAIN_MARKER in grounded.lower()

        claims_grounded, claims_closed = await asyncio.gather(
            verify_claims([] if abstained else parse_claims(grounded), triples_prompt, verifier=verifier),
            verify_claims(parse_sentences(closed), triples_prompt, True, verifier=verifier),
        )

        # gold-based pass: same claims, gold evidence triples as the reference corpus
        gold_capped = len(entry["evidence_triples"]) > GOLD_CAP
        gold_prompt = verbalise_gold(entry["evidence_triples"][:GOLD_CAP])
        gclaims_grounded, gclaims_closed = await asyncio.gather(
            verify_claims(
                [] if abstained else [{**c, "cited_triples": []} for c in parse_claims(grounded)],
                gold_prompt, True, verifier=verifier),
            verify_claims(parse_sentences(closed), gold_prompt, True, verifier=verifier),
        )

    recall, rplus = evidence_recall(entry, triples)
    cprec, n_cited = citation_precision(claims_grounded)
    return {
        "id": entry["id"],
        "model": model,
        "answer_type": entry["answer_type"],
        "n_seeds": len(entry["seed_uris"]),
        "degenerate": not triples_prompt,
        "evidence_recall_at_k": recall,
        "R_plus": rplus,
        "n_context_triples": len(triples),
        "closed": {
            "correct": correctness(closed, entry),
            **claim_stats(claims_closed),
        },
        "grounded": {
            "correct": correctness(grounded, entry),
            "abstained": int(abstained),
            "citation_precision": cprec,
            "n_cited": n_cited,
            **(claim_stats([]) if abstained else claim_stats(claims_grounded)),
        },
        # raw artifacts: freeze the (expensive) generations so any verification
        # variant (e.g. gold-based H) can be recomputed retrospectively, no re-run
        "closed_answer": closed,
        "grounded_answer": grounded,
        "closed_claims": claims_closed,
        "grounded_claims": claims_grounded,
        # gold-based verification (same answers, gold evidence as reference)
        "gold_capped": int(gold_capped),
        "closed_gold": claim_stats(gclaims_closed),
        "grounded_gold": claim_stats(gclaims_grounded),
    }


# ── aggregation ──────────────────────────────────────────────────────────────
def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def aggregate(rows: list[dict]) -> dict:
    by_model = defaultdict(list)
    for r in rows:
        by_model[r["model"]].append(r)
    out = {}
    for model, rs in by_model.items():
        non_degen = [r for r in rs if not r["degenerate"]]
        # correctness over non-ask
        def acc(cond):
            return _mean([r[cond]["correct"] for r in rs if r[cond]["correct"] is not None])
        Hc = _mean([r["closed"]["H"] for r in rs])
        # abstention is a separate outcome: excluded from grounded H (not counted as 0 or 1)
        Hg = _mean([r["grounded"]["H"] for r in non_degen if not r["grounded"]["abstained"]])
        # gold-based H: same exclusions, plus questions whose gold set was capped
        uncapped = [r for r in rs if not r["gold_capped"]]
        Hc_g = _mean([r["closed_gold"]["H"] for r in uncapped])
        Hg_g = _mean([r["grounded_gold"]["H"] for r in non_degen
                      if not r["grounded"]["abstained"] and not r["gold_capped"]])
        out[model] = {
            "n": len(rs),
            "n_non_degenerate": len(non_degen),
            "acc_closed": acc("closed"),
            "acc_grounded": acc("grounded"),
            "delta_acc": (acc("grounded") - acc("closed")) if (acc("closed") is not None and acc("grounded") is not None) else None,
            "H_closed": Hc,
            "H_grounded": Hg,
            "delta_H": (Hc - Hg) if (Hc is not None and Hg is not None) else None,
            "H_closed_gold": Hc_g,
            "H_grounded_gold": Hg_g,
            "delta_H_gold": (Hc_g - Hg_g) if (Hc_g is not None and Hg_g is not None) else None,
            "abstention_rate": _mean([r["grounded"]["abstained"] for r in non_degen]),
            "citation_precision": _mean([r["grounded"]["citation_precision"] for r in rs]),
            "evidence_recall_at_k": _mean([r["evidence_recall_at_k"] for r in rs]),
            "R_plus_rate": _mean([r["R_plus"] for r in rs]),
        }
    return out


def by_stratum(rows: list[dict]) -> list[dict]:
    out = []
    for model in sorted({r["model"] for r in rows}):
        for label, pred in (("R+", lambda r: r["R_plus"] == 1), ("R-", lambda r: r["R_plus"] == 0)):
            rs = [r for r in rows if r["model"] == model and not r["degenerate"] and pred(r)]
            if not rs:
                continue
            out.append({
                "model": model,
                "stratum": label,
                "n": len(rs),
                "H_closed": _mean([r["closed"]["H"] for r in rs]),
                "H_grounded": _mean([r["grounded"]["H"] for r in rs if not r["grounded"]["abstained"]]),
                "abstention_rate": _mean([r["grounded"]["abstained"] for r in rs]),
                "acc_grounded": _mean([r["grounded"]["correct"] for r in rs if r["grounded"]["correct"] is not None]),
            })
    return out


# ── sampling + main ──────────────────────────────────────────────────────────
def _is_entity_answer(e: dict) -> bool:
    """The eval subset: questions whose answer is a set of DBpedia entities —
    SELECT questions whose gold answers are all resources (dbr:). Excludes
    count/ask and any literal-valued selects."""
    return (e["answer_type"] == "select"
            and bool(e.get("gold_answers"))
            and all(a["uri"].startswith("dbr:") for a in e["gold_answers"]))


def pick(questions: list[dict], args) -> list[dict]:
    if args.ids:
        by_id = {e["id"]: e for e in questions}
        return [by_id[i] for i in args.ids if i in by_id]
    # entity-answer questions only, then random sample with a fixed seed
    pool = [e for e in questions if _is_entity_answer(e)]
    return random.Random(args.seed).sample(pool, min(args.n, len(pool)))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200, help="sample size (ignored if --ids)")
    ap.add_argument("--seed", type=int, default=42, help="random sample seed (fixed for reproducibility)")
    ap.add_argument("--ids", nargs="*", default=None)
    ap.add_argument("--models", nargs="*", default=LOCKED_MODELS)
    ap.add_argument("--images", action="store_true", help="attach entity images (multimodal models only); off by default")
    ap.add_argument("--verifier-backend", default=config.VERIFIER, choices=["llm", "nli"],
                    help="'llm' (uses --verifier-model) or 'nli' (cross-encoder)")
    ap.add_argument("--verifier-model", default=config.VERIFIER_MODEL,
                    help="model id for the LLM verifier (independent of --models avoids self-grading)")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--out", default=str(RESULTS))
    ap.add_argument("--ablation-csv", default=None, help="path for the Qwen size-vs-hallucination CSV")
    args = ap.parse_args()

    config.VERIFIER_MODEL = args.verifier_model  # _verify_llm reads this

    questions = json.loads(GOLD.read_text())
    sample = pick(questions, args)
    sem = asyncio.Semaphore(args.concurrency)
    print(f"answer_models={args.models} | verifier={args.verifier_backend}"
          f"{':' + args.verifier_model if args.verifier_backend == 'llm' else ''} | "
          f"{len(sample)} questions ({dict(Counter(e['answer_type'] for e in sample))})")

    rows = []
    for model in args.models:
        done = 0
        async def one(e):
            nonlocal done
            r = {"id": e["id"], "model": model, "error": "unknown"}
            for _ in range(2):  # retry once on transient API failures (e.g. null content)
                try:
                    r = await eval_question(e, model, args.verifier_backend, sem, images=args.images)
                    break
                except Exception as ex:
                    r = {"id": e["id"], "model": model, "error": f"{type(ex).__name__}: {ex}"}
            done += 1
            if done % 10 == 0:
                print(f"  [{model}] {done}/{len(sample)}")
            return r
        rows.extend(await asyncio.gather(*(one(e) for e in sample)))

    ok = [r for r in rows if "error" not in r]
    errs = [r for r in rows if "error" in r]
    if errs:
        print(f"\n{len(errs)} errors (e.g. {errs[0]['error']})")

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "raw.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))

    summary = aggregate(ok)
    with open(outdir / "summary.csv", "w", newline="") as f:
        cols = ["model", "n", "n_non_degenerate", "acc_closed", "acc_grounded", "delta_acc",
                "H_closed", "H_grounded", "delta_H",
                "H_closed_gold", "H_grounded_gold", "delta_H_gold",
                "abstention_rate", "citation_precision", "evidence_recall_at_k", "R_plus_rate"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for model, m in summary.items():
            w.writerow({"model": model, **{k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()}})

    strata = by_stratum(ok)
    with open(outdir / "by_stratum.csv", "w", newline="") as f:
        if strata:
            w = csv.DictWriter(f, fieldnames=list(strata[0].keys()))
            w.writeheader()
            for s in strata:
                w.writerow({k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items()})

    # size-vs-hallucination CSV: Qwen size-sweep only (frontier excluded),
    # abstained/degenerate grounded rows omitted (abstention is a separate outcome)
    ablation_path = Path(args.ablation_csv) if args.ablation_csv else (outdir / "ablation.csv")
    ab_fields = ["question_id", "model", "model_params", "setting",
                 "n_claims", "n_supported", "n_inferred", "n_unverifiable", "hallucination_rate"]
    with open(ablation_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ab_fields)
        w.writeheader()
        for r in ok:
            if r["model"] not in MODEL_PARAMS:
                continue
            for setting in ("closed", "grounded"):
                if setting == "grounded" and (r["degenerate"] or r["grounded"]["abstained"]):
                    continue
                s = r[setting]
                w.writerow({
                    "question_id": r["id"], "model": r["model"],
                    "model_params": MODEL_PARAMS[r["model"]], "setting": setting,
                    "n_claims": s["n"], "n_supported": s["supported"],
                    "n_inferred": s["inferred"], "n_unverifiable": s["unverifiable"],
                    "hallucination_rate": round(s["H"], 6),
                })

    # console summary
    print("\n=== SUMMARY (per model) ===")
    for model, m in summary.items():
        print(f"\n{model}  (n={m['n']}, non-degenerate={m['n_non_degenerate']})")
        print(f"  accuracy:      closed {m['acc_closed']}  grounded {m['acc_grounded']}  Δ {m['delta_acc']}")
        print(f"  hallucination(retr): closed {m['H_closed']}  grounded {m['H_grounded']}  Δ {m['delta_H']}  (Δ>0 = grounding helps)")
        print(f"  hallucination(gold): closed {m['H_closed_gold']}  grounded {m['H_grounded_gold']}  Δ {m['delta_H_gold']}")
        print(f"  abstention {m['abstention_rate']} | citation_prec {m['citation_precision']} | evidence_recall {m['evidence_recall_at_k']} | R+ {m['R_plus_rate']}")
    n_capped = sum(r.get("gold_capped", 0) for r in ok)
    if n_capped:
        print(f"\n({n_capped} runs had >{GOLD_CAP} gold triples — excluded from gold-H; retrieved-H unaffected)")
    print(f"\nwrote {outdir}/raw.jsonl, summary.csv, by_stratum.csv, {ablation_path}")


if __name__ == "__main__":
    asyncio.run(main())
