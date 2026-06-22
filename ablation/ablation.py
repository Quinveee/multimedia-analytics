import argparse
import asyncio
import csv
import json
import os
import random
import sys
import time
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model-name", required=True,
                   help="HuggingFace model id, e.g. Qwen/Qwen3-VL-8B-Instruct")
    p.add_argument("--model-params", required=True, type=float,
                   help="Nominal parameter count in billions, e.g. 8 or 235")
    p.add_argument("--model-url", default="http://localhost:8267/v1",
                   help="vLLM endpoint base URL (ignored with --openrouter)")
    p.add_argument("--openrouter", action="store_true",
                   help="Route calls through OpenRouter (https://openrouter.ai/api/v1). "
                        "Set OPENROUTER_API_KEY in the environment. Model name must be "
                        "in OpenRouter format, e.g. qwen/qwen3-vl-8b-instruct.")
    p.add_argument("--n-questions", type=int, default=None,
                   help="Number of questions to evaluate (sampled with --seed). "
                        "set None to use the entire dataset.")
    p.add_argument("--verifier", choices=["llm", "nli"], default="llm",
                   help="Claim verification method. 'llm' classifies each claim with "
                        "--verifier-model; 'nli' uses a local cross-encoder (no API cost).")
    p.add_argument("--verifier-model", default="openai/gpt-4o-mini",
                   help="OpenRouter model used when --verifier llm. Defaults to a cheap "
                        "model that is good enough for 3-way claim classification. "
                        "Other good cheap options: google/gemini-2.0-flash-001, "
                        "anthropic/claude-3.5-haiku.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default="ablation/results.csv",
                   help="Output CSV path (appended to if it already exists)")
    p.add_argument("--overwrite", action="store_true",
                   help="Overwrite existing rows for this model instead of resuming")
    return p.parse_args()


def _configure_env(args: argparse.Namespace) -> None:
    root = Path(__file__).resolve().parent.parent
    os.environ.setdefault("KG_PATH", str(
        root / "offline" / "data" / "kg_subset.db"))

    os.environ["LLM_TEMPERATURE"] = "0.0"
    # Verifier method + model are fixed here so they don't vary across ablation runs
    os.environ["VERIFIER"] = args.verifier
    os.environ["VERIFIER_MODEL"] = args.verifier_model
    # Keep NLI on CPU so it doesn't try to grab GPU memory
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

    if not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY environment variable is not set.")


FIELDS = [
    "question_id", "model", "model_params", "setting",
    "n_claims", "n_supported", "n_inferred", "n_unverifiable",
    "hallucination_rate",
]


