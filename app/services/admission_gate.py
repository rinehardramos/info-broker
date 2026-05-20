"""
Pre-run admission gate.

Before any research run is dispatched to Temporal, this gate enforces:

  1. **Global concurrency** — total active runs across all users must be
     under GLOBAL_MAX_CONCURRENT (default 2, matching subscription quota +
     hardware capacity on a 16GB / 2-brain-worker host).
  2. **Per-user concurrency** — a single user may not have more than
     PER_USER_MAX_CONCURRENT active runs at once (default 1). Prevents
     one user from filling both global slots and starving others.
  3. **Daily cap** — per-user total runs in the last 24 hours under
     DAILY_RUN_CAP (default 30). Configurable per tier in D2.

On rejection, returns a structured AdmissionRejection that the HTTP layer
turns into a 429 with reason + retry-after + queue-position hint.

Bypasses (set GATE_ENABLED=false to disable; useful for tests and admin
emergency runs). Always-admitted user_ids are configured via
GATE_BYPASS_USER_IDS (comma-separated UUIDs).

Counts come from pipeline_runs.status IN ('queued', 'running'). This is the
source of truth; agent_sessions.run_count is denormalized and not relied on
here.

Slice D1 — single-tier hard caps. Slice D2 will add tier-based caps,
priority queues, queue-position estimates, WebSocket position updates.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Literal

from app.routers.v3.db import fetch_one

log = logging.getLogger(__name__)

# ── Configurable caps (env-overridable for ops) ───────────────────────────────
def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip())
    except (TypeError, ValueError):
        return default


GLOBAL_MAX_CONCURRENT = _int_env("GATE_GLOBAL_MAX_CONCURRENT", 2)
PER_USER_MAX_CONCURRENT = _int_env("GATE_PER_USER_MAX_CONCURRENT", 1)
DAILY_RUN_CAP = _int_env("GATE_DAILY_RUN_CAP", 30)
GATE_ENABLED = os.environ.get("GATE_ENABLED", "true").lower() != "false"
_BYPASS_RAW = os.environ.get("GATE_BYPASS_USER_IDS", "")
GATE_BYPASS_USER_IDS: set[str] = {
    u.strip() for u in _BYPASS_RAW.split(",") if u.strip()
}


# ── Decision types ────────────────────────────────────────────────────────────
RejectionReason = Literal[
    "global_concurrency_exhausted",
    "per_user_concurrency_exhausted",
    "daily_cap_exhausted",
]


@dataclass
class AdmissionDecision:
    admitted: bool
    reason: RejectionReason | None = None
    message: str = ""
    retry_after_seconds: int = 60
    global_active: int = 0
    user_active: int = 0
    user_runs_today: int = 0


# ── The gate ─────────────────────────────────────────────────────────────────
def check_admission(user_id: str) -> AdmissionDecision:
    """
    Decide whether a new run from this user can be admitted right now.

    Read-only against pipeline_runs. Safe to call from request-thread.
    """
    # Bypass disabled gate or explicit allow-list.
    if not GATE_ENABLED:
        return AdmissionDecision(admitted=True)
    if user_id in GATE_BYPASS_USER_IDS:
        return AdmissionDecision(admitted=True)

    counts = _count_active_and_recent(user_id)
    g_active = counts["global_active"]
    u_active = counts["user_active"]
    u_today = counts["user_runs_today"]

    # ── 1. Global concurrency ──
    if g_active >= GLOBAL_MAX_CONCURRENT:
        return AdmissionDecision(
            admitted=False,
            reason="global_concurrency_exhausted",
            message=(
                f"Server is busy: {g_active}/{GLOBAL_MAX_CONCURRENT} active runs. "
                "Try again in a minute, or submit and you'll be notified when capacity opens."
            ),
            retry_after_seconds=90,
            global_active=g_active,
            user_active=u_active,
            user_runs_today=u_today,
        )

    # ── 2. Per-user concurrency ──
    if u_active >= PER_USER_MAX_CONCURRENT:
        return AdmissionDecision(
            admitted=False,
            reason="per_user_concurrency_exhausted",
            message=(
                f"You have {u_active} active run(s) already. Wait for it to finish "
                "before starting another."
            ),
            retry_after_seconds=60,
            global_active=g_active,
            user_active=u_active,
            user_runs_today=u_today,
        )

    # ── 3. Daily cap ──
    if u_today >= DAILY_RUN_CAP:
        return AdmissionDecision(
            admitted=False,
            reason="daily_cap_exhausted",
            message=(
                f"Daily limit reached ({u_today}/{DAILY_RUN_CAP} runs in last 24h). "
                "Resets on a rolling 24-hour window."
            ),
            retry_after_seconds=3600,
            global_active=g_active,
            user_active=u_active,
            user_runs_today=u_today,
        )

    return AdmissionDecision(
        admitted=True,
        global_active=g_active,
        user_active=u_active,
        user_runs_today=u_today,
    )


# ── Internal: single DB roundtrip for all three counts ───────────────────────
def _count_active_and_recent(user_id: str) -> dict[str, int]:
    """One query, three counts. Cheaper than three separate calls."""
    try:
        row = fetch_one(
            """
            SELECT
                COUNT(*) FILTER (WHERE status IN ('queued', 'running'))             AS global_active,
                COUNT(*) FILTER (WHERE status IN ('queued', 'running') AND user_id = %s)
                                                                                    AS user_active,
                COUNT(*) FILTER (WHERE user_id = %s
                                  AND started_at > now() - interval '24 hours')     AS user_runs_today
            FROM pipeline_runs
            """,
            (user_id, user_id),
        )
    except Exception as exc:
        # If the DB read fails, fail OPEN (admit). Safer than blocking real
        # work behind a transient infra issue. Logged so it's visible.
        log.warning("admission gate: count query failed (%s) — admitting.", exc)
        return {"global_active": 0, "user_active": 0, "user_runs_today": 0}

    return {
        "global_active": int(row["global_active"] or 0),
        "user_active": int(row["user_active"] or 0),
        "user_runs_today": int(row["user_runs_today"] or 0),
    }


# ── Observability helper ──────────────────────────────────────────────────────
def gate_stats() -> dict:
    """Snapshot of gate config + current global counts. For burn-in + admin."""
    return {
        "enabled": GATE_ENABLED,
        "limits": {
            "global_max_concurrent": GLOBAL_MAX_CONCURRENT,
            "per_user_max_concurrent": PER_USER_MAX_CONCURRENT,
            "daily_run_cap": DAILY_RUN_CAP,
        },
        "bypass_user_ids": sorted(GATE_BYPASS_USER_IDS),
    }
