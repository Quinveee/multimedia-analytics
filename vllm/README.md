# vLLM on Snellius

## 1. Setup (first time only)

```bash
ssh snellius
python3 -m venv $HOME/vllm-env
source $HOME/vllm-env/bin/activate
pip install vllm
```

## 2. Submit the job

```bash
sbatch serve.job
```

Check it's running:
```bash
squeue -u $USER
```

Note the node it's running on (e.g. `gcn1`):
```bash
squeue -u $USER -o "%N"
```

## 3. SSH tunnel (on your local machine)

```bash
ssh -L 8000:<node>:8000 snellius
# e.g. ssh -L 8000:gcn1:8000 snellius
```

Keep this terminal open.

## 4. Run pipeline

```bash
cd mma2025/src
LLM_BASE_URL=http://localhost:8000/v1 LLM_MODEL=Qwen/Qwen2.5-7B-Instruct \
python3 pipeline.py --question "Who did Marie Curie marry?"
```

## Models

| Model | GPU mem | Use |
|---|---|---|
| `Qwen/Qwen2.5-7B-Instruct` | ~16GB | default |
| `Qwen/Qwen2.5-72B-Instruct` | ~160GB | high quality (multi-GPU) |
