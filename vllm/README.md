# vLLM on Snellius

Submit from repo root (`~/multimedia-analytics`).

## 1. Install (first time only)

```bash
sbatch vllm/install.job
```

## 2. Serve

```bash
sbatch vllm/serve.job
```

Check the node: `squeue -u $USER`

## 3. SSH tunnel (local machine)

```bash
ssh -L 8267:<node>:8267 snellius
```

## 4. Run pipeline

```bash
cd mma2025/src
LLM_BASE_URL=http://localhost:8267/v1 LLM_MODEL=Qwen/Qwen2.5-7B-Instruct \
python3 pipeline.py --question "Who did Marie Curie marry?"
```

## Models

| Model | GPU mem |
|---|---|
| `Qwen/Qwen2.5-7B-Instruct` | ~16 GB |
| `Qwen/Qwen2.5-72B-Instruct` | ~160 GB |
