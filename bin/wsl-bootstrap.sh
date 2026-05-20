#!/usr/bin/env bash
# WSL2 / Linux first-run bootstrap for Info-Broker.
#
# Assumes:
#   - Docker Desktop is installed and running (with WSL2 backend on Windows)
#   - This script is run from the repo root inside WSL
#   - Repo lives in the WSL filesystem (NOT /mnt/c/...) for usable perf
#
# Usage:
#   ./bin/wsl-bootstrap.sh                # default profile (postgres+qdrant+temporal+workers+api+frontend)
#   ./bin/wsl-bootstrap.sh --with graph   # also start neo4j knowledge-graph service
#   ./bin/wsl-bootstrap.sh --with ui      # also start temporal-ui
#   ./bin/wsl-bootstrap.sh --with tunnel  # also start cloudflared (requires CLOUDFLARED_TOKEN in .env)

set -euo pipefail

# ─── Color helpers ───
RED=$(tput setaf 1 2>/dev/null || echo)
GREEN=$(tput setaf 2 2>/dev/null || echo)
YELLOW=$(tput setaf 3 2>/dev/null || echo)
BLUE=$(tput setaf 4 2>/dev/null || echo)
DIM=$(tput dim 2>/dev/null || echo)
RESET=$(tput sgr0 2>/dev/null || echo)

step()  { echo "${BLUE}▶${RESET} $*"; }
ok()    { echo "${GREEN}✓${RESET} $*"; }
warn()  { echo "${YELLOW}!${RESET} $*"; }
fail()  { echo "${RED}✗${RESET} $*"; exit 1; }

# ─── Parse args ───
PROFILES=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --with) PROFILES+=("--profile" "$2"); shift 2 ;;
    -h|--help) sed -n '2,15p' "$0" ; exit 0 ;;
    *) fail "Unknown arg: $1" ;;
  esac
done

# ─── Environment checks ───
step "Verifying environment"

if ! grep -qi microsoft /proc/version 2>/dev/null; then
  warn "Not running under WSL. This script also works on plain Linux."
fi

if ! command -v docker >/dev/null 2>&1; then
  fail "docker not on PATH. Install Docker Desktop (WSL integration enabled) and reopen shell."
fi

if ! docker info >/dev/null 2>&1; then
  fail "Docker daemon not reachable. Start Docker Desktop."
fi
ok "Docker reachable"

if [[ "$PWD" == /mnt/c/* ]] || [[ "$PWD" == /mnt/d/* ]]; then
  warn "Repo is on the Windows filesystem (${PWD}). Vite/Postgres will be 10-50x slower."
  warn "Strongly recommend cloning into the WSL filesystem (e.g. ~/projects/info-broker)."
fi

# ─── Memory budget hint ───
if [[ -r /proc/meminfo ]]; then
  TOTAL_MB=$(awk '/^MemTotal:/ {print int($2/1024)}' /proc/meminfo)
  if (( TOTAL_MB < 9000 )); then
    warn "WSL has only ${TOTAL_MB}MB RAM. Recommended 12GB+ — see docs/operations/wsl-getting-started.md for .wslconfig."
  else
    ok "WSL memory: ${TOTAL_MB}MB"
  fi
fi

# ─── .env ───
if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    ok "Created .env from .env.example — edit before continuing if you need API keys."
  else
    warn ".env not found and no .env.example to copy. Create .env with at minimum GEMINI_API_KEY."
  fi
fi

# ─── Claude Code creds discovery ───
step "Locating Claude Code credentials"

CLAUDE_CONFIG_DIR="${HOME}/.config/anthropic"
HAS_HOST_CREDS=0
if [[ -f "${CLAUDE_CONFIG_DIR}/credentials.json" ]]; then
  HAS_HOST_CREDS=1
  ok "Found host credentials at ${CLAUDE_CONFIG_DIR}/credentials.json"
fi

if [[ $HAS_HOST_CREDS -eq 0 ]] && ! grep -q '^CLAUDE_CODE_OAUTH_REFRESH_TOKEN=.\+' .env 2>/dev/null && ! grep -q '^ANTHROPIC_API_KEY=.\+' .env 2>/dev/null; then
  warn "No Claude credentials found."
  warn "Run one of:"
  warn "   1. claude auth login           (preferred — uses subscription)"
  warn "   2. echo 'ANTHROPIC_API_KEY=sk-ant-...' >> .env"
  warn "   3. echo 'CLAUDE_CODE_OAUTH_REFRESH_TOKEN=...' >> .env"
  warn "Continuing anyway — brain runs will fail until creds are configured."
fi

# Export so docker-compose picks it up when mounting
if [[ $HAS_HOST_CREDS -eq 1 ]]; then
  export CLAUDE_CREDS_DIR="${CLAUDE_CONFIG_DIR}"
fi

# ─── Pull images ───
step "Pulling images${PROFILES[*]:+ ($(IFS=, ; echo "${PROFILES[*]}"))}"
docker compose "${PROFILES[@]}" pull --quiet 2>&1 | grep -vE "^$|Pulling|Pulled" || true

# ─── Build local images ───
step "Building local images"
docker compose "${PROFILES[@]}" build --quiet 2>&1 | tail -10

# ─── Start stack ───
step "Starting stack (detached)"
docker compose "${PROFILES[@]}" up -d --remove-orphans

# ─── Wait for postgres ───
step "Waiting for Postgres to be ready"
for i in {1..30}; do
  if docker compose exec -T postgres pg_isready -U user -d info_broker >/dev/null 2>&1; then
    ok "Postgres ready"
    break
  fi
  sleep 1
  [[ $i -eq 30 ]] && fail "Postgres not ready after 30s"
done

# ─── Run migrations ───
if docker compose exec -T info-broker-api ls alembic.ini >/dev/null 2>&1; then
  step "Running Alembic migrations"
  docker compose exec -T info-broker-api alembic upgrade head 2>&1 | tail -10
fi

# ─── Health-check API ───
step "Health-checking API"
for i in {1..30}; do
  if curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then
    ok "API healthy"
    break
  fi
  sleep 1
  [[ $i -eq 30 ]] && warn "API not responding on http://localhost:8000/healthz — check logs"
done

# ─── Summary ───
echo
echo "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo "  ${GREEN}Info-Broker is up.${RESET}"
echo "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo
echo "  Frontend:    http://localhost:5173"
echo "  API:         http://localhost:8000"
echo "  API docs:    http://localhost:8000/docs"
if [[ " ${PROFILES[*]} " == *"ui"* ]]; then
  echo "  Temporal UI: http://localhost:8233"
fi
if [[ " ${PROFILES[*]} " == *"graph"* ]]; then
  echo "  Neo4j:       http://localhost:7474"
fi
echo
echo "  ${DIM}Logs: docker compose logs -f${RESET}"
echo "  ${DIM}Stop: docker compose down${RESET}"
echo
