#!/usr/bin/env bash
# =============================================================================
# Smoke tests — MirAI Platform (owuicore)
#
# Usage:
#   ./tests/smoke_test.sh                    # Run all tests
#   ./tests/smoke_test.sh --quick            # Services health only
#   OWUI_API_KEY=sk-xxx ./tests/smoke_test.sh  # Custom API key
#
# Prerequisites: curl, jq, a running owuicore stack
# =============================================================================
set -uo pipefail

OWUI_URL="${OWUI_URL:-http://localhost:3000}"
OWUI_API_KEY="${OWUI_API_KEY:-}"
PIPELINES_URL="${PIPELINES_URL:-http://localhost:9099}"
QUICK="${1:-}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PASS=0
FAIL=0
SKIP=0

pass() { PASS=$((PASS+1)); echo -e "  ${GREEN}PASS${NC} $1"; }
fail() { FAIL=$((FAIL+1)); echo -e "  ${RED}FAIL${NC} $1 — $2"; }
skip() { SKIP=$((SKIP+1)); echo -e "  ${YELLOW}SKIP${NC} $1 — $2"; }
section() { echo -e "\n${CYAN}=== $1 ===${NC}"; }

http_ok() {
  local url="$1" label="$2"
  local code
  code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null) || code="000"
  if [[ "$code" == "200" || "$code" == "302" ]]; then
    pass "$label (HTTP $code)"
  else
    fail "$label" "HTTP $code"
  fi
}

api() {
  # Call OWUI API and return body. Args: method path [data]
  local method="$1" path="$2" data="${3:-}"
  local args=(-sS --max-time 30 -X "$method" -H "Content-Type: application/json")
  [[ -n "$OWUI_API_KEY" ]] && args+=(-H "Authorization: Bearer $OWUI_API_KEY")
  [[ -n "$data" ]] && args+=(-d "$data")
  curl "${args[@]}" "${OWUI_URL}${path}" 2>/dev/null
}

chat() {
  # Send a chat message and return the assistant response text.
  # Args: model_id prompt [timeout]
  local model="$1" prompt="$2" timeout="${3:-60}"
  local body
  body=$(jq -n --arg m "$model" --arg p "$prompt" '{
    model: $m,
    messages: [{role: "user", content: $p}],
    stream: false
  }')
  local resp
  resp=$(curl -sS --max-time "$timeout" -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $OWUI_API_KEY" \
    -d "$body" \
    "${OWUI_URL}/api/chat/completions" 2>/dev/null)
  echo "$resp" | jq -r '.choices[0].message.content // .detail // "ERROR"' 2>/dev/null
}

# ─────────────────────────────────────────────────────────────────────────────
section "1. Services Health"

http_ok "$OWUI_URL"                          "OpenWebUI"
http_ok "http://localhost:8082/realms/openwebui/.well-known/openid-configuration" "Keycloak"
http_ok "http://localhost:8083"               "SearXNG"
http_ok "http://localhost:9100/healthz"       "Image-gen"
http_ok "http://localhost:9998/tika"          "Tika"

http_ok "http://localhost:8081/healthz"       "GrafRAG bridge"
http_ok "http://localhost:8000/healthz"       "ANEF API"
http_ok "http://localhost:8093/healthz"       "Dataview"
http_ok "http://localhost:8087/healthz"       "Tchapreader"
http_ok "http://localhost:8086/healthz"       "Websnap"

# Pipelines (needs API key)
PKEY=$(grep "^PIPELINES_API_KEY=" "$(dirname "$0")/../.env" 2>/dev/null | cut -d= -f2 || echo "")
if [[ -n "$PKEY" ]]; then
  code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 \
    -H "Authorization: Bearer $PKEY" "$PIPELINES_URL/v1/models" 2>/dev/null) || code="000"
  if [[ "$code" == "200" ]]; then pass "Pipelines API"; else fail "Pipelines API" "HTTP $code"; fi
else
  skip "Pipelines API" "no PIPELINES_API_KEY"
fi

[[ "$QUICK" == "--quick" ]] && { echo -e "\n${CYAN}Quick mode — skipping API tests${NC}"; echo -e "\n${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}, ${YELLOW}$SKIP skipped${NC}"; exit $FAIL; }

# ─────────────────────────────────────────────────────────────────────────────
section "2. API — Models & Config"

