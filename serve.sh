#!/bin/bash
sbatch spotlight/serve.job
sbatch vllm/serve_small.job
sbatch vllm/serve_big.job
