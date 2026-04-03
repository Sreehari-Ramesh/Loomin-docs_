#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

mkdir -p images models/ollama offline/rpms

echo "[export] Build project images with build compose"
docker compose -f docker-compose.build.yml build

echo "[export] Save images"
docker save loomin-frontend:latest -o images/frontend.tar
docker save loomin-backend:latest -o images/backend.tar
docker pull ollama/ollama:latest
docker save ollama/ollama:latest -o images/ollama.tar

echo "[export] Export host model store to bundle"
if [ -d /var/lib/loomin/ollama ]; then
  cp -r /var/lib/loomin/ollama/. models/ollama/
else
  echo "[warn] /var/lib/loomin/ollama not found. Start ollama once and pull models before export."
fi

echo "[export] Complete"
