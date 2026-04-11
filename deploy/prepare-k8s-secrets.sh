#!/usr/bin/env bash
# Create owui-socle-secrets in the socle namespace.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "${ROOT_DIR}/scripts/load_env.sh"
load_dotenv_preserve_existing "${ROOT_DIR}/.env"

: "${NAMESPACE:=owui-socle}"

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE"

kubectl -n "$NAMESPACE" create secret generic owui-socle-secrets \
  --from-literal=SCW_SECRET_KEY_LLM="${SCW_SECRET_KEY_LLM:-CHANGE_ME}" \
  --from-literal=SCW_API_KEY="${SCW_API_KEY:-${SCW_SECRET_KEY_LLM:-CHANGE_ME}}" \
  --from-literal=PIPELINES_API_KEY="${PIPELINES_API_KEY:-CHANGE_ME}" \
  --from-literal=WEBUI_SECRET_KEY="${WEBUI_SECRET_KEY:-CHANGE_ME}" \
  --from-literal=SEARXNG_SECRET="${SEARXNG_SECRET:-CHANGE_ME}" \
  --from-literal=KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-CHANGE_ME}" \
  --from-literal=KEYCLOAK_CLIENT_SECRET="${KEYCLOAK_CLIENT_SECRET:-CHANGE_ME}" \
  --from-literal=POSTGRES_USER="${POSTGRES_USER:-owui}" \
  --from-literal=POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-CHANGE_ME}" \
  --from-literal=MYVAULT_CLIENT_SECRET="${MYVAULT_CLIENT_SECRET:-CHANGE_ME}" \
  --from-literal=OWUI_API_KEY="${OWUI_API_KEY:-}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Applied owui-socle-secrets in namespace ${NAMESPACE}."
