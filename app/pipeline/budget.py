"""Budget planning and enforcement for pipeline runs.

Phase 1: BudgetPlan / plan_run_budget() — cost estimation.
Phase 2 (Wallet v2 / MVP-M1): hold / consume / release / refund / extend_hold / topup
  — idempotent, atomic, fail-closed ops backed by user_budget_wallets +
    wallet_operations tables.

Backward-compat shims: reserve_budget() and release_budget() delegate to the
new ops so existing callers are not broken.  Both are deprecated.
"""
from __future__ import annotations

import warnings
import uuid as _uuid_mod
from dataclasses import dataclass, field
from typing import Optional

import psycopg2.extras

from app.routers.v3.db import get_conn


# ---------------------------------------------------------------------------
# Phase 1 — cost estimation models
# ---------------------------------------------------------------------------

@dataclass
class RunBudgetIn:
    """Caller-supplied budget constraints for a single run."""
    research_type: str = "general"       # general | deep | quick
    complexity: str = "medium"           # low | medium | high
    search_scope: str = "search"         # search | deep_search | exhaustive
    quality_tier: str = "normal"         # draft | normal | premium
    priority: str = "normal"             # low | normal | high
    max_tool_calls: int = 30
    max_tokens: int = 100_000
    hard_limit_usd: Optional[float] = None


@dataclass
class BudgetPlan:
    """Estimated cost for a run, produced by plan_run_budget()."""
    estimated_cost_units: float
    max_tool_calls: int
    max_tokens: int
    hard_limit_usd: Optional[float]
    breakdown: dict = field(default_factory=dict)


# Cost multiplier tables (dimensionless "units")
_RESEARCH_TYPE_MULT = {"quick": 1.0, "general": 2.0, "deep": 4.0}
_COMPLEXITY_MULT = {"low": 1.5, "medium": 3.0, "high": 5.0}
_SEARCH_SCOPE_MULT = {"search": 2.0, "deep_search": 4.0, "exhaustive": 8.0}
_QUALITY_TIER_MULT = {"draft": 1.0, "normal": 1.5, "premium": 2.5}
_PRIORITY_MULT = {"low": 0.8, "normal": 1.0, "high": 1.2}


def estimate_cost(budget: RunBudgetIn) -> BudgetPlan:
    """Return a BudgetPlan with estimated_cost_units computed from multipliers."""
    rt = _RESEARCH_TYPE_MULT.get(budget.research_type, 2.0)
    cx = _COMPLEXITY_MULT.get(budget.complexity, 3.0)
    ss = _SEARCH_SCOPE_MULT.get(budget.search_scope, 2.0)
    qt = _QUALITY_TIER_MULT.get(budget.quality_tier, 1.5)
    pr = _PRIORITY_MULT.get(budget.priority, 1.0)

    units = rt * cx * ss * qt * pr

    return BudgetPlan(
        estimated_cost_units=units,
        max_tool_calls=budget.max_tool_calls,
        max_tokens=budget.max_tokens,
        hard_limit_usd=budget.hard_limit_usd,
        breakdown={
            "research_type_mult": rt,
            "complexity_mult": cx,
            "search_scope_mult": ss,
            "quality_tier_mult": qt,
            "priority_mult": pr,
        },
    )


def plan_run_budget(budget: RunBudgetIn) -> BudgetPlan:
    """Public alias used by agent.py and other callers."""
    return estimate_cost(budget)


# ---------------------------------------------------------------------------
# Phase 2 (Wallet v2) — result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class HoldResult:
    ok: bool
    hold_id: Optional[str]        # idempotency_key echoed back (UUID string)
    held_ru: int
    reason: Optional[str] = None  # "insufficient" | "below_floor" | "wallet_unavailable"


@dataclass
class ConsumeResult:
    ok: bool
    balance_after: int
    held_after: int
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_wallet(cur, user_id: str, org_id: str = "") -> None:
    """Auto-provision a wallet row with a 1000 RU starter balance."""
    cur.execute(
        """INSERT INTO user_budget_wallets (user_id, org_id, balance_ru, held_ru, spent_ru_lifetime)
           VALUES (%s, %s, 1000, 0, 0)
           ON CONFLICT (user_id) DO NOTHING""",
        (user_id, org_id or None),
    )


