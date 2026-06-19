# Multimedia Analytics

Interactive Visual Grounding of LLM Responses in Multimodal Knowledge Graphs

An interactive visual analytics dashboard where users ask natural language questions over a multimodal KG, and the system maps each claim in the LLM's answer back to its supporting KG triple, or flags it as hallucinated.

## Repo structure

- `app/` — Plotly/Dash frontend + backend pipeline (LLM calls, KG retrieval, claim verification)
- `offline/` — offline data pipeline (KG subset construction from DBpedia + LC-QuAD)
- `vllm/` — Slurm jobs to serve LLM on Snellius via vLLM
- `spotlight/` — Slurm jobs to serve DBpedia Spotlight on Snellius

## Setup

> Run once to install environments on Snellius compute nodes.

```bash
./setup.sh
```

## Serve

> Run each session to start all services.

```bash
./serve.sh
```

Then check assigned nodes with `squeue -u $USER` and set up SSH tunnels, see `vllm/README.md` and `spotlight/README.md`.
