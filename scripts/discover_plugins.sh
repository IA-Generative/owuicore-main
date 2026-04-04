#!/usr/bin/env bash
# Discover sibling repos that contain owui-plugin.yaml.
# Outputs one path per line (relative to the socle repo root).
#
# Discovery order:
#   1. PLUGIN_PATHS env var (comma-separated)
#   2. Sibling directories of this repo that contain owui-plugin.yaml
#
# Compatible with macOS and Linux.

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
    dir_real="$(cd "$dir" && pwd)"
    socle_real="$(cd "$SOCLE_DIR" && pwd)"
    [[ "$dir_real" == "$socle_real" ]] && continue

    if [[ -f "$dir/owui-plugin.yaml" ]]; then
        # Output relative path from socle (portable, no GNU realpath)
        python3 -c "import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))" "$dir_real" "$socle_real"
    fi
done
