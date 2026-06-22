# Quantitative evaluation: grounded vs. closed-book

Design for the batch evaluation that measures the **difference** between the
closed-book and KG-grounded conditions of the pipeline. This is the source of
the paper's Results section.

## 1. What we are measuring

The experiment is a **paired, within-question A/B test**. For every question we
run the same model twice through `run_pipeline()`; the *only* thing that differs
is whether the retrieved triples are supplied (grounded) or not (closed-book).
Linker, retriever, verifier, prompt skeleton, and temperature are frozen, so any
measured difference is attributable to grounding.

Because it is paired, the headline numbers are **per-question deltas**, not two
independent population means. This buys statistical power and lets us show the
*distribution* of the effect, not just its average.

Three orthogonal questions, each with its own truth source:

| Question | Metric family | Truth source |
|---|---|---|
| Does grounding get the **right answer**? | Correctness | LC-QuAD gold answer (`?uri` binding) |
| Does grounding reduce **unsupported claims**? | Groundedness / hallucination | Verifier labels (instrument) |
| Did grounding even **have the facts**? | Retrieval recall | Gold `evidence_triples` |

Correctness is truth vs. the world; groundedness is faithfulness vs. the
retrieved context; retrieval recall conditions and explains both.

## 2. Ground truth available (and the one gap to close)

`offline/data/validated_questions.json` already gives us, per question:
`question`, `gold_sparql`, `seed_uris`, `evidence_triples`.

**Missing: the gold answer.** `validate.py::_solve()` computes `solutions` (the
variable bindings that satisfy the gold query) but discards them, keeping only
the projected BGP as `evidence_triples`. We need the value bound to the answer
variable. Add to the validated entry:

```jsonc
"answer_vars": ["uri"],                 // projection var(s) of the gold query
"gold_answers": ["dbr:Jordan_River"],   // SELECT: bound ?uri values (shortened)
"answer_type": "select",                // "select" | "count" | "ask"
"gold_count": null,                     // COUNT: len(distinct solutions)
"gold_boolean": null                    // ASK: true (validated ⇒ a solution exists)
```

Extraction in `validate.py::run()`, right after `solutions = _solve(...)`:
- read the projected variable(s) from the original `SELECT` head (default `?uri`);
- `gold_answers = sorted({ shorten(str(b[var])) for b in solutions for var in answer_vars })`;
- `answer_type` from the head: `COUNT(...)` → `count` (`gold_count = len(gold_answers)`),
  `ASK` → `ask` (`gold_boolean = True`), else `select`.

> ASK questions are degenerate here: we only retain questions whose gold query
> *has* a solution, so every surviving ASK has gold answer `true` — there is no
> negative class. **Exclude ASK from the correctness metric** (keep them for
> groundedness) and report the SELECT/COUNT counts.

Labels (`label`/`abstract`) come from the `nodes` table for human-readable
matching and alias expansion.

## 3. Metric definitions

Notation: a pipeline run yields claims, each labelled
`supported` | `inferred` | `unverifiable` by the verifier. Let
`n = #claims`, and `n_s, n_i, n_u` the per-label counts.

### 3.1 Correctness (vs. gold answer) — SELECT/COUNT only
Generated answers are prose, not SPARQL bindings, so we use **normalized
containment**:

- Build the gold surface set = labels of `gold_answers` ∪ DBpedia redirect
  aliases, lower-cased, punctuation/diacritics stripped.
- `correct@1 = 1` iff ≥1 gold surface appears in the answer on word boundaries.
- For multi-answer SELECT also report **answer recall** =
  `|gold surfaces matched| / |gold surfaces|` and **precision** against a list of
  candidate spans (optional; `correct@1` is the headline).
- COUNT: `correct = 1` iff the gold integer appears as a token in the answer.

Containment is cheap and reproducible but has false positives (substring
collisions) and false negatives (paraphrase, "NYC" vs "New York City").
**Mitigation:** alias/redirect expansion + word-boundary match; plus a
**secondary LLM-judge correctness** on a fixed independent model
("does this answer correctly answer Q given gold = X? yes/no") run on a sample
to bound the containment metric's error.

