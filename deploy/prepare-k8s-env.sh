#!/usr/bin/env bash
# Validate and export K8s env vars for the socle deployment.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo ".env is missing. Copy .env.example to .env and fill in your secrets." >&2
  exit 1
fi

source "${ROOT_DIR}/scripts/load_env.sh"
load_dotenv_preserve_existing "${ROOT_DIR}/.env"

: "${NAMESPACE:=owui-socle}"
export NAMESPACE

required_vars=(
  NAMESPACE
  OPENWEBUI_IMAGE
  PIPELINES_IMAGE
  SEARXNG_IMAGE
  VALKEY_IMAGE
  OPENWEBUI_HOST
  KEYCLOAK_HOST
  LETSENCRYPT_EMAIL
  KEYCLOAK_ADMIN
  SCW_LLM_BASE_URL
  SCW_LLM_MODEL
)

missing=0
for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "Missing required variable: ${var_name}" >&2
    missing=1
  fi
done

if [[ "$missing" -ne 0 ]]; then
  exit 1
fi

echo "Kubernetes environment variables look complete."
