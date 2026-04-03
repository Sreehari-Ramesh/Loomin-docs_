#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
DATA_FILE="${2:-tests/faithfulness_cases.jsonl}"

if [ ! -f "$DATA_FILE" ]; then
  echo "[fail] missing test case file: $DATA_FILE"
  exit 1
fi

python tests/faithfulness_check.py --base-url "$BASE_URL" --cases "$DATA_FILE"
