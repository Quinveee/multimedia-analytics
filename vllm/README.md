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
ssh -N -L 8267:<node>:8267 $USER@snellius.surf.nl   # small
ssh -N -L 8268:<node>:8268 $USER@snellius.surf.nl   # big
```

## Models

| Job | Model | GPU mem | GPUs | Port |
|---|---|---|---|---|
| `serve_small.job` | `Qwen/Qwen3-VL-8B-Instruct` | ~18 GB | 1 | 8267 |
| `serve_big.job` | `Qwen/Qwen3-VL-32B-Instruct` | ~64 GB | 2 | 8268 |
