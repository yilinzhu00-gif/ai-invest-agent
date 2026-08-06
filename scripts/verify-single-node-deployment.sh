#!/usr/bin/env bash
set -euo pipefail

target="${1:-}"
case "$target" in
  https://*) ;;
  *) echo "refusing non-HTTPS target; pass https://your-domain" >&2; exit 2 ;;
esac

curl --fail --silent --show-error --max-time 10 "$target/api/v1/health/ready" >/dev/null
curl --fail --silent --show-error --max-time 10 -I "$target/" | grep -qi '^strict-transport-security:' || {
  echo "missing Strict-Transport-Security response header" >&2
  exit 1
}
echo "single-node HTTPS deployment checks passed"
