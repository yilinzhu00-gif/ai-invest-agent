#!/usr/bin/env bash
set -euo pipefail

if ! command -v k6 >/dev/null 2>&1; then
  echo "k6 is required. Install it with: brew install k6" >&2
  exit 127
fi

target_env="${K6_TARGET_ENV:-local}"
if [ "$target_env" = "production" ]; then
  echo "refusing to run k6 against production; use an approved staging target" >&2
  exit 2
fi

report_dir="${K6_REPORT_DIR:-reports/k6}"
mkdir -p "$report_dir"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}" \
  k6 run --summary-export="$report_dir/summary.json" load/k6/agent_runs.js
echo "k6 summary written to $report_dir/summary.json"
