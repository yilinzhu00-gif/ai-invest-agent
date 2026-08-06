#!/usr/bin/env bash
set -euo pipefail

base_url="${1:?usage: smoke-test.sh http://test-host:8000}"
case "$base_url" in
  *production*|*prod.*) echo "refusing non-test target" >&2; exit 2 ;;
esac
curl -fsS "$base_url/api/v1/health/live" >/dev/null
curl -fsS "$base_url/api/v1/health/ready" >/dev/null
