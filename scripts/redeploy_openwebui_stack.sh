#!/usr/bin/env bash
# Redeploy the full OpenWebUI stack with all tools/skills.
#
# This script:
#   1. Delegates to anef-knowledge-assistant's redeploy (grafrag + ANEF)
#   2. Deploys all sidecar services (browser-use, tchap-reader, etc.)
#   3. Registers ALL tools/filters from manifest.yaml into OpenWebUI
#
# Usage:
#   bash scripts/redeploy_openwebui_stack.sh              # K8s (default)
#   bash scripts/redeploy_openwebui_stack.sh --docker      # Local Docker
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANEF_ROOT="${ANEF_ROOT:-${ROOT_DIR}/../anef-knowledge-assistant}"
BROWSER_USE_ROOT="${BROWSER_USE_ROOT:-${ROOT_DIR}/../browser-skill-owui}"
TCHAP_READER_ROOT="${TCHAP_READER_ROOT:-${ROOT_DIR}/../tchap-reader}"
MODE="${1:-k8s}"

export GRAFRAG_ROOT="${ROOT_DIR}"
export ANEF_ROOT

printf '╔══════════════════════════════════════════════════════════════╗\n'
printf '║  Full OpenWebUI Stack Redeploy                              ║\n'
printf '║  grafrag + ANEF + browser-use + tchap-reader + all tools    ║\n'
printf '╚══════════════════════════════════════════════════════════════╝\n\n'

# ── Step 1: Core stack (grafrag + ANEF) ───────────────────────
if [[ "${MODE}" == "--docker" || "${MODE}" == "docker" ]]; then
  printf '┌──────────────────────────────────────────────────────────┐\n'
  printf '│ [1/4] Restarting grafrag Docker stack                    │\n'
  printf '└──────────────────────────────────────────────────────────┘\n\n'
  (cd "${ROOT_DIR}" && docker compose pull && docker compose up -d --remove-orphans)
  printf 'Waiting for OpenWebUI...\n'
  for i in $(seq 1 60); do
    curl -sf "http://localhost:${OPENWEBUI_PORT:-3000}/api/version" >/dev/null 2>&1 && break
    sleep 2
  done
  curl -s "http://localhost:${OPENWEBUI_PORT:-3000}/api/version" && echo ""
else
  printf '┌──────────────────────────────────────────────────────────┐\n'
  printf '│ [1/4] Redeploying grafrag K8s stack (via ANEF)           │\n'
  printf '└──────────────────────────────────────────────────────────┘\n\n'
  if [[ -d "${ANEF_ROOT}" && -x "${ANEF_ROOT}/scripts/redeploy_openwebui_stack.sh" ]]; then
    bash "${ANEF_ROOT}/scripts/redeploy_openwebui_stack.sh" "$@"
  else
    printf 'WARNING: anef repository not found at %s\n' "${ANEF_ROOT}"
    printf 'Deploying grafrag K8s stack directly...\n'
    (cd "${ROOT_DIR}" && ./deploy/deploy-k8s.sh)
  fi
fi

# ── Step 2: Sidecar services ─────────────────────────────────
printf '\n┌──────────────────────────────────────────────────────────┐\n'
printf '│ [2/4] Deploying sidecar services                         │\n'
printf '└──────────────────────────────────────────────────────────┘\n\n'

# browser-use
if [[ -d "${BROWSER_USE_ROOT}" ]]; then
  printf '  browser-use: '
  if [[ "${MODE}" == "--docker" || "${MODE}" == "docker" ]]; then
    if [[ -x "${BROWSER_USE_ROOT}/scripts/deploy_docker.sh" ]]; then
      bash "${BROWSER_USE_ROOT}/scripts/deploy_docker.sh" 2>&1 | tail -1
    else
      printf 'deploy_docker.sh not found, skipping\n'
    fi
  else
    if [[ -x "${BROWSER_USE_ROOT}/scripts/deploy_k8s.sh" ]]; then
      bash "${BROWSER_USE_ROOT}/scripts/deploy_k8s.sh" 2>&1 | tail -1
    else
      printf 'deploy_k8s.sh not found, skipping\n'
    fi
  fi
