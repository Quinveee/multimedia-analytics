# vLLM on Snellius

Submit from repo root (`~/multimedia-analytics`).

## 1. Install (first time only)

```bash
sbatch vllm/install.job
```

## 2. Serve

```bash
sbatch vllm/serve_small.job   # Qwen3-VL-8B  → port 8267  (app "small" slot)
sbatch vllm/serve_big.job     # Qwen3-VL-32B → port 8268  (app "big"   slot)
```

Check the node: `squeue -u $USER`

## 3. SSH tunnel (local machine)

```bash
ssh -N -L 8267:<node>:8267 $USER@snellius.surf.nl   # small
ssh -N -L 8268:<node>:8268 $USER@snellius.surf.nl   # big
```

## Models

| Job | Model | GPU mem | GPUs | Port | Use |
|---|---|---|---|---|---|
| `serve_2b.job`   | `Qwen/Qwen3-VL-2B-Instruct`           | ~4 GB  | 1 | 8265 | ablation |
| `serve_4b.job`   | `Qwen/Qwen3-VL-4B-Instruct`           | ~8 GB  | 1 | 8266 | ablation |
| `serve_small.job`| `Qwen/Qwen3-VL-8B-Instruct`           | ~18 GB | 1 | 8267 | app / ablation |
| `serve_big.job`  | `Qwen/Qwen3-VL-32B-Instruct`          | ~64 GB | 2 | 8268 | app |
| `serve_30b.job`  | `Qwen/Qwen3-VL-30B-A3B-Instruct`      | ~60 GB | 1 | 8269 | ablation |
| `serve_35b.job`  | `Qwen/Qwen3-VL-35B-Instruct`          | ~70 GB | 2 | 8270 | ablation |
| `serve_235b.job` | `Qwen/Qwen3-VL-235B-A22B-Instruct`    | ~235 GB (fp8) | 4 | 8271 | ablation |

## Ablation study

To run the full hallucination-rate ablation (one self-contained job per model,
no tunnel needed — vLLM and the eval script run on the same Slurm node):

```bash
sbatch ablation/jobs/run_2b.job
sbatch ablation/jobs/run_4b.job
sbatch ablation/jobs/run_8b.job
sbatch ablation/jobs/run_30b.job
sbatch ablation/jobs/run_35b.job
sbatch ablation/jobs/run_235b.job
```

Each job appends its results to `ablation/results.csv`.  Once all jobs finish,
generate the plot from the repo root:

```bash
python ablation/plot.py
```

Output: `ablation/hallucination_vs_params.png`
