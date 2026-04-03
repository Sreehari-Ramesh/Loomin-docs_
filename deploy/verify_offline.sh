#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"

check() {
  local name="$1"
  local url="$2"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" "$url")
  if [ "$code" = "200" ]; then
    echo "[ok] $name"
  else
    echo "[fail] $name (HTTP $code)"
    exit 1
  fi
}

check "backend" "$BASE_URL/health"
check "frontend" "http://localhost:3000"
check "ollama" "http://localhost:11434/api/tags"

echo "offline verification succeeded"
echo "compose file used: deploy/docker-compose.offline.yml"
