#!/usr/bin/env bash
# Deploy the owuicore socle to Kubernetes.
# Services: OpenWebUI, Keycloak, Pipelines, SearXNG, Valkey
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "${ROOT_DIR}/deploy/prepare-k8s-env.sh"

source "${ROOT_DIR}/scripts/load_env.sh"
load_dotenv_preserve_existing "${ROOT_DIR}/.env"

: "${DEPLOYMENT_WAIT_TIMEOUT_SECONDS:=600}"
export DEPLOYMENT_WAIT_TIMEOUT_SECONDS

for dependency in kubectl docker envsubst curl; do
  if ! command -v "$dependency" >/dev/null 2>&1; then
    echo "Missing required dependency: $dependency" >&2
    exit 1
  fi
done

# --- Build & push custom images ---
./deploy/build-images.sh
./deploy/push-images.sh

# --- Secrets ---
./deploy/prepare-registry-secrets.sh || true
./deploy/prepare-k8s-secrets.sh

# --- Render manifests ---
mkdir -p k8s/rendered

RENDER_VARS='${IMAGE_TAG} ${KEYCLOAK_ADMIN} ${KEYCLOAK_CLIENT_SECRET} ${KEYCLOAK_HOST} ${KEYCLOAK_REALM} ${KEYCLOAK_TLS_SECRET_NAME} ${LETSENCRYPT_EMAIL} ${NAMESPACE} ${OPENAI_EMBEDDING_MODEL} ${OPENWEBUI_HOST} ${OPENWEBUI_IMAGE} ${PIPELINES_IMAGE} ${REGISTRY} ${SCW_LLM_BASE_URL} ${SCW_LLM_MODEL} ${SEARXNG_HOST} ${SEARXNG_IMAGE} ${SEARXNG_TLS_SECRET_NAME} ${TLS_SECRET_NAME} ${VALKEY_IMAGE}'

render_file() {
  local source_file="$1"
  local target_file="k8s/rendered/$(basename "$source_file")"
  envsubst "$RENDER_VARS" < "$source_file" > "$target_file"
}

# cert-manager
render_file cert-manager/clusterissuer-letsencrypt.yaml

# k8s manifests (skip examples and optional searxng ingress)
for manifest in k8s/base/*.yaml; do
  manifest_name="$(basename "$manifest")"
  [[ "$manifest_name" == "secret.example.yaml" ]] && continue
  [[ "$manifest_name" == "kustomization.yaml" ]] && continue
  [[ "$manifest_name" == "configmap-searxng.yaml" ]] && continue
  if [[ "$manifest_name" == "ingress-searxng.yaml" && -z "${SEARXNG_HOST:-}" ]]; then
    continue
  fi
  render_file "$manifest"
done

# Keycloak realm
if [[ -f scripts/render_keycloak_realm.py ]]; then
  python3 scripts/render_keycloak_realm.py \
    --source keycloak/realm-openwebui.k8s.json \
    --output k8s/rendered/realm-openwebui.json \
    --password-file keycloak/realm-passwords.local.json
fi

# SearXNG configmap
if [[ -f scripts/render_searxng_configmap.py ]]; then
  python3 scripts/render_searxng_configmap.py "$NAMESPACE" > k8s/rendered/configmap-searxng.yaml
fi

# Pipelines configmap
if [[ -f scripts/render_pipelines_configmap.py ]]; then
  python3 scripts/render_pipelines_configmap.py "$NAMESPACE" > k8s/rendered/configmap-pipelines.yaml
fi

# --- Apply manifests ---
echo "Applying namespace..."
kubectl apply -f k8s/rendered/namespace.yaml
kubectl apply -f k8s/rendered/clusterissuer-letsencrypt.yaml

echo "Applying PVCs..."
kubectl apply -f k8s/rendered/pvc-openwebui.yaml

echo "Applying configmaps..."
kubectl apply -f k8s/rendered/configmap.yaml
[[ -f k8s/rendered/configmap-searxng.yaml ]] && kubectl apply -f k8s/rendered/configmap-searxng.yaml
[[ -f k8s/rendered/configmap-pipelines.yaml ]] && kubectl apply -f k8s/rendered/configmap-pipelines.yaml

# Keycloak realm configmap
if [[ -f k8s/rendered/realm-openwebui.json ]]; then
  kubectl -n "$NAMESPACE" create configmap keycloak-realm \
    --from-file=realm-openwebui.json=k8s/rendered/realm-openwebui.json \
    --dry-run=client -o yaml | kubectl apply -f -
fi

echo "Applying deployments and services..."
# Socle services
for svc in openwebui keycloak pipelines searxng valkey; do
  [[ -f "k8s/rendered/deployment-${svc}.yaml" ]] && kubectl apply -f "k8s/rendered/deployment-${svc}.yaml"
  [[ -f "k8s/rendered/service-${svc}.yaml" ]] && kubectl apply -f "k8s/rendered/service-${svc}.yaml"
done

echo "Applying ingresses..."
kubectl apply -f k8s/rendered/ingress-openwebui.yaml
kubectl apply -f k8s/rendered/ingress-keycloak.yaml
if [[ -n "${SEARXNG_HOST:-}" && -f k8s/rendered/ingress-searxng.yaml ]]; then
  kubectl apply -f k8s/rendered/ingress-searxng.yaml
fi

# Ensure-tools job
if [[ -f k8s/rendered/job-ensure-tools.yaml ]]; then
  kubectl -n "$NAMESPACE" delete job ensure-tools --ignore-not-found
  kubectl apply -f k8s/rendered/job-ensure-tools.yaml
fi

# Register-plugins cronjob
if [[ -f k8s/rendered/cronjob-register-plugins.yaml ]]; then
  kubectl apply -f k8s/rendered/cronjob-register-plugins.yaml
fi

# --- Wait for readiness ---
echo "Waiting for deployments to become available..."
for svc in openwebui keycloak pipelines searxng search-valkey; do
  if kubectl -n "$NAMESPACE" get deployment "$svc" >/dev/null 2>&1; then
    kubectl -n "$NAMESPACE" wait --for=condition=available "deployment/${svc}" \
      --timeout="${DEPLOYMENT_WAIT_TIMEOUT_SECONDS}s" || echo "Warning: ${svc} not ready"
  fi
done

echo ""
echo "=== Socle deployment complete ==="
kubectl -n "$NAMESPACE" get pods,svc,ingress
echo ""
echo "To deploy feature plugins, run: ./deploy/deploy-plugins.sh"
