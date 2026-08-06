#!/usr/bin/env bash
set -euo pipefail

binding_file="${1:-deploy/env/provider-binding.env}"
if [ ! -f "$binding_file" ]; then
  echo "provider binding file not found: $binding_file" >&2
  exit 2
fi

value_for() {
  grep -E "^$1=" "$binding_file" | head -n 1 | cut -d= -f2-
}

required=(
  CLOUD_PROVIDER DEPLOY_REGION CONTAINER_IMAGE_DIGEST GITHUB_OIDC_AUDIENCE
  OIDC_ISSUER OIDC_JWKS_URL DATABASE_SECRET_REF OBJECT_STORAGE_BUCKET
  OBJECT_STORAGE_SECRET_REF GRAFANA_URL
)
for key in "${required[@]}"; do
  value="$(value_for "$key")"
  if [ -z "$value" ] || [[ "$value" == *"replace-with"* ]]; then
    echo "missing operator binding: $key" >&2
    exit 2
  fi
done

image_digest="$(value_for CONTAINER_IMAGE_DIGEST)"
case "$image_digest" in
  *@sha256:[0-9a-f][0-9a-f]*) ;;
  *) echo "CONTAINER_IMAGE_DIGEST must use an immutable sha256 digest" >&2; exit 2 ;;
esac
echo "provider binding contract is complete; deployment still requires human Environment approval"