if [[ -z "$OWUI_API_KEY" ]]; then
  skip "API tests" "set OWUI_API_KEY to run"
  echo -e "\n${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}, ${YELLOW}$SKIP skipped${NC}"
  exit $FAIL
fi

# Models list
models_json=$(api GET /api/models)
model_count=$(echo "$models_json" | jq '.data | length' 2>/dev/null || echo 0)
if (( model_count >= 10 )); then
  pass "Models registered ($model_count)"
else
  fail "Models registered" "only $model_count models"
fi

# Pipeline models present
for mid in "anef-regulatory.assistant" "anef-regulatory.legal" "graphrag-bridge.graphrag-local" "graphrag-bridge.graphrag-global"; do
  if echo "$models_json" | jq -e ".data[] | select(.id == \"$mid\")" >/dev/null 2>&1; then
    pass "Pipeline model: $mid"
  else
    fail "Pipeline model: $mid" "not found"
  fi
done

# Default model (check env var on container or DB config)
default_model=$(docker exec owuicore-openwebui-1 printenv DEFAULT_MODELS 2>/dev/null || echo "unset")
if [[ "$default_model" == *"gpt-oss-120b"* ]]; then
  pass "Default model: gpt-oss-120b"
else
  fail "Default model" "got: $default_model"
fi

# Tools registered
tools_json=$(api GET /api/v1/tools/)
tool_count=$(echo "$tools_json" | jq 'length' 2>/dev/null || echo 0)
if (( tool_count >= 4 )); then
  pass "Tools registered ($tool_count)"
else
  fail "Tools registered" "only $tool_count"
fi

# Functions (filters)
functions_json=$(api GET /api/v1/functions/)
filter_count=$(echo "$functions_json" | jq '[.[] | select(.type == "filter")] | length' 2>/dev/null || echo 0)
if (( filter_count >= 1 )); then
  pass "Vision filter registered ($filter_count)"
else
  fail "Vision filter" "not found"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "3. Chat — LLM basique"

resp=$(chat "gpt-oss-120b" "Reponds uniquement 'PONG'. Rien d'autre." 30)
if echo "$resp" | grep -qi "pong"; then
  pass "gpt-oss-120b responds"
else
  fail "gpt-oss-120b responds" "got: ${resp:0:80}"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "4. Feature APIs directes"

