#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# MetricStore Quick Start
# Spins up the stack, waits for it to be healthy, seeds sample metrics,
# and prints a getting-started summary.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

BOLD=$(tput bold 2>/dev/null || printf '')
RESET=$(tput sgr0 2>/dev/null || printf '')
GREEN=$(tput setaf 2 2>/dev/null || printf '')
CYAN=$(tput setaf 6 2>/dev/null || printf '')
YELLOW=$(tput setaf 3 2>/dev/null || printf '')

API_BASE="${METRICSTORE_URL:-http://localhost:8000}"
HEALTH_URL="${API_BASE}/health"
IMPORT_URL="${API_BASE}/api/v1/metrics/import/yaml"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXAMPLES_DIR="${SCRIPT_DIR}/../examples"

banner() { printf "\n${BOLD}${CYAN}▶  %s${RESET}\n" "$*"; }
ok()     { printf "${GREEN}✔  %s${RESET}\n" "$*"; }
warn()   { printf "${YELLOW}⚠  %s${RESET}\n" "$*"; }

# ── 1. Start the stack ────────────────────────────────────────────────────────
banner "Starting MetricStore with Docker Compose…"
docker compose up -d
ok "Containers started"

# ── 2. Wait for health check ──────────────────────────────────────────────────
banner "Waiting for MetricStore to be ready…"
MAX_WAIT=60
WAITED=0
until curl -sf "${HEALTH_URL}" > /dev/null 2>&1; do
  if (( WAITED >= MAX_WAIT )); then
    warn "Timed out after ${MAX_WAIT}s. Check logs: docker compose logs app"
    exit 1
  fi
  printf "."
  sleep 2
  WAITED=$(( WAITED + 2 ))
done
printf "\n"
ok "MetricStore is healthy (${WAITED}s)"

# ── 3. Run database migrations ────────────────────────────────────────────────
banner "Running database migrations…"
docker compose exec -T app alembic upgrade head 2>/dev/null \
  || warn "Migration step skipped (alembic may not be available in container path)"

# ── 4. Seed sample metrics ────────────────────────────────────────────────────
banner "Importing sample metrics from examples/sample_metrics.yaml…"

SAMPLE_FILE="${EXAMPLES_DIR}/sample_metrics.yaml"
if [[ ! -f "${SAMPLE_FILE}" ]]; then
  warn "Sample file not found: ${SAMPLE_FILE}"
  warn "Skipping seed step."
else
  HTTP_STATUS=$(
    curl -s -o /tmp/ms_import_response.json -w "%{http_code}" \
      -X POST "${IMPORT_URL}" \
      -H "Content-Type: application/yaml" \
      --data-binary "@${SAMPLE_FILE}"
  )

  if [[ "${HTTP_STATUS}" == "200" || "${HTTP_STATUS}" == "201" ]]; then
    IMPORTED=$(python3 -c \
      "import json,sys; d=json.load(open('/tmp/ms_import_response.json')); \
       print(d.get('imported', d.get('created', '?')))" 2>/dev/null || echo "?")
    ok "Imported ${IMPORTED} metrics (HTTP ${HTTP_STATUS})"
  else
    warn "Import returned HTTP ${HTTP_STATUS} — check /tmp/ms_import_response.json"
    cat /tmp/ms_import_response.json 2>/dev/null || true
  fi
fi

# ── 5. Print summary ──────────────────────────────────────────────────────────
METRIC_COUNT=$(
  curl -sf "${API_BASE}/api/v1/metrics?limit=1" 2>/dev/null \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('total', '?'))" \
    2>/dev/null || echo "?"
)

printf "\n"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
printf "${BOLD}MetricStore is running!${RESET}  ${METRIC_COUNT} metrics in your catalog.\n"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
printf "\n"
printf "  ${BOLD}REST API${RESET}      ${CYAN}${API_BASE}/docs${RESET}\n"
printf "  ${BOLD}MCP endpoint${RESET}  ${CYAN}${API_BASE}/mcp${RESET}\n"
printf "  ${BOLD}Health${RESET}        ${CYAN}${API_BASE}/health${RESET}\n"
printf "\n"
printf "${BOLD}Try it now:${RESET}\n"
printf "\n"
printf "  # List all metrics\n"
printf "  ${CYAN}curl -s '${API_BASE}/api/v1/metrics' | python3 -m json.tool | head -40${RESET}\n"
printf "\n"
printf "  # Search for revenue metrics\n"
printf "  ${CYAN}curl -s '${API_BASE}/api/v1/metrics?search=revenue' | python3 -m json.tool${RESET}\n"
printf "\n"
printf "  # Get a specific metric definition\n"
printf "  ${CYAN}curl -s '${API_BASE}/api/v1/metrics/mrr' | python3 -m json.tool${RESET}\n"
printf "\n"
printf "${BOLD}Connect Claude Desktop:${RESET}\n"
printf "  Copy ${CYAN}examples/claude_desktop_config.json${RESET} into your Claude Desktop config.\n"
printf "  Then ask Claude: \"What metrics does my company track for revenue?\"\n"
printf "\n"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
