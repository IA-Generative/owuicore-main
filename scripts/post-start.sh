#!/usr/bin/env bash
# Post-start hook: waits for OWUI to be ready, then registers tools + MCP servers.
# Called by Docker healthcheck success or K8s post-start hook.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOCLE_DIR="$(dirname "$SCRIPT_DIR")"

MODE="${1:-docker}"
DB_PATH="${2:-}"

echo "[post-start] Ensuring tools are registered (mode=$MODE)..."

cd "$SOCLE_DIR"
python3 scripts/ensure_tools.py --mode "$MODE" --wait ${DB_PATH:+--db-path "$DB_PATH"}

echo "[post-start] Done."