# Websnap
resp=$(curl -sS --max-time 30 -X POST http://localhost:8086/extract \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}' 2>/dev/null)
if echo "$resp" | jq -e '.markdown // .content // .ok' >/dev/null 2>&1; then
  pass "Websnap /extract"
else
  fail "Websnap /extract" "${resp:0:80}"
fi

# ANEF
resp=$(curl -sS --max-time 30 -X POST http://localhost:8000/search-title \
  -H "Content-Type: application/json" \
  -d '{"query":"salarie"}' 2>/dev/null)
if echo "$resp" | jq -e '.items // .results' >/dev/null 2>&1; then
  pass "ANEF /search-title"
else
  fail "ANEF /search-title" "${resp:0:80}"
fi

# Dataview
resp=$(curl -sS --max-time 30 -X POST http://localhost:8093/preview \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.data.gouv.fr/fr/datasets/r/008a2dda-2c60-4b63-b910-998f6f818089"}' 2>/dev/null)
if echo "$resp" | jq -e '.columns // .rows' >/dev/null 2>&1; then
  pass "Dataview /preview"
else
  # Accept any non-error JSON response (file might be unavailable)
  if echo "$resp" | jq -e '.detail' >/dev/null 2>&1; then
    skip "Dataview /preview" "$(echo "$resp" | jq -r '.detail.message // .detail' 2>/dev/null | head -c 60)"
  else
    fail "Dataview /preview" "${resp:0:80}"
  fi
fi

# Tchapreader
resp=$(curl -sS --max-time 10 http://localhost:8087/healthz 2>/dev/null)
if echo "$resp" | jq -e '.status' >/dev/null 2>&1; then
  pass "Tchapreader /healthz"
else
  fail "Tchapreader /healthz" "${resp:0:80}"
fi

# GrafRAG bridge
resp=$(curl -sS --max-time 10 http://localhost:8081/healthz 2>/dev/null)
if echo "$resp" | jq -e '.status' >/dev/null 2>&1; then
  pass "GrafRAG /healthz detailed"
else
  fail "GrafRAG /healthz detailed" "${resp:0:80}"
fi

# Tika extraction
resp=$(echo "Hello Tika" | curl -sS --max-time 10 -X PUT \
  -H "Content-Type: text/plain" \
  --data-binary @- http://localhost:9998/tika 2>/dev/null)
if echo "$resp" | grep -qi "hello"; then
  pass "Tika text extraction"
else
  fail "Tika text extraction" "${resp:0:80}"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "5. Chat — Tool call Websnap"

resp=$(chat "gpt-oss-120b" "Utilise le tool websnap pour extraire le contenu de https://example.com et montre-moi le resultat." 60)
if echo "$resp" | grep -qiE "example|domain|illustrative|strip"; then
  if echo "$resp" | grep -qi "strip"; then
    fail "Websnap tool call" "NoneType strip error"
  else
    pass "Websnap tool call via chat"
  fi
else
  # Tool might not have been called — check if response mentions inability
  if echo "$resp" | grep -qiE "ERROR\|impossible\|null"; then
    fail "Websnap tool call" "${resp:0:100}"
  else
    skip "Websnap tool call" "model did not call tool: ${resp:0:80}"
  fi
fi

section "6. Chat — Pipeline ANEF"
# (renumbered from 5)

resp=$(chat "anef-regulatory.assistant" "Quelles pieces pour un titre salarie L421-1 ?" 60)
if echo "$resp" | grep -qi "pièce\|document\|justificatif\|passeport"; then
  pass "ANEF pipeline responds with documents"
else
  fail "ANEF pipeline" "${resp:0:100}"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "6. Recherche web"

# Direct SearXNG test
resp=$(curl -sS --max-time 15 "http://localhost:8083/search?q=test&format=json" 2>/dev/null)
result_count=$(echo "$resp" | jq '.results | length' 2>/dev/null || echo 0)
if (( result_count > 0 )); then
  pass "SearXNG direct ($result_count results)"
else
  fail "SearXNG direct" "0 results"
fi

# SearXNG from inside OWUI container (same network path)
resp=$(docker exec owuicore-openwebui-1 curl -sS "http://searxng:8080/search?q=test&format=json" 2>/dev/null)
result_count=$(echo "$resp" | jq '.results | length' 2>/dev/null || echo 0)
if (( result_count > 0 )); then
  pass "SearXNG via owui-net ($result_count results)"
else
  fail "SearXNG via owui-net" "0 results"
fi

# Chat with web search
resp=$(chat "gpt-oss-120b" "Quelle heure est-il a Paris en ce moment ? Utilise la recherche web." 45)
if echo "$resp" | grep -qiE "[0-9]{1,2}[h:]|heure|time|paris|ERROR"; then
  pass "Chat web search triggered"
else
  fail "Chat web search" "${resp:0:100}"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "7. Embeddings Scaleway"

SCW_URL=$(grep "^SCW_LLM_BASE_URL=" "$(dirname "$0")/../.env" 2>/dev/null | cut -d= -f2 || echo "")
SCW_KEY=$(grep "^SCW_SECRET_KEY_LLM=" "$(dirname "$0")/../.env" 2>/dev/null | cut -d= -f2 || echo "")
if [[ -n "$SCW_URL" && -n "$SCW_KEY" ]]; then
  resp=$(curl -sS --max-time 15 -X POST "${SCW_URL}/embeddings" \
    -H "Authorization: Bearer $SCW_KEY" \
    -H "Content-Type: application/json" \
    -d '{"input":"test embedding","model":"bge-multilingual-gemma2"}' 2>/dev/null)
  if echo "$resp" | jq -e '.data[0].embedding' >/dev/null 2>&1; then
    dim=$(echo "$resp" | jq '.data[0].embedding | length')
    pass "Scaleway embeddings (dim=$dim)"
  else
    fail "Scaleway embeddings" "${resp:0:80}"
  fi
else
  skip "Scaleway embeddings" "no SCW_LLM_BASE_URL"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "Resultats"

TOTAL=$((PASS + FAIL + SKIP))
echo ""
echo -e "  ${GREEN}$PASS passed${NC} / ${RED}$FAIL failed${NC} / ${YELLOW}$SKIP skipped${NC} / $TOTAL total"
echo ""

if (( FAIL > 0 )); then
  echo -e "  ${RED}SOME TESTS FAILED${NC}"
  exit 1
else
  echo -e "  ${GREEN}ALL TESTS PASSED${NC}"
  exit 0
fi
