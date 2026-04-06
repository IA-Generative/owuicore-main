#!/usr/bin/env bash
# Deploy all feature plugins in Docker local mode
# Usage: ./deploy/deploy-plugins-docker.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARENT_DIR="$(dirname "$ROOT_DIR")"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[plugins]${NC} $*"; }
warn() { echo -e "${YELLOW}[plugins]${NC} $*"; }

# All plugin repos with docker-compose
PLUGINS=(
    "owuitools-dataview"
    "owuitools-websnap"
    "owuitools-tchapreader"
    "owuitools-gristmcp"
)

log "Deploying ${#PLUGINS[@]} plugins in Docker mode..."
echo ""

count=0
for plugin in "${PLUGINS[@]}"; do
    plugin_dir="${PARENT_DIR}/${plugin}"
    if [[ ! -d "$plugin_dir" ]]; then
        warn "Skip $plugin — not found"
        continue
    fi

    compose_file=""
    for f in docker-compose.yml docker-compose.yaml; do
        [[ -f "$plugin_dir/$f" ]] && compose_file="$f" && break
    done

    if [[ -z "$compose_file" ]]; then
        warn "Skip $plugin — no docker-compose"
        continue
    fi

    log "Building $plugin..."
    (cd "$plugin_dir" && docker compose up -d --build 2>&1 | tail -2)
    count=$((count + 1))
    echo ""
done

log "$count plugin(s) started"
echo ""

# Register tools in OWUI
log "Registering tools..."
(cd "$ROOT_DIR" && docker compose run --rm ensure-tools 2>&1 | grep -E "OK:|Done" | tail -15)

# Restart OWUI
log "Restarting OpenWebUI..."
docker restart owuicore-openwebui-1 2>/dev/null || true
sleep 10

log "All done. Services:"
for plugin in "${PLUGINS[@]}"; do
    container=$(docker ps --format "{{.Names}}\t{{.Status}}" 2>/dev/null | grep "$plugin" | head -1)
    if [[ -n "$container" ]]; then
        echo -e "  ${GREEN}✓${NC} $container"
    else
        echo -e "  ${YELLOW}✗${NC} $plugin — not running"
    fi
done
