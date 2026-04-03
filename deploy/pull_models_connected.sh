#!/usr/bin/env bash
set -euo pipefail

MODELS=("llama3:8b" "mistral:7b")

for m in "${MODELS[@]}"; do
  echo "[models] pulling $m"
  ollama pull "$m"
done

echo "[models] done"