else
  printf '  browser-use: not found at %s, skipping\n' "${BROWSER_USE_ROOT}"
fi

# tchap-reader
if [[ -d "${TCHAP_READER_ROOT}" ]]; then
  printf '  tchap-reader: '
  if [[ "${MODE}" == "--docker" || "${MODE}" == "docker" ]]; then
    if [[ -x "${TCHAP_READER_ROOT}/scripts/deploy_docker.sh" ]]; then
      bash "${TCHAP_READER_ROOT}/scripts/deploy_docker.sh" 2>&1 | tail -1
    else
      printf 'deploy_docker.sh not found, skipping\n'
    fi
  else
    if [[ -x "${TCHAP_READER_ROOT}/scripts/deploy_k8s.sh" ]]; then
      bash "${TCHAP_READER_ROOT}/scripts/deploy_k8s.sh" 2>&1 | tail -1
    else
      printf 'deploy_k8s.sh not found, skipping\n'
    fi
  fi
else
  printf '  tchap-reader: not found at %s, skipping\n' "${TCHAP_READER_ROOT}"
fi

# ── Step 3: Register ALL tools/filters + model config ────────
printf '\n┌──────────────────────────────────────────────────────────┐\n'
printf '│ [3/5] Registering all tools & filters in OpenWebUI       │\n'
printf '└──────────────────────────────────────────────────────────┘\n\n'

if [[ "${MODE}" == "--docker" || "${MODE}" == "docker" ]]; then
  python3 "${ROOT_DIR}/scripts/register_all_openwebui_tools.py" --mode docker
else
  NAMESPACE="${NAMESPACE:-grafrag}"
  python3 "${ROOT_DIR}/scripts/register_all_openwebui_tools.py" --mode k8s --namespace "${NAMESPACE}"
fi

# ── Step 4: Provision model aliases (preserves tool config) ──
printf '\n┌──────────────────────────────────────────────────────────┐\n'
printf '│ [4/5] Provisioning model aliases                         │\n'
printf '└──────────────────────────────────────────────────────────┘\n\n'

python3 "${ROOT_DIR}/scripts/provision_openwebui_model_aliases.py" 2>&1 || echo "  (model provisioning skipped)"

# ── Step 5: Verify ────────────────────────────────────────────
printf '\n┌──────────────────────────────────────────────────────────┐\n'
printf '│ [5/5] Verification                                       │\n'
printf '└──────────────────────────────────────────────────────────┘\n\n'

if [[ "${MODE}" == "--docker" || "${MODE}" == "docker" ]]; then
  printf '  OpenWebUI:     '; curl -s "http://localhost:${OPENWEBUI_PORT:-3000}/api/version" 2>/dev/null || echo "unreachable"
  printf '\n  browser-use:   '; curl -s "http://localhost:8086/healthz" 2>/dev/null || echo "unreachable"
  printf '\n  tchap-reader:  '; curl -s "http://localhost:8087/healthz" 2>/dev/null || echo "unreachable"
  echo ""

  # Verify tools are registered with correct owner
  DB_PATH="${ROOT_DIR}/openwebui/data/webui.db"
  if [[ -f "${DB_PATH}" ]]; then
    printf '  Tools registered:\n'
    sqlite3 "${DB_PATH}" "SELECT '    ✓ ' || id || ' (' || (SELECT count(*) FROM json_each(specs)) || ' methods)' FROM tool WHERE id IN ('browser_use', 'tchap_reader', 'tchap_admin');" 2>/dev/null || true
    printf '  Models with tools:\n'
    sqlite3 "${DB_PATH}" "SELECT '    ✓ ' || id || ' tools=' || json_extract(meta, '$.toolIds') FROM model WHERE json_extract(meta, '$.toolIds') IS NOT NULL;" 2>/dev/null || true
    echo ""
  fi
fi

printf '\n╔══════════════════════════════════════════════════════════════╗\n'
printf '║  Stack redeployed with all tools & model config!            ║\n'
printf '╚══════════════════════════════════════════════════════════════╝\n'
