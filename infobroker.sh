#!/usr/bin/env bash
# infobroker.sh — manage the Info-Broker stack on the WSL home server.
#
# This box IS the production home server. The public surface is:
#   • infobroker.tech       → Cloudflare Pages (frontend; deploys on merge, NOT here)
#   • api.infobroker.tech   → host cloudflared tunnel → this stack's info-broker-api:8000
# The tunnel runs as a HOST service (not the docker `tunnel` profile), so a plain
# `up` is enough to restore api.infobroker.tech after a reboot.
#
# Usage:
#   ./infobroker.sh up [ui|graph]  — start the full stack (opt. profiles), wait healthy, migrate
#   ./infobroker.sh down           — stop & remove containers (volumes/data preserved)
#   ./infobroker.sh restart        — restart without rebuilding (pick up code/volume changes)
#   ./infobroker.sh build          — rebuild changed images (api + frontend) + restart
#   ./infobroker.sh api            — rebuild + restart API only, then migrate
#   ./infobroker.sh frontend       — rebuild + restart frontend only
#   ./infobroker.sh all            — force-rebuild ALL images (no cache) + restart
#   ./infobroker.sh db             — run DB schema migrations only
#   ./infobroker.sh health         — local + PUBLIC health checks + tunnel status
#   ./infobroker.sh tunnel         — show host cloudflared tunnel status + ingress
#   ./infobroker.sh status         — show container health + URLs
#   ./infobroker.sh logs [svc]     — tail logs (all app services, or one named service)
#   ./infobroker.sh clean          — prune regenerable junk (pycache, caches, test artifacts)

set -euo pipefail

export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Public domains served off this host.
PUBLIC_API="https://api.infobroker.tech"
PUBLIC_WEB="https://infobroker.tech"

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

log()  { echo -e "${CYAN}▶${RESET} $*"; }
ok()   { echo -e "${GREEN}✓${RESET} $*"; }
warn() { echo -e "${YELLOW}⚠${RESET} $*"; }
die()  { echo -e "${RED}✗${RESET} $*" >&2; exit 1; }

# ── Helpers ───────────────────────────────────────────────────────────────────

wait_healthy() {
  local svc="$1" max="${2:-60}" elapsed=0
  echo -n "  Waiting for $svc to be healthy"
  while [[ $elapsed -lt $max ]]; do
    local state
    state=$(docker inspect --format='{{.State.Health.Status}}' \
      "$(docker compose ps -q "$svc" 2>/dev/null)" 2>/dev/null || echo "none")
    if [[ "$state" == "healthy" ]]; then
      echo -e " ${GREEN}✓${RESET}"
      return 0
    fi
    echo -n "."
    sleep 2
    elapsed=$((elapsed + 2))
  done
  echo -e " ${YELLOW}timeout (service may still start)${RESET}"
}

run_migrations() {
  log "Running DB schema migrations..."
  docker compose exec info-broker-api python3 -c \
    "from app.routers.v3.db import run_migrations; run_migrations(); print('migrations ok')" \
    2>&1 | grep -v "^time=" || warn "migrations step reported an error (is the API up?)"
  ok "Migrations complete"
}

# curl a URL and print a coloured PASS/FAIL line. Args: label url [expected_substr]
check_url() {
  local label="$1" url="$2" want="${3:-}" body code
  body=$(curl -sS -m 15 -w $'\n%{http_code}' "$url" 2>/dev/null) || {
    echo -e "  ${RED}✗${RESET} ${label} — ${RED}unreachable${RESET} ($url)"; return 1; }
  code="${body##*$'\n'}"; body="${body%$'\n'*}"
  if [[ "$code" == "200" ]] && { [[ -z "$want" ]] || [[ "$body" == *"$want"* ]]; }; then
    echo -e "  ${GREEN}✓${RESET} ${label} — HTTP ${code} ${CYAN}${url}${RESET}"
  else
    echo -e "  ${RED}✗${RESET} ${label} — HTTP ${code} (expected 200${want:+ containing '$want'}) ${url}"
    return 1
  fi
}

tunnel_status() {
  echo -e "${BOLD}Cloudflare tunnel (host service):${RESET}"
  if systemctl is-active --quiet cloudflared 2>/dev/null; then
    echo -e "  ${GREEN}✓${RESET} cloudflared.service active (systemd)"
  elif pgrep -f "cloudflared.*tunnel run" >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓${RESET} cloudflared running (pid $(pgrep -f 'cloudflared.*tunnel run' | head -1))"
  else
    echo -e "  ${RED}✗${RESET} cloudflared NOT running — ${PUBLIC_API} will not resolve to this host"
    return 1
  fi
  echo "  ingress: api.infobroker.tech → http://localhost:8000"
}

show_status() {
  echo ""
  echo -e "${BOLD}Service status:${RESET}"
  docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null \
    | grep -v "^time="
  echo ""
}

show_urls() {
  echo -e "${BOLD}URLs:${RESET}"
  echo "  Frontend (local)   http://localhost:5173"
  echo "  API (local)        http://localhost:8000/docs"
  echo "  API (public)       ${PUBLIC_API}/healthz"
  echo "  Frontend (public)  ${PUBLIC_WEB}"
  # Temporal UI only exists when the `ui` profile is running.
  if docker compose ps --services --filter status=running 2>/dev/null | grep -qx temporal-ui; then
    echo "  Temporal UI        http://localhost:8233"
  fi
  echo ""
}

