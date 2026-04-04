#!/usr/bin/env bash
# Discover sibling repos that contain owui-plugin.yaml.
# Outputs one path per line (relative to the socle repo root).
#
# Discovery order:
#   1. PLUGIN_PATHS env var (comma-separated)
#   2. Sibling directories of this repo that contain owui-plugin.yaml

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOCLE_DIR="$(dirname "$SCRIPT_DIR")"
PARENT_DIR="$(dirname "$SOCLE_DIR")"

# 1. From env var
if [[ -n "${PLUGIN_PATHS:-}" ]]; then
    IFS=',' read -ra PATHS <<< "$PLUGIN_PATHS"
    for p in "${PATHS[@]}"; do
        p="$(echo "$p" | xargs)"  # trim
        [[ -n "$p" ]] && echo "$p"
    done
    exit 0
fi

# 2. Scan sibling directories
for dir in "$PARENT_DIR"/*/; do
    # Skip the socle itself
    [[ "$(realpath "$dir")" == "$(realpath "$SOCLE_DIR")" ]] && continue

    if [[ -f "$dir/owui-plugin.yaml" ]]; then
        # Output relative path from socle
        realpath --relative-to="$SOCLE_DIR" "$dir"
    fi
done