### 3.2 Groundedness / hallucination (vs. verifier)
Per answer:
- **hallucination rate** `H = n_u / n` — share of claims unsupported by the KG.
- **support rate** `S = n_s / n`; **inferred rate** `I = n_i / n`.
- `inferred` counts as *not hallucinated* but is reported separately (it is the
  multi-hop bucket). Headline `H` uses `unverifiable` only; a strict variant
  `H_strict = (n_i + n_u)/n` is reported as robustness.
- **any-hallucination@question** `= 1[n_u > 0]` — a granularity-robust binary
  (see confounds).

Both conditions are scored against the **same** retrieved triples — the closed
answer's sentences are checked against the KG with `verify_uncited=True`. This
is what makes `H_closed` and `H_grounded` directly comparable: both ask "what
fraction of this answer is backed by the graph?".

### 3.3 Abstention (grounded only)
Detect the canned refusal ("The provided facts do not contain enough
information…") by normalized match → `abstained ∈ {0,1}`. Crossed with retrieval:
- **correct abstention**: `abstained ∧ ¬R+` (honest "don't know" when the KG
  lacked the fact) — *good*.
- **over-abstention**: `abstained ∧ R+` (refused despite the fact being present)
  — *bad*.
Abstentions are a **separate outcome**, never counted as hallucinations.

### 3.4 Attribution / citation precision (grounded only)
The grounded prompt requires `[T#]` citations, so alignment is self-reported and
checkable:
- **citation coverage** `= n_cited / n` (uncited claims violate the prompt).
- **citation precision** `= #(cited claims labelled supported) / n_cited` —
  how often a cited triple actually entails the sentence (the verifier already
  computes this per cited claim).
- **citation correctness vs. gold** `= |cited triples ∩ gold evidence| /
  |cited triples|` — stronger: did it cite the *actually-relevant* evidence,
  not just any entailing triple.

### 3.5 Retrieval recall (shared conditioning variable)
Match `evidence_triples` against retrieved triples (subject/predicate/object on
shortened URIs):
- **evidence recall@k** `= |gold evidence ∩ verbalised [T#] list| / |gold
  evidence|` — what grounding actually saw (after the `KG_MAX_TRIPLES` cap).
- **evidence recall (subgraph)** — same over the full retrieved subgraph
  (pre-cap). The gap = ranking/truncation loss.
- **R+** `= 1[evidence recall@k > 0]` — "grounding had ≥1 needed fact". This is
  the key stratifier (RQ2: KG incompleteness).

## 4. The headline *difference* metrics

All paired (same questions), reported per model:

1. **ΔAccuracy** `= Acc_grounded − Acc_closed` — does grounding produce more
   correct answers.
2. **ΔHallucination** `= H_closed − H_grounded` — the headline. Expected
   positive and **larger for smaller models** (less parametric knowledge to fall
   back on). Reported macro (mean of per-question H) with paired bootstrap CI.
3. **Abstention profile** (grounded) — correct-abstention vs over-abstention
   rates; grounding should convert hallucinations into honest refusals.
4. **Citation precision** (grounded) — reliability of the self-attribution the
   UI shows; no closed-book counterpart.

Secondary / conditioning: evidence recall@k, and **everything stratified by
R+ vs R−** (Section 6).

## 5. Experimental protocol

- **Questions**: the validated LC-QuAD subset. Run all of it if tractable, else a
  stratified sample over `answer_type`, `#evidence_triples` (hop complexity), and
  R+/R−. Report N and the sampling.
- **Models**: the three tiers — `small` (Qwen3-VL-8B), `big` (Qwen3-VL-32B), and
  one frontier API (`claude-*` or `gpt-*`). The sweep across scale is itself a
  result axis.
- **Verifier = the measurement instrument. Pin it, and keep it independent of
  the model under test.**
  - *Self-grading hazard*: with `VERIFIER_MODEL = big`, evaluating the `big`
    generator is self-preference-biased. Fix the verifier to **one model used for
    all runs**.
  - *Recommendation*: **NLI verifier** (`cross-encoder/nli-deberta-v3-base`) as
    primary — deterministic, reproducible, generator-agnostic, and it is what the
    report already claims. Add a **frontier-LLM verifier** as a robustness
    cross-check on a sample. Report both; flag any divergence.
- **Determinism**: `LLM_TEMPERATURE = 0`. vLLM is not bit-exact at temp 0, so run
  **k = 3 seeds on ≥1 model** to bound run-to-run variance; single run for the
  rest, noted.
- **Degenerate runs**: when no entity links / empty subgraph, the pipeline sets
  `grounded = closed`. These contribute ΔH = 0 spuriously — **tag and exclude
  from Δ metrics**, report their count as a *retrieval-failure* stratum.

## 6. Stratification (the analytical core)

Cross every metric with retrieval status:

| Stratum | Meaning | What an unsupported grounded claim implies |
|---|---|---|
| **R+** evidence retrieved | grounding had the fact | model **ignored** an available fact → model failure |
| **R−** evidence missing | grounding lacked the fact | **KG gap** → not the model's fault (RQ2) |

This is what licenses the report's central claim that an `unverifiable` label is
"missing knowledge, not necessarily false". ΔHallucination on **R+** isolates the
pure grounding effect; abstention on **R−** measures honest deferral.

## 7. Statistics

- **Correctness** (binary, paired): McNemar's test on (closed correct, grounded
  correct); report ΔAccuracy with a paired bootstrap 95% CI.
