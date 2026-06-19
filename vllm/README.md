# vLLM on Snellius

Submit from repo root (`~/multimedia-analytics`).

## 1. Install (first time only)

```bash
sbatch vllm/install.job
```

## 2. Serve

```bash
sbatch vllm/serve_small.job   # Qwen2.5-7B  → port 8267
sbatch vllm/serve_big.job     # Qwen2.5-72B → port 8268
```

Check the node: `squeue -u $USER`

## 3. SSH tunnel (local machine)

```bash
ssh -N -L 8267:<node>:8267 scur0267@snellius.surf.nl   # small
ssh -N -L 8268:<node>:8268 scur0267@snellius.surf.nl   # big
```

## Models

| Job | Model | GPU mem | GPUs | Port |
|---|---|---|---|---|
| `serve_small.job` | `Qwen/Qwen2.5-7B-Instruct` | ~16 GB | 1 | 8267 |
| `serve_big.job` | `Qwen/Qwen2.5-72B-Instruct` | ~160 GB | 2 | 8268 |
