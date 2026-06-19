# Multimedia Analytics

Interactive Visual Grounding of LLM Responses in Multimodal Knowledge Graphs

An interactive visual analytics dashboard where users ask natural language questions over a multimodal KG, and the system maps each claim in the LLM's answer back to its supporting KG triple, or flags it as hallucinated.

## Repo structure

- `app/` — backend pipeline + Plotly/Dash demo app
- `offline/` — offline data pipeline (KG subset construction from DBpedia + LC-QuAD)
- `vllm/` — Slurm jobs to serve LLM on Snellius via vLLM
- `spotlight/` — Slurm jobs to serve DBpedia Spotlight on Snellius

## Setup

Run once on Snellius to install environments:

```bash
./setup.sh
```

Then each session, start the models:

```bash
./serve.sh
```

Check assigned nodes with `squeue -u $USER`, then open SSH tunnels (see `vllm/README.md` and `spotlight/README.md`).

## Data

Place the KG files in `offline/data/`:

```
offline/data/
  kg_subset.db
  images/
```

## App (`app/`)

Base app scaffold from the course: https://github.com/GoncaloBFM/mma2026, original entry point is `src/main.py`.

Dependencies are managed with `uv`. All commands run from `app/`.

**Test the pipeline from CLI:**

```bash
uv run python3 src/pipeline.py --question "Who is Marie Curie?"
```

**Run the demo UI:**

```bash
uv run python3 src/demo.py
```

Then open http://127.0.0.1:8050. Ask a question, see grounded + closed-book answers with claim highlighting. Select nodes in the subgraph to re-run with a filtered KG context.

The pipeline entry point is `run_pipeline()` in `src/pipeline.py`, see the docstring for the full return shape.

Models, API keys, and endpoints can be configured via env vars or directly in `src/config.py`.