def _idempotency_hit(cur, user_id: str, idem_key: str) -> Optional[dict]:
    """Return prior wallet_operations row if idempotency_key already exists."""
    cur.execute(
        "SELECT * FROM wallet_operations WHERE user_id = %s AND idempotency_key = %s",
        (user_id, idem_key),
    )
    row = cur.fetchone()
    if row is None:
        return None
    # psycopg2 RealDictCursor returns a dict-like; normalise to plain dict
    if hasattr(row, "keys"):
        return dict(row)
    # plain tuple cursor: column order per CREATE TABLE definition
    keys = ["id", "user_id", "run_id", "idempotency_key", "op",
            "delta_ru", "balance_after", "held_after", "reason", "created_at"]
    return dict(zip(keys, row))


def _write_op(cur, user_id: str, run_id: Optional[str], idem_key: str,
              op: str, delta_ru: int, balance_after: int, held_after: int,
              reason: Optional[str]) -> None:
    cur.execute(
        """INSERT INTO wallet_operations
               (user_id, run_id, idempotency_key, op, delta_ru, balance_after, held_after, reason)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (user_id, run_id or None, idem_key, op, delta_ru, balance_after, held_after, reason),
    )


# ---------------------------------------------------------------------------
# Phase 2 (Wallet v2) — six wallet operations
# ---------------------------------------------------------------------------

def hold(user_id: str, run_id: str, p90_ru: int, idempotency_key: str) -> HoldResult:
    """Atomically reserve p90_ru from the user's wallet for a run.

    Checks:
    - available_ru (balance - held) >= p90_ru
    - (balance - p90_ru) >= floor_ru

    Returns HoldResult.  FAILS CLOSED on any DB error.
    """
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                _ensure_wallet(cur, user_id)

                # Idempotency check first
                prior = _idempotency_hit(cur, user_id, idempotency_key)
                if prior is not None:
                    return HoldResult(
                        ok=(prior["op"] == "hold"),
                        hold_id=prior["idempotency_key"],
                        held_ru=prior["held_after"],
                        reason=prior["reason"],
                    )

                # Atomic conditional UPDATE with row-level guard
                cur.execute(
                    """UPDATE user_budget_wallets
                          SET held_ru    = held_ru + %s,
                              version    = version + 1,
                              updated_at = now()
                        WHERE user_id = %s
                          AND (balance_ru - held_ru) >= %s
                          AND (balance_ru - %s) >= floor_ru
                       RETURNING balance_ru, held_ru""",
                    (p90_ru, user_id, p90_ru, p90_ru),
                )
                row = cur.fetchone()
                if row is None:
                    # Determine specific reason for rejection
                    cur.execute(
                        "SELECT balance_ru, held_ru, floor_ru FROM user_budget_wallets WHERE user_id = %s",
                        (user_id,),
                    )
                    w = cur.fetchone()
                    if w is not None and (w["balance_ru"] - w["held_ru"]) >= p90_ru:
                        reason = "below_floor"
                    else:
                        reason = "insufficient"
                    return HoldResult(ok=False, hold_id=None, held_ru=0, reason=reason)

                balance_after = int(row["balance_ru"])
                held_after = int(row["held_ru"])
                _write_op(cur, user_id, run_id, idempotency_key,
                          "hold", p90_ru, balance_after, held_after, None)
                return HoldResult(ok=True, hold_id=idempotency_key,
                                  held_ru=p90_ru, reason=None)
    except Exception:
        return HoldResult(ok=False, hold_id=None, held_ru=0, reason="wallet_unavailable")


def consume(user_id: str, run_id: str, phase_n: int,
            actual_ru: int, idempotency_key: str) -> ConsumeResult:
    """Commit actual RU usage for a phase: decrements both balance and held.

    FAILS CLOSED on DB error.
    """
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                prior = _idempotency_hit(cur, user_id, idempotency_key)
                if prior is not None:
                    return ConsumeResult(
                        ok=(prior["op"].startswith("consume")),
                        balance_after=prior["balance_after"],
                        held_after=prior["held_after"],
                        reason=prior["reason"],
                    )

                cur.execute(
                    """UPDATE user_budget_wallets
                          SET balance_ru        = GREATEST(0, balance_ru - %s),
                              held_ru           = GREATEST(0, held_ru - %s),
                              spent_ru_lifetime = spent_ru_lifetime + %s,
                              version           = version + 1,
                              updated_at        = now()
                        WHERE user_id = %s
                       RETURNING balance_ru, held_ru""",
                    (actual_ru, actual_ru, actual_ru, user_id),
                )
                row = cur.fetchone()
                if row is None:
                    return ConsumeResult(ok=False, balance_after=0, held_after=0,
                                        reason="wallet_not_found")

                balance_after = int(row["balance_ru"])
                held_after = int(row["held_ru"])
                op_label = f"consume_phase_{phase_n}"
                _write_op(cur, user_id, run_id, idempotency_key,
                          op_label, -actual_ru, balance_after, held_after, None)
                return ConsumeResult(ok=True, balance_after=balance_after,
                                     held_after=held_after)
    except Exception:
        return ConsumeResult(ok=False, balance_after=0, held_after=0,
                             reason="wallet_unavailable")


def release(user_id: str, run_id: str, remaining_ru: int,
            idempotency_key: str) -> None:
    """Release the unconsumed portion of a hold back to spendable balance.

    Does not alter balance_ru — only reduces held_ru.
    Best-effort: DB errors are swallowed; orphan watchdog handles stuck held_ru.
    """
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                prior = _idempotency_hit(cur, user_id, idempotency_key)
                if prior is not None:
                    return  # already released

                cur.execute(
                    """UPDATE user_budget_wallets
                          SET held_ru    = GREATEST(0, held_ru - %s),
                              version    = version + 1,
                              updated_at = now()
                        WHERE user_id = %s
                       RETURNING balance_ru, held_ru""",
                    (remaining_ru, user_id),
                )
                row = cur.fetchone()
                if row is None:
                    return

                _write_op(cur, user_id, run_id, idempotency_key,
                          "release", -remaining_ru,
                          int(row["balance_ru"]), int(row["held_ru"]), None)
    except Exception:
        pass  # release is best-effort; watchdog job handles orphaned holds


def refund(user_id: str, run_id: str, full_amount_ru: int,
           idempotency_key: str) -> None:
    """Fully refund a failed run: returns balance_ru and zeroes held portion.

    Best-effort on DB error — caller should log failures separately.
    """
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                prior = _idempotency_hit(cur, user_id, idempotency_key)
                if prior is not None:
                    return

                cur.execute(
                    """UPDATE user_budget_wallets
                          SET balance_ru = balance_ru + %s,
                              held_ru    = GREATEST(0, held_ru - %s),
                              version    = version + 1,
                              updated_at = now()
                        WHERE user_id = %s
                       RETURNING balance_ru, held_ru""",
                    (full_amount_ru, full_amount_ru, user_id),
                )
                row = cur.fetchone()
                if row is None:
                    return

                _write_op(cur, user_id, run_id, idempotency_key,
                          "refund", full_amount_ru,
                          int(row["balance_ru"]), int(row["held_ru"]), None)
    except Exception:
        pass


def extend_hold(user_id: str, run_id: str, additional_ru: int,
                idempotency_key: str) -> HoldResult:
    """Extend an in-flight hold by additional_ru if wallet allows.

    Same guard as hold: available_ru >= additional_ru AND post-hold >= floor_ru.
    FAILS CLOSED on DB error.
    """
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                prior = _idempotency_hit(cur, user_id, idempotency_key)
                if prior is not None:
                    return HoldResult(
                        ok=(prior["op"] == "extend_hold"),
                        hold_id=prior["idempotency_key"],
                        held_ru=prior["held_after"],
                        reason=prior["reason"],
                    )

                cur.execute(
                    """UPDATE user_budget_wallets
                          SET held_ru    = held_ru + %s,
                              version    = version + 1,
                              updated_at = now()
                        WHERE user_id = %s
                          AND (balance_ru - held_ru) >= %s
                          AND (balance_ru - %s) >= floor_ru
                       RETURNING balance_ru, held_ru""",
                    (additional_ru, user_id, additional_ru, additional_ru),
                )
                row = cur.fetchone()
                if row is None:
                    return HoldResult(ok=False, hold_id=None, held_ru=0,
                                      reason="insufficient")

                balance_after = int(row["balance_ru"])
                held_after = int(row["held_ru"])
                _write_op(cur, user_id, run_id, idempotency_key,
                          "extend_hold", additional_ru, balance_after, held_after, None)
                return HoldResult(ok=True, hold_id=idempotency_key,
                                  held_ru=additional_ru, reason=None)
    except Exception:
        return HoldResult(ok=False, hold_id=None, held_ru=0, reason="wallet_unavailable")


def topup(user_id: str, amount_ru: int, payment_ref: str,
          idempotency_key: str) -> None:
    """Credit amount_ru to user's wallet (manual top-up flow).

    Idempotent: safe to retry on webhook re-delivery.
    Re-raises DB errors so the webhook handler can 5xx and retry.
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            _ensure_wallet(cur, user_id)

            prior = _idempotency_hit(cur, user_id, idempotency_key)
            if prior is not None:
                return

            cur.execute(
                """UPDATE user_budget_wallets
                      SET balance_ru  = balance_ru + %s,
                          version     = version + 1,
                          updated_at  = now()
                    WHERE user_id = %s
                   RETURNING balance_ru, held_ru""",
                (amount_ru, user_id),
            )
            row = cur.fetchone()
            if row is None:
                return

            _write_op(cur, user_id, None, idempotency_key,
                      "topup", amount_ru,
                      int(row["balance_ru"]), int(row["held_ru"]), payment_ref)


# ---------------------------------------------------------------------------
# Phase 2 legacy helpers (kept for budget admission check)
# ---------------------------------------------------------------------------

def estimate_run_cost(budget: RunBudgetIn) -> float:
    """Return estimated cost units for a run."""
    return estimate_cost(budget).estimated_cost_units


def check_admission(user_id: str, run_id: str, tool_call_count: int, max_tool_calls: int) -> bool:
    """Return False when the tool-call limit is exceeded for this run."""
    return tool_call_count < max_tool_calls


# ---------------------------------------------------------------------------
# Deprecated backward-compat shims
# ---------------------------------------------------------------------------

def reserve_budget(user_id: str, org_id: str, estimated_units: float) -> bool:
    """DEPRECATED. Use hold() instead.

    Wraps hold() with an auto-generated run_id and idempotency key.
    Returns True on success, False on failure.
    Unlike the old implementation, this FAILS CLOSED on DB errors.
    """
    warnings.warn(
        "reserve_budget() is deprecated; use hold() with an explicit run_id "
        "and idempotency_key.",
        DeprecationWarning,
        stacklevel=2,
    )
    run_id = str(_uuid_mod.uuid4())
    idem_key = f"reserve_budget__{user_id}__{estimated_units}__{run_id}"
    result = hold(user_id, run_id, int(estimated_units), idem_key)
    return result.ok


def release_budget(user_id: str, run_id: str, estimated_units: float,
                   actual_units: float) -> None:
    """DEPRECATED. Use consume() + release() instead.

    Consumes actual_units then releases any remaining hold.
    """
    warnings.warn(
        "release_budget() is deprecated; use consume() + release() separately.",
        DeprecationWarning,
        stacklevel=2,
    )
    consume_key = f"release_budget_consume__{user_id}__{run_id}"
    consume(user_id, run_id, 0, int(actual_units), consume_key)
    remaining = max(0, int(estimated_units) - int(actual_units))
    if remaining > 0:
        release_key = f"release_budget_release__{user_id}__{run_id}"
        release(user_id, run_id, remaining, release_key)
