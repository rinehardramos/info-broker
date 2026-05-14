#!/usr/bin/env bash
# dev.sh — rebuild, restart, and health-check the info-broker stack
#
# Usage:
#   ./dev.sh              — rebuild changed images + restart all services
#   ./dev.sh api          — rebuild + restart API only
#   ./dev.sh frontend     — rebuild + restart frontend only
#   ./dev.sh all          — force-rebuild ALL images (no cache) + restart
#   ./dev.sh restart      — restart without rebuilding (pick up volume changes)
#   ./dev.sh db           — run DB schema migrations only
#   ./dev.sh logs         — tail logs for all services
#   ./dev.sh logs api     — tail logs for a specific service
#   ./dev.sh status       — show container health

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

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
    2>&1 | grep -v "^time="
  ok "Migrations complete"
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
  echo "  Frontend   http://localhost:5173"
  echo "  API        http://localhost:8000/docs"
  echo "  Temporal   http://localhost:8233"
  echo ""
}

# ── Commands ──────────────────────────────────────────────────────────────────

cmd="${1:-}"

case "$cmd" in

  # ── Full rebuild + restart ─────────────────────────────────────────────────
  "" | "")
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

  # ── Logs ───────────────────────────────────────────────────────────────────
  "logs")
    svc="${2:-}"
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

  # ── Unknown ────────────────────────────────────────────────────────────────
  *)
    die "Unknown command: $cmd\nUsage: ./dev.sh [api|frontend|all|restart|db|logs|status]"
    ;;
esac