def _done_ids(out: Path, model_name: str) -> set[str]:
    """Return question IDs already written for this model (for resume)."""
    if not out.exists():
        return set()
    done: set[str] = set()
    with open(out, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("model") == model_name:
                done.add(row["question_id"])
    return done


def _stats(claims: list[dict]) -> dict:
    n = len(claims)
    n_sup = sum(1 for c in claims if c["label"] == "supported")
    n_inf = sum(1 for c in claims if c["label"] == "inferred")
    n_unv = sum(1 for c in claims if c["label"] == "unverifiable")
    return {
        "n_claims": n,
        "n_supported": n_sup,
        "n_inferred": n_inf,
        "n_unverifiable": n_unv,
        "hallucination_rate": round(n_unv / n, 6) if n > 0 else 0.0,
    }


def main() -> None:
    args = _parse_args()
    _configure_env(args)

    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "app"))

    from src.services.kg import KG, verbalise_triples
    from src.services.llm import (
        answer_closed,
        answer_grounded,
        parse_claims,
        parse_sentences,
    )
    from src.services.verifier import verify_claims

    # load dataset
    vq_path = root / "offline" / "data" / "validated_questions.json"
    all_qs = json.loads(vq_path.read_text(encoding="utf-8"))
    if args.n_questions is None:
        sample = all_qs
    else:
        rng = random.Random(args.seed)
        sample = rng.sample(all_qs, min(args.n_questions, len(all_qs)))

    # resume / overwrite
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.overwrite:
        # Remove existing rows for this model and rewrite header
        existing: list[dict] = []
        if out.exists():
            with open(out, newline="", encoding="utf-8") as f:
                existing = [r for r in csv.DictReader(f)
                            if r.get("model") != args.model_name]
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(existing)
        done: set[str] = set()
    else:
        done = _done_ids(out, args.model_name)

    remaining = [q for q in sample if q["id"] not in done]

    answer_model = args.model_name

    print(f"\nmodel      : {args.model_name}  ({args.model_params}B params)")
    print(f"endpoint   : OpenRouter")
    verifier_label = (f"llm ({args.verifier_model})"
                      if args.verifier == "llm" else "nli (local cross-encoder)")
    print(f"verifier   : {verifier_label}")
    print(f"questions  : {len(sample)} sampled | {len(done)} already done | "
          f"{len(remaining)} to evaluate")
    print(f"output     : {out}\n")

    if not remaining:
        print("All questions already evaluated for this model.")
        return

    # evaluation
    f_out = open(out, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(f_out, fieldnames=FIELDS)
    if not out.stat().st_size or args.overwrite:
        writer.writeheader()

    totals: dict[str, dict] = {
        "closed":   {"n_claims": 0, "n_unverifiable": 0},
        "grounded": {"n_claims": 0, "n_unverifiable": 0},
    }
    t0 = time.time()
    errors = 0

    try:
        for i, q in enumerate(remaining, 1):
            qid = q["id"]
            question = q["question"]
            seed_uris = q.get("seed_uris", [])

            try:
                subgraph = KG.get_subgraph(seed_uris, k=1)
                triples_prompt = verbalise_triples(subgraph, question)

                # Closed-book (model answers from parametric memory only)
                closed_ans = asyncio.run(
                    answer_closed(question, model=answer_model))
                claims_closed = asyncio.run(verify_claims(
                    parse_sentences(closed_ans),
                    triples_prompt,
                    verify_uncited=True,
                ))

                # Grounded (model must ground every sentence in a KG triple
                if triples_prompt:
                    grounded_ans = asyncio.run(answer_grounded(
                        question, triples_prompt, model=answer_model
                    ))
                else:
                    grounded_ans = closed_ans
                claims_grounded = asyncio.run(verify_claims(
                    parse_claims(grounded_ans),
                    triples_prompt,
                    verify_uncited=False,
                ))

                for setting, claims in (
                    ("closed", claims_closed),
                    ("grounded", claims_grounded),
                ):
                    st = _stats(claims)
                    writer.writerow({
                        "question_id": qid,
                        "model": args.model_name,
                        "model_params": args.model_params,
                        "setting": setting,
                        **st,
                    })
                    totals[setting]["n_claims"] += st["n_claims"]
                    totals[setting]["n_unverifiable"] += st["n_unverifiable"]

                f_out.flush()

            except Exception as exc:
                errors += 1
                print(f"  [WARN] q={qid}: {exc}")
                continue

            if i % 10 == 0 or i == len(remaining):
                elapsed = time.time() - t0
                qps = i / elapsed
                eta = (len(remaining) - i) / qps if qps > 0 else float("inf")
                c_hr = (totals["closed"]["n_unverifiable"] /
                        max(totals["closed"]["n_claims"], 1))
                g_hr = (totals["grounded"]["n_unverifiable"] /
                        max(totals["grounded"]["n_claims"], 1))
                print(
                    f"  [{i:4d}/{len(remaining)}]  "
                    f"closed={c_hr:.3f}  grounded={g_hr:.3f}  "
                    f"errors={errors}  eta={eta / 60:.1f}min"
                )
    finally:
        f_out.close()

    # print summary of results
    print(f"\n{'─'*60}")
    print(f"Model: {args.model_name} ({args.model_params}B)")
    for setting in ("closed", "grounded"):
        nc = totals[setting]["n_claims"]
        nu = totals[setting]["n_unverifiable"]
        hr = nu / nc if nc else 0.0
        print(f"  {setting:8s}: {hr:.3f} hallucination rate  "
              f"({nu}/{nc} unverifiable claims)")
    print(f"Errors: {errors}")
    print(f"Results written to {out}")


if __name__ == "__main__":
    main()
