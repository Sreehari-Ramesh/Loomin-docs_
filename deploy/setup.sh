#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RPM_DIR="$ROOT_DIR/offline/rpms"
IMAGE_DIR="$ROOT_DIR/images"
MODEL_DIR="$ROOT_DIR/models"

log() {
  echo "[setup] $1"
}

log "Installing Docker engine and compose plugin from local RPMs"
sudo dnf install -y "$RPM_DIR"/*.rpm

log "Enabling Docker service"
sudo systemctl enable --now docker

log "Preparing local persistent directories"
sudo mkdir -p /var/lib/loomin/ollama /var/lib/loomin/backend-data

log "Loading pre-exported container images"
for tar in "$IMAGE_DIR"/*.tar; do
  [ -f "$tar" ] || continue
  sudo docker load -i "$tar"
done

if [ -d "$MODEL_DIR/ollama" ]; then
  log "Restoring Ollama local model store"
  sudo cp -r "$MODEL_DIR/ollama/." /var/lib/loomin/ollama/
fi

log "Starting Loomin stack (offline runtime compose)"
cd "$ROOT_DIR"
sudo docker compose -f docker-compose.offline.yml up -d

log "Done. Services: frontend:3000 backend:8000 ollama:11434"
