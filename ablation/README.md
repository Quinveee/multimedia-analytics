ablation.py measures the hallucination rate in closed-book and KG-grounded settings for per model. The results are appended to a shared CSV so all models end up in one file for plotting.

vLLM mode (local Snellius, requires vLLM server to be running):

    python ablation/ablation.py \\
        --model-name  Qwen/Qwen3-VL-8B-Instruct \\
        --model-params 8 \\
        --model-url   http://localhost:8267/v1 \\
        --n-questions 500 \\
        --out         ablation/results.csv

OpenRouter mode (set OPENROUTER_API_KEY):

    python ablation/ablation.py \\
        --model-name  qwen/qwen3-vl-8b-instruct \\
        --model-params 8 \\
        --openrouter \\
        --n-questions 500 \\
        --out         ablation/results.csv

    # Required env vars:
    #   OPENROUTER_API_KEY  for --openrouter

The script:
  1. Samples --n-questions questions from validated_questions.json (with a fixed seed).
  2. For each question, retrieves a KG subgraph via the gold seed_uris
     (Spotlight is intentionally bypassed so results don't depend on entity
     linking quality).
  3. Generates a closed-book answer (no KG context) and a KG-grounded answer
     (with [T#] citations).
  4. Verifies every claim with the NLI cross-encoder (model-agnostic, runs on
     CPU so it does not compete with vLLM for GPU memory).
  5. Appends one row per (question, setting) to --out.

Resume support: questions already present in the CSV for this model are skipped,
so an interrupted run can be continued by re-running the same command.