#!/usr/bin/env python3
"""A/B test: OLD vs NEW grounded prompt + claim parser.

For a handful of validated questions, generate the grounded answer under BOTH the
old prompt (rigid one-fact-per-sentence) and the new prompt (natural prose), parse
each with its matching parser, and report:

  1. whether the LLM output changes meaningfully (length, sentence structure,
     multi-fact sentences, verbatim predicate copying), and
  2. whether the new parser works — including a cross-check that parses the SAME
     new-style answer with both parsers, exposing the citations the old parser drops.

Spotlight is bypassed: the grounded context is built directly from each question's
known seed_uris, so only the LLM endpoint (OpenRouter, via config) is needed.

Run from anywhere:  python3 eval/ab_prompt_test.py
"""
import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
# config's default KG_PATH is relative to app/; pin it absolute so we run anywhere
os.environ.setdefault("KG_PATH", str(ROOT / "offline" / "data" / "kg_subset.db"))

from src import config  # noqa: E402
from src.services.kg import KG, verbalise_triples, rank_triples  # noqa: E402
from src.services.llm import answer_grounded, parse_claims, _achat  # NEW prompt + parser  # noqa: E402

VQ_PATH = ROOT / "offline" / "data" / "validated_questions.json"
DEFAULT_IDS = ["2653", "915", "841", "2468"]


# ── OLD prompt: verbatim copy of answer_grounded() before our change ──────────
def old_system(triples: str) -> str:
    return (
        "Answer the question as a paragraph using ONLY the knowledge graph facts below. "
        "Each sentence must state exactly one fact and end with its citation. "
        "Do not use bullet points or lists. "
        "Do not combine multiple facts into one sentence.\n\n"
        "Make the text well formulated and sound."
        "Correct: 'Marie Curie was born in Warsaw. [T1] She died from aplastic anemia. [T5]'\n"
        "Wrong: 'Marie Curie was born in Warsaw and died from aplastic anemia. [T1][T5]'\n\n"
        "If the facts contain no relevant information, respond only with: "
        '"The provided facts do not contain enough information to answer this question."\n\n'
        f"Facts:\n{triples}"
    )


async def old_answer_grounded(question: str, triples: str, model: str) -> str:
    return await _achat(
        [
            {"role": "system", "content": old_system(triples)},
            {"role": "user", "content": question},
        ],
        model=model,
    )


# ── OLD parser: verbatim copy of parse_claims() before our change ─────────────
def parse_claims_old(answer: str) -> list[dict]:
    matches = list(re.finditer(r"\[T(\d+)\]", answer))
    if not matches:
        clean = answer.strip()
        return [{"claim": clean, "cited_triples": [], "start": 0, "end": len(answer)}] if clean else []
    result, last = [], 0
    for m in matches:
        idx = int(m.group(1))
        clean = re.sub(r"^[\s.,;]+", "", answer[last:m.start()]).strip()
        if clean:
            result.append({"claim": clean, "cited_triples": [idx], "start": last, "end": m.end()})
        last = m.end()
    tail = re.sub(r"^[\s.,;]+", "", answer[last:]).strip()
    if tail:
        result.append({"claim": tail, "cited_triples": [], "start": last, "end": len(answer)})
    return result


# ── metrics ───────────────────────────────────────────────────────────────────
def citation_integrity(answer: str, claims: list[dict]) -> tuple[int, int]:
    """(citations present in the text, citations captured by the parser)."""
    in_text = len(re.findall(r"\[T\d+\]", answer))
    captured = sum(len(c["cited_triples"]) for c in claims)
    return in_text, captured


def naturalness(answer: str, claims: list[dict], pred_labels: list[str]) -> dict:
    plain = re.sub(r"\[T\d+\]", "", answer)
    sents = [s for s in re.split(r"(?<=[.!?])\s+", plain.strip()) if s.strip()]
    words = re.findall(r"\w+", plain)
    multi = sum(1 for c in claims if len(c["cited_triples"]) >= 2)
    # verbatim predicate copying: distinct predicate labels reproduced verbatim
    distinct = sorted(set(pred_labels))
    copied = [p for p in distinct if re.search(rf"\b{re.escape(p)}\b", answer)]
    return {
        "chars": len(answer),
        "sentences": len(sents),
        "avg_words_per_sentence": round(len(words) / max(len(sents), 1), 1),
        "multi_cite_sentences": multi,
        "verbatim_predicates": f"{len(copied)}/{len(distinct)}",
        "verbatim_predicate_list": copied,
    }


