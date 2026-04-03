#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR/.."

ARCHIVE_NAME="loomin-bootstrap.tar.gz"

tar -czf "$ROOT_DIR/$ARCHIVE_NAME" \
  deploy/setup.sh \
  deploy/verify_offline.sh \
  deploy/download_docker_rpms.sh \
  deploy/export_bundle.sh \
  deploy/pull_models_connected.sh \
  deploy/docker-compose.yml \
  deploy/docker-compose.build.yml \
  deploy/docker-compose.offline.yml \
  deploy/offline \
  deploy/images \
  deploy/models

echo "Created: $ROOT_DIR/$ARCHIVE_NAME"