# ── Commands ──────────────────────────────────────────────────────────────────

cmd="${1:-}"; shift || true

case "$cmd" in

  # ── Start the stack (optional profiles) ────────────────────────────────────
  "up")
    PF=()
    for p in "$@"; do
      case "$p" in
        ui|graph|tunnel) PF+=(--profile "$p") ;;
        *) die "Unknown profile: $p (valid: ui, graph, tunnel)" ;;
      esac
    done
    log "Starting stack${*:+ with profiles: $*}..."
    docker compose ${PF[@]+"${PF[@]}"} up -d
    wait_healthy postgres 30
    wait_healthy info-broker-api 60
    sleep 3
    run_migrations
    show_status
    show_urls
    ok "Stack up"
    ;;

  # ── Stop & remove containers (data preserved) ──────────────────────────────
  "down")
    log "Stopping & removing containers (named volumes preserved)..."
    docker compose down
    ok "Stack down — postgres/qdrant/redis data volumes kept"
    ;;

  # ── Rebuild changed images + restart ───────────────────────────────────────
  "" | "build")
    log "Rebuilding changed images..."
    docker compose build info-broker-api frontend
    log "Restarting services..."
    docker compose up -d
    wait_healthy postgres 30
    wait_healthy info-broker-api 60
    sleep 3
    run_migrations
    show_status
    show_urls
    ok "Stack ready"
    ;;

  # ── API only ───────────────────────────────────────────────────────────────
  "api")
    log "Rebuilding API image..."
    docker compose build info-broker-api
    log "Restarting API..."
    docker compose up -d info-broker-api
    wait_healthy info-broker-api 60
    run_migrations
    ok "API restarted"
    ;;

  # ── Frontend only ──────────────────────────────────────────────────────────
  "frontend")
    log "Rebuilding frontend image..."
    docker compose build frontend
    log "Restarting frontend..."
    docker compose up -d frontend
    sleep 3
    ok "Frontend restarted — http://localhost:5173"
    ;;

  # ── Force rebuild everything (no cache) ────────────────────────────────────
  "all")
    warn "Force-rebuilding ALL images (no cache) — this takes a few minutes..."
    docker compose build --no-cache
    log "Restarting all services..."
    docker compose up -d
    wait_healthy postgres 30
    wait_healthy info-broker-api 60
    sleep 3
    run_migrations
    show_status
    show_urls
    ok "Full rebuild complete"
    ;;

  # ── Restart without rebuild (picks up volume/code changes) ─────────────────
  "restart")
    log "Restarting all services (no rebuild)..."
    docker compose restart
    wait_healthy info-broker-api 60
    ok "Services restarted"
    show_urls
    ;;

  # ── Migrations only ────────────────────────────────────────────────────────
  "db")
    run_migrations
    ;;

  # ── Health: local + public + tunnel ────────────────────────────────────────
  "health")
    rc=0
    echo -e "${BOLD}Local:${RESET}"
    check_url "API     /healthz" "http://localhost:8000/healthz" '"status":"ok"' || rc=1
    check_url "Frontend       " "http://localhost:5173/"                          || rc=1
    echo ""
    echo -e "${BOLD}Public (via Cloudflare):${RESET}"
    check_url "api.infobroker.tech/healthz" "${PUBLIC_API}/healthz" '"status":"ok"' || rc=1
    check_url "infobroker.tech            " "${PUBLIC_WEB}/"                        || rc=1
    echo ""
    tunnel_status || rc=1
    echo ""
    [[ $rc -eq 0 ]] && ok "All health checks passed" || die "One or more health checks FAILED"
    ;;

  # ── Tunnel status only ─────────────────────────────────────────────────────
  "tunnel")
    tunnel_status
    ;;

  # ── Logs ───────────────────────────────────────────────────────────────────
  "logs")
    svc="${1:-}"
    if [[ -n "$svc" ]]; then
      docker compose logs -f "$svc"
    else
      docker compose logs -f info-broker-api frontend
    fi
    ;;

  # ── Status ─────────────────────────────────────────────────────────────────
  "status")
    show_status
    show_urls
    ;;

  # ── Prune regenerable junk ─────────────────────────────────────────────────
  "clean")
    log "Pruning regenerable artifacts (gitignored — safe)..."
    find . -path ./frontend/node_modules -prune -o -type d -name __pycache__ -print0 2>/dev/null \
      | xargs -0 rm -rf 2>/dev/null || true
    rm -rf .pytest_cache .ruff_cache 2>/dev/null || true
    rm -f test-results/*.json 2>/dev/null || true
    ok "Cleaned __pycache__, .pytest_cache, .ruff_cache, test-results/*.json"
    ;;

  # ── Help / unknown ─────────────────────────────────────────────────────────
  "help" | "-h" | "--help")
    grep -E '^#( |$)' "$0" | sed -E 's/^# ?//'
    ;;
  *)
    die "Unknown command: $cmd\nRun ./infobroker.sh help for usage."
    ;;
esac
