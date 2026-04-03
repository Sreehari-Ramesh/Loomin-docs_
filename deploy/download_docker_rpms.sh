#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RPM_OUT="$ROOT_DIR/offline/rpms"
mkdir -p "$RPM_OUT"

echo "[download] Fetching RHEL9-compatible Docker RPMs with dependencies"
sudo dnf download --resolve --destdir "$RPM_OUT" \
  containerd.io docker-ce docker-ce-cli docker-buildx-plugin docker-compose-plugin

echo "[download] RPMs available in $RPM_OUT"
