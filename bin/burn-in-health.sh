#!/usr/bin/env bash
# One-shot health snapshot for the loop-substrate burn-in.
# Run daily during the 30-day OLD-path phase-out window.
#
# Exit 0 if all signals are green, 1 otherwise. Useful in a cron + email/Slack.
#
# Usage:
#   ./bin/burn-in-health.sh          # human-readable report
#   ./bin/burn-in-health.sh --json   # machine-readable, for logging

set -euo pipefail

JSON=0
[[ "${1:-}" == "--json" ]] && JSON=1

# ─── Color helpers (skipped in JSON mode) ───
if [[ $JSON -eq 0 ]]; then
  GREEN=$(tput setaf 2 2>/dev/null || echo)
  RED=$(tput setaf 1 2>/dev/null || echo)
  YELLOW=$(tput setaf 3 2>/dev/null || echo)
  DIM=$(tput dim 2>/dev/null || echo)
  RESET=$(tput sgr0 2>/dev/null || echo)
fi

# ─── Stack alive? ───
if ! docker compose ps --format json 2>/dev/null | grep -q '"State":"running"'; then
  if [[ $JSON -eq 1 ]]; then
    echo '{"healthy":false,"reason":"stack_down"}'
  else
    echo "${RED}✗${RESET} Stack is not running. Bring it up with: docker compose up -d"
  fi
  exit 1
fi

# ─── Helper: run psql, return single value ───
psql_q() {
  docker compose exec -T postgres psql -U user -d info_broker -tA -c "$1" 2>/dev/null | tr -d '[:space:]'
}

# ─── Helper: count log matches in last 24h ───
log_count() {
  docker compose logs --since 24h "$1" 2>&1 | grep -cE "$2" || true
}

# ─── Gather signals ───

# 1. OLD-path warning fires (target: 0)
old_path_count=$(log_count info-broker-api "OLD single-shot brain path is active")

# 2. Loop run completion rate (target: ≥95%)
completed_24h=$(psql_q "SELECT count(*) FROM agent_sessions WHERE created_at > now() - interval '24 hours' AND status = 'completed'")
failed_24h=$(psql_q   "SELECT count(*) FROM agent_sessions WHERE created_at > now() - interval '24 hours' AND status = 'failed'")
total_24h=$(( ${completed_24h:-0} + ${failed_24h:-0} ))
if [[ $total_24h -eq 0 ]]; then
  completion_pct="n/a"
  completion_ok=1   # no runs is OK, just no signal
else
  completion_pct=$(( completed_24h * 100 / total_24h ))
  completion_ok=$(( completion_pct >= 95 ? 1 : 0 ))
fi

# 3. Working memory snapshots present (target: ≥3 per completed loop run)
wm_per_run=$(psql_q "
  SELECT COALESCE(round(avg(c)::numeric, 1), 0)
  FROM (
    SELECT count(*) AS c
    FROM working_memory_snapshots
    WHERE created_at > now() - interval '24 hours'
    GROUP BY run_id
  ) t
" || echo "0")
wm_ok=$(awk -v v="${wm_per_run:-0}" 'BEGIN{ exit !(v+0 >= 3) }' && echo 1 || echo 0)

# 4. Brain worker crash patterns (target: 0)
brain_errors=$(log_count is-temporal-worker "Traceback|UnhandledException|FATAL")

# 5. Brain p95 turn duration (target: <120s — soft signal)
p95_turn=$(psql_q "
  SELECT COALESCE(percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch from (created_at - lag_t))), 0)::int
  FROM (
    SELECT created_at, lag(created_at) OVER (PARTITION BY run_id ORDER BY turn) AS lag_t
    FROM working_memory_snapshots
    WHERE created_at > now() - interval '24 hours'
  ) t
  WHERE lag_t IS NOT NULL
" || echo "0")

# ─── Verdict ───
healthy=1
[[ "$old_path_count" -gt 0 ]] && healthy=0
[[ "$completion_ok" -eq 0 ]] && healthy=0
[[ "$wm_ok" -eq 0 ]] && [[ $total_24h -gt 0 ]] && healthy=0
[[ "$brain_errors" -gt 5 ]] && healthy=0

# ─── Output ───
if [[ $JSON -eq 1 ]]; then
  cat <<JSON
{
  "healthy": $([[ $healthy -eq 1 ]] && echo true || echo false),
  "old_path_warnings_24h": $old_path_count,
  "runs_24h": $total_24h,
  "completion_pct": "$completion_pct",
  "wm_snapshots_per_run_avg": "$wm_per_run",
  "brain_worker_errors_24h": $brain_errors,
  "turn_p95_seconds": $p95_turn
}
JSON
  exit $(( 1 - healthy ))
fi

# Human-readable
echo
echo "${DIM}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo "  Loop-substrate burn-in health · 24h window"
echo "${DIM}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

dot_ok()    { echo -n "${GREEN}●${RESET}"; }
dot_warn()  { echo -n "${YELLOW}●${RESET}"; }
dot_bad()   { echo -n "${RED}●${RESET}"; }

# OLD path
if [[ $old_path_count -eq 0 ]]; then dot_ok; else dot_bad; fi
echo "  OLD-path warning fired: $old_path_count time(s)"
[[ $old_path_count -gt 0 ]] && echo "     ${DIM}→ Loop is silently falling back. Check IS_USE_LOOP and logs.${RESET}"

# Completion
if [[ "$completion_pct" == "n/a" ]]; then dot_warn
elif [[ $completion_ok -eq 1 ]]; then dot_ok
else dot_bad
fi
echo "  Run completion rate: ${completion_pct}% (${completed_24h:-0}/${total_24h})"
[[ "$completion_pct" != "n/a" && $completion_ok -eq 0 ]] && echo "     ${DIM}→ Below 95% target. Investigate failed-run reasons.${RESET}"

# WM snapshots
if [[ $total_24h -eq 0 ]]; then dot_warn
elif [[ $wm_ok -eq 1 ]]; then dot_ok
else dot_bad
fi
echo "  Working-memory snapshots per run: avg ${wm_per_run:-0}"
[[ $total_24h -gt 0 && $wm_ok -eq 0 ]] && echo "     ${DIM}→ Below 3. Loop may be terminating early or not snapshotting.${RESET}"

# Brain errors
if [[ $brain_errors -eq 0 ]]; then dot_ok
elif [[ $brain_errors -le 5 ]]; then dot_warn
else dot_bad
fi
echo "  is-temporal-worker error/Traceback patterns: $brain_errors"
[[ $brain_errors -gt 5 ]] && echo "     ${DIM}→ docker compose logs --since 24h is-temporal-worker | less${RESET}"

# Turn duration
if [[ $p95_turn -eq 0 ]]; then dot_warn
elif [[ $p95_turn -lt 120 ]]; then dot_ok
else dot_warn
fi
echo "  Turn p95 duration: ${p95_turn}s ${DIM}(target <120s)${RESET}"

echo

if [[ $healthy -eq 1 ]]; then
  echo "  ${GREEN}Overall: HEALTHY${RESET}"
  exit 0
else
  echo "  ${RED}Overall: ATTENTION NEEDED${RESET}"
  echo "  ${DIM}Rollback option: set IS_USE_LOOP=false in .env, docker compose up -d${RESET}"
  exit 1
fi
