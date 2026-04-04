#!/usr/bin/env bash
# Create owui-registry image pull secret in the socle namespace.
# Also replicates to feature namespaces if FEATURE_NAMESPACES is set.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "${ROOT_DIR}/scripts/load_env.sh"
load_dotenv_preserve_existing "${ROOT_DIR}/.env"

if [[ -z "${REGISTRY_SERVER:-}" || -z "${REGISTRY_USERNAME:-}" || -z "${REGISTRY_PASSWORD:-}" ]]; then
  echo "Registry credentials are incomplete. Skipping."
  exit 0
fi

if [[ "${REGISTRY_USERNAME}" == "CHANGE_ME" || "${REGISTRY_PASSWORD}" == "CHANGE_ME" ]]; then
  echo "Registry credentials still use placeholders. Skipping."
  exit 0
fi

: "${NAMESPACE:=owui-socle}"

# Namespaces where the registry secret must exist
NAMESPACES=("$NAMESPACE")
if [[ -n "${FEATURE_NAMESPACES:-}" ]]; then
  IFS=',' read -ra EXTRA <<< "$FEATURE_NAMESPACES"
  NAMESPACES+=("${EXTRA[@]}")
fi

for ns in "${NAMESPACES[@]}"; do
  ns="$(echo "$ns" | xargs)"
  kubectl get namespace "$ns" >/dev/null 2>&1 || kubectl create namespace "$ns"

  kubectl -n "$ns" create secret docker-registry owui-registry \
    --docker-server="${REGISTRY_SERVER}" \
    --docker-username="${REGISTRY_USERNAME}" \
    --docker-password="${REGISTRY_PASSWORD}" \
    --docker-email="${REGISTRY_EMAIL:-ops@example.local}" \
    --dry-run=client -o yaml | kubectl apply -f -

  echo "Applied owui-registry in namespace ${ns}."
done