- **Rates** (per-question H, paired): Wilcoxon signed-rank on per-question ΔH;
  report mean ΔH with paired bootstrap CI and an effect size.
- **Aggregation**: **macro** (mean over questions, equal weight) is the headline;
  **micro** (pool all claims) reported as secondary. Macro avoids long answers
  dominating.

## 8. Confounds & mitigations

1. **Claim-granularity mismatch.** Closed = full sentences (`parse_sentences`);
   grounded = citation-bounded chunks (`parse_claims`). Different segmenters bias
   raw claim counts. *Mitigations*: (a) per-question rates with equal weight;
   (b) **any-hallucination@question** binary; (c) robustness pass segmenting both
   with the same sentence splitter.
2. **Verifier noise.** It's a proxy. *Mitigation*: instrument validation (§10) +
   dual verifier (NLI + LLM) agreement.
3. **Containment correctness errors.** *Mitigation*: alias/redirect expansion,
   word-boundary match, secondary LLM-judge on a sample.
4. **Degenerate grounded==closed.** Tagged and excluded from Δ (§5).
5. **Temp-0 nondeterminism.** k-seed variance bound (§5).
6. **Verifier self-preference.** Pinned independent verifier (§5).

## 9. Outputs & harness

`eval/run_eval.py`:
1. load `validated_questions.json` (with the §2 additions);
2. for each (question × model): `run_pipeline(q, answer_model=model)` with the
   verifier pinned independent of `model`;
3. compute per-question metrics (§3) incl. retrieval matching and gold-answer
   containment;
4. write **`eval/results/raw.jsonl`** — one row per (question, model) carrying
   both conditions and every raw count (for drill-down + figures);
5. write **`eval/results/summary.csv`** — aggregates per (model, condition) and
   the paired Δ table;
6. write **`eval/results/by_stratum.csv`** — metrics split by R+/R−.

`raw.jsonl` row schema (sketch):
```jsonc
{
  "id": "2653", "model": "big", "answer_type": "select",
  "R_plus": true, "evidence_recall_at_k": 1.0, "degenerate": false,
  "closed":   {"correct": 0, "n": 4, "n_s": 1, "n_i": 0, "n_u": 3, "H": 0.75},
  "grounded": {"correct": 1, "n": 3, "n_s": 3, "n_i": 0, "n_u": 0, "H": 0.0,
               "abstained": false, "n_cited": 3, "cite_prec": 1.0,
               "cite_correct_vs_gold": 1.0}
}
```
`raw.jsonl` is the input to the `academic-plotting` skill for the Results figures
(ΔH by model tier; H by R+/R−; abstention profile; recall-vs-accuracy).

## 10. Verifier validation (instrument calibration)

Before trusting the numbers, validate the verifier against gold on a held-out
sample:
- **Positives**: (gold evidence triple, a sentence it supports) → should be
  `supported`.
- **Negatives**: (random non-evidence triple, same sentence) → should be
  `unverifiable`.
Report verifier precision/recall/agreement (NLI vs LLM). This calibrates how much
to trust H and citation precision, and is a cheap, defensible paragraph for the
paper's methodology.

## 11. Dependency note

This harness needs `validated_questions.json` + `kg_subset.db`, neither of which
is built yet (`offline/data/` currently holds only `uris.json`). The offline
pipeline (`offline/main.py`) must run first, **including the §2 `validate.py`
change**, before the eval can execute.
