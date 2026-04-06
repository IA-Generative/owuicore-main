#!/usr/bin/env bash
# Quick check of all SearXNG engines via the proxy
# Usage: ./scripts/check-search-engines.sh [query]
set -uo pipefail

SEARXNG_URL="${SEARXNG_URL:-http://localhost:8083}"
QUERY="${1:-test}"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo "Query: '$QUERY' via $SEARXNG_URL"
echo ""
printf "%-15s %-8s %-10s %s\n" "ENGINE" "STATUS" "RESULTS" "TIME"
printf "%-15s %-8s %-10s %s\n" "------" "------" "-------" "----"

for engine in google startpage qwant duckduckgo mojeek wikipedia bing braveapi; do
    start=$(python3 -c "import time; print(int(time.time()*1000))")
    result=$(curl -s --max-time 15 "${SEARXNG_URL}/search?q=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$QUERY")&format=json&engines=${engine}" 2>/dev/null)
    elapsed=$(( $(python3 -c "import time; print(int(time.time()*1000))") - start ))

    count=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('results',[])))" 2>/dev/null || echo "0")
    unresponsive=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('unresponsive_engines',[])))" 2>/dev/null || echo "?")

    if [ "$count" -gt 0 ] 2>/dev/null; then
        printf "${GREEN}%-15s %-8s %-10s %s${NC}\n" "$engine" "OK" "$count" "${elapsed}ms"
    elif [ "$unresponsive" = "1" ] 2>/dev/null; then
        printf "${RED}%-15s %-8s %-10s %s${NC}\n" "$engine" "BLOCKED" "0" "${elapsed}ms"
    else
        printf "${YELLOW}%-15s %-8s %-10s %s${NC}\n" "$engine" "EMPTY" "0" "${elapsed}ms"
    fi
done