def fmt_claims(claims: list[dict]) -> str:
    out = []
    for c in claims:
        out.append(f"      cited={c['cited_triples']!s:12s} \"{c['claim']}\"")
    return "\n".join(out) or "      (none)"


async def run_one(entry: dict, model: str) -> dict:
    q = entry["question"]
    subgraph = KG.get_subgraph(entry["seed_uris"], k=config.KG_HOP)
    ctx = verbalise_triples(subgraph, q)
    pred_labels = [t["predicate_label"] for t in rank_triples(subgraph, q)]

    if not ctx.strip():
        return {"id": entry["id"], "question": q, "skipped": "empty context"}

    # same model, same context, temperature from config — only the prompt differs
    old_ans, new_ans = await asyncio.gather(
        old_answer_grounded(q, ctx, model),
        answer_grounded(q, ctx, model),
    )

    old_claims = parse_claims_old(old_ans)
    new_claims = parse_claims(new_ans)
    # cross-check: parse the SAME new-style answer with the OLD parser
    new_ans_old_parser = parse_claims_old(new_ans)

    old_int = citation_integrity(old_ans, old_claims)
    new_int = citation_integrity(new_ans, new_claims)
    cross_int = citation_integrity(new_ans, new_ans_old_parser)

    return {
        "id": entry["id"],
        "question": q,
        "context_triples": ctx.count("[T"),
        "old": {
            "answer": old_ans,
            "claims": old_claims,
            "citations_in_text_vs_captured": old_int,
            "naturalness": naturalness(old_ans, old_claims, pred_labels),
        },
        "new": {
            "answer": new_ans,
            "claims": new_claims,
            "citations_in_text_vs_captured": new_int,
            "naturalness": naturalness(new_ans, new_claims, pred_labels),
        },
        "parser_cross_check_on_new_answer": {
            "old_parser_captured": cross_int,        # (in_text, captured) — drops if captured < in_text
            "new_parser_captured": new_int,
            "citations_dropped_by_old_parser": cross_int[0] - cross_int[1],
        },
    }


def report(r: dict) -> None:
    if r.get("skipped"):
        print(f"\n# [{r['id']}] {r['question']}  — SKIPPED ({r['skipped']})")
        return
    print("\n" + "=" * 100)
    print(f"# [{r['id']}] {r['question']}   ({r['context_triples']} context triples)")
    for cond in ("old", "new"):
        d = r[cond]
        nat = d["naturalness"]
        print(f"\n--- {cond.upper()} prompt ---")
        print(f'  ANSWER: {d["answer"]}')
        print(f"  stats: {nat['sentences']} sentences, {nat['avg_words_per_sentence']} avg words/sentence, "
              f"{nat['multi_cite_sentences']} multi-cite sentences, "
              f"verbatim predicates {nat['verbatim_predicates']} {nat['verbatim_predicate_list']}")
        it, cap = d["citations_in_text_vs_captured"]
        print(f"  parser({cond}): {len(d['claims'])} claims, citations {cap}/{it} captured")
        print(fmt_claims(d["claims"]))
    cc = r["parser_cross_check_on_new_answer"]
    print(f"\n--- PARSER CROSS-CHECK on the NEW answer ---")
    print(f"  OLD parser: {cc['old_parser_captured'][1]}/{cc['old_parser_captured'][0]} citations captured "
          f"(DROPPED {cc['citations_dropped_by_old_parser']})")
    print(f"  NEW parser: {cc['new_parser_captured'][1]}/{cc['new_parser_captured'][0]} citations captured")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", default=DEFAULT_IDS)
    ap.add_argument("--model", default=config.ANSWER_MODEL)
    ap.add_argument("--out", default=str(ROOT / "eval" / "results" / "ab_prompt.json"))
    args = ap.parse_args()

    vq = {e["id"]: e for e in json.load(open(VQ_PATH))}
    entries = [vq[i] for i in args.ids if i in vq]
    print(f"Model: {args.model}  |  questions: {[e['id'] for e in entries]}")

    results = []
    for e in entries:
        try:
            results.append(await run_one(e, args.model))
        except Exception as ex:
            results.append({"id": e["id"], "question": e["question"], "error": f"{type(ex).__name__}: {ex}"})
    for r in results:
        if r.get("error"):
            print(f"\n# [{r['id']}] {r['question']}  — ERROR: {r['error']}")
        else:
            report(r)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
