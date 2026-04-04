#!/usr/bin/env bash
set -euo pipefail

BRIDGE_BASE_URL="${BRIDGE_BASE_URL:-http://localhost:${BRIDGE_PORT:-8081}}"
OPENWEBUI_BASE_URL="${OPENWEBUI_BASE_URL:-http://localhost:${OPENWEBUI_PORT:-3000}}"

echo "Checking bridge health at ${BRIDGE_BASE_URL}/healthz"
curl -fsS "${BRIDGE_BASE_URL}/healthz" >/dev/null

echo "Checking bridge query flow"
curl -fsS -X POST "${BRIDGE_BASE_URL}/query" \
  -H 'Content-Type: application/json' \
  -d '{"question":"What does this repository do?"}' >/dev/null

echo "Checking Open WebUI at ${OPENWEBUI_BASE_URL}"
curl -fsS -L "${OPENWEBUI_BASE_URL}" >/dev/null

echo "Smoke tests passed."

