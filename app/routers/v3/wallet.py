"""Wallet router — UI-P4 + Enhancement 3.4.

Endpoints:
  GET  /v3/wallet                           — current wallet snapshot
  GET  /v3/wallet/transactions              — paginated wallet_operations audit log
  PUT  /v3/wallet/floor                     — update floor_ru
  GET  /v3/wallet/forecast                  — rolling burn rate + month-end projection
  GET  /v3/runs/{run_id}/cost_breakdown     — per-phase RU breakdown + wallet ops for a run

All endpoints require authentication. Read-only from budget.py's perspective —
this router never calls hold/consume/release/refund directly.

TODO (post-MVP): POST /v3/wallet/topup — initiate Stripe checkout session (arch P8)
TODO (post-MVP): PUT /v3/wallet/auto_topup — configure AutoTopupRule (arch P8)
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import fetch_one, fetch_all, get_conn
from app.pipeline import budget as _budget_ops  # for _ensure_wallet side-effect only

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v3/wallet", tags=["v3-wallet"])
runs_cost_router = APIRouter(prefix="/v3/runs", tags=["v3-runs-cost"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class WalletSnapshot(BaseModel):
    balance_ru: int
    held_ru: int
    available_ru: int
    floor_ru: int
    spent_ru_lifetime: int
    created_at: str
    version: int


class WalletTransaction(BaseModel):
    id: str
    operation: str
    amount_ru: int
    balance_before: int
    balance_after: int
    held_before: int
    held_after: int
    run_id: Optional[str]
    metadata: Optional[str]
    created_at: str


class WalletTransactionsOut(BaseModel):
    transactions: list[WalletTransaction]
    total: int


class FloorUpdateIn(BaseModel):
    floor_ru: int = Field(..., ge=0, description="Floor RU must be non-negative")


class ForecastOut(BaseModel):
    last_30d_consumed: int
    last_7d_consumed: int
    rolling_daily_avg: float
    month_end_projection: int
    days_until_floor_ru: Optional[int]


class PhaseBreakdown(BaseModel):
    phase_id: str
    ru_consumed: int
    n_tacticians: int


class TechniqueBreakdown(BaseModel):
    technique_id: str
    calls: int
    ru_estimate: int


class RunCostBreakdown(BaseModel):
    run_id: str
    total_ru: int
    status: str
    started_at: Optional[str]
    completed_at: Optional[str]
    by_phase: list[PhaseBreakdown]
    by_technique: list[TechniqueBreakdown]
    wallet_operations: list[dict]
    by_technique_note: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auto_provision(user_id: str) -> None:
    """Ensure wallet row exists; delegates to budget._ensure_wallet via a
    lightweight INSERT ... ON CONFLICT DO NOTHING pattern.
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO user_budget_wallets
                               (user_id, balance_ru, held_ru, spent_ru_lifetime)
                           VALUES (%s, 1000, 0, 0)
                           ON CONFLICT (user_id) DO NOTHING""",
                    (user_id,),
                )
    except Exception as exc:
        log.warning("wallet auto-provision failed for %s: %s", user_id, exc)


def _get_wallet_snapshot(user_id: str) -> dict:
    """Return wallet row, auto-provisioning if absent."""
    _auto_provision(user_id)
    row = fetch_one(
        """SELECT balance_ru, held_ru,
                  (balance_ru - held_ru) AS available_ru,
                  floor_ru,
                  COALESCE(spent_ru_lifetime, 0)::int AS spent_ru_lifetime,
                  created_at,
                  version
             FROM user_budget_wallets
            WHERE user_id = %s""",
        (user_id,),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return row


# ---------------------------------------------------------------------------
# GET /v3/wallet
# ---------------------------------------------------------------------------

@router.get("", response_model=WalletSnapshot)
def get_wallet(current_user: dict = Depends(get_current_user)):
    """Return the current user's wallet snapshot."""
    user_id = str(current_user["id"])
    row = _get_wallet_snapshot(user_id)
    return WalletSnapshot(
        balance_ru=int(row["balance_ru"]),
        held_ru=int(row["held_ru"]),
        available_ru=int(row["available_ru"]),
        floor_ru=int(row["floor_ru"]),
        spent_ru_lifetime=int(row["spent_ru_lifetime"]),
        created_at=str(row["created_at"]),
        version=int(row["version"]),
    )


# ---------------------------------------------------------------------------
# GET /v3/wallet/transactions
# ---------------------------------------------------------------------------

@router.get("/transactions", response_model=WalletTransactionsOut)
def get_wallet_transactions(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """Return paginated wallet_operations rows for the current user."""
    user_id = str(current_user["id"])

    total_row = fetch_one(
        "SELECT COUNT(*) AS n FROM wallet_operations WHERE user_id = %s",
        (user_id,),
    )
    total = int(total_row["n"]) if total_row else 0

    rows = fetch_all(
        """SELECT id,
                  op              AS operation,
                  ABS(delta_ru)   AS amount_ru,
                  (balance_after - delta_ru) AS balance_before,
                  balance_after,
                  (held_after - delta_ru)    AS held_before,
                  held_after,
                  run_id,
                  reason          AS metadata,
                  created_at
             FROM wallet_operations
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s""",
        (user_id, limit, offset),
    )

    transactions = [
        WalletTransaction(
            id=str(r["id"]),
            operation=r["operation"],
            amount_ru=int(r["amount_ru"]),
            balance_before=int(r["balance_before"]),
            balance_after=int(r["balance_after"]),
            held_before=int(r["held_before"]),
            held_after=int(r["held_after"]),
            run_id=str(r["run_id"]) if r["run_id"] else None,
            metadata=r["metadata"],
            created_at=str(r["created_at"]),
        )
        for r in rows
    ]
    return WalletTransactionsOut(transactions=transactions, total=total)


# ---------------------------------------------------------------------------
# PUT /v3/wallet/floor
# ---------------------------------------------------------------------------

@router.put("/floor", response_model=WalletSnapshot)
def put_wallet_floor(
    body: FloorUpdateIn,
    current_user: dict = Depends(get_current_user),
):
    """Update floor_ru. Rejects negative values (Pydantic ge=0)."""
    user_id = str(current_user["id"])
    _auto_provision(user_id)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE user_budget_wallets
                          SET floor_ru   = %s,
                              version    = version + 1,
                              updated_at = now()
                        WHERE user_id = %s""",
                    (body.floor_ru, user_id),
                )
    except Exception as exc:
        log.error("floor update failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update floor")

    row = _get_wallet_snapshot(user_id)
    return WalletSnapshot(
        balance_ru=int(row["balance_ru"]),
        held_ru=int(row["held_ru"]),
        available_ru=int(row["available_ru"]),
        floor_ru=int(row["floor_ru"]),
        spent_ru_lifetime=int(row["spent_ru_lifetime"]),
        created_at=str(row["created_at"]),
        version=int(row["version"]),
    )


# ---------------------------------------------------------------------------
# GET /v3/wallet/forecast
# ---------------------------------------------------------------------------

@router.get("/forecast", response_model=ForecastOut)
def get_forecast(current_user: dict = Depends(get_current_user)):
    """Compute rolling burn rate and project month-end spend.

    Uses wallet_operations consume_* rows (negative delta_ru) to calculate
    actual RU consumed over the last 30 and 7 days.
    """
    user_id = str(current_user["id"])

    row_30d = fetch_one(
        """SELECT COALESCE(SUM(ABS(delta_ru)), 0)::int AS consumed
             FROM wallet_operations
            WHERE user_id = %s
              AND op LIKE 'consume%'
              AND created_at >= now() - INTERVAL '30 days'""",
        (user_id,),
    )
    row_7d = fetch_one(
        """SELECT COALESCE(SUM(ABS(delta_ru)), 0)::int AS consumed
             FROM wallet_operations
            WHERE user_id = %s
              AND op LIKE 'consume%'
              AND created_at >= now() - INTERVAL '7 days'""",
        (user_id,),
    )

    last_30d = int(row_30d["consumed"]) if row_30d else 0
    last_7d = int(row_7d["consumed"]) if row_7d else 0

    # Rolling daily average: prefer 7d if we have data (more recent); fallback 30d / 30
    if last_7d > 0:
        rolling_daily_avg = last_7d / 7.0
    elif last_30d > 0:
        rolling_daily_avg = last_30d / 30.0
    else:
        rolling_daily_avg = 0.0

    # Days remaining in the current calendar month
    import datetime
    today = datetime.date.today()
    # last day of current month
    if today.month == 12:
        last_day = datetime.date(today.year + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        last_day = datetime.date(today.year, today.month + 1, 1) - datetime.timedelta(days=1)
    days_remaining = (last_day - today).days + 1  # inclusive of today

    month_end_projection = last_30d + int(rolling_daily_avg * days_remaining)

    # Days until floor breach
    wallet_row = _get_wallet_snapshot(user_id)
    available_ru = int(wallet_row["available_ru"])
    floor_ru = int(wallet_row["floor_ru"])
    spendable_above_floor = max(0, available_ru - floor_ru)

    if rolling_daily_avg > 0 and spendable_above_floor >= 0:
        days_until_floor: Optional[int] = int(spendable_above_floor / rolling_daily_avg)
    else:
        days_until_floor = None

    return ForecastOut(
        last_30d_consumed=last_30d,
        last_7d_consumed=last_7d,
        rolling_daily_avg=round(rolling_daily_avg, 2),
        month_end_projection=month_end_projection,
        days_until_floor_ru=days_until_floor,
    )


# ---------------------------------------------------------------------------
# GET /v3/runs/{run_id}/cost_breakdown
# ---------------------------------------------------------------------------

@runs_cost_router.get("/{run_id}/cost_breakdown", response_model=RunCostBreakdown)
def get_run_cost_breakdown(
    run_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return RU breakdown for a single run.

    by_phase: aggregates consume_phase_N wallet_operations rows.
    by_technique: MVP placeholder — splits consumed RU evenly across techniques
      listed in the run's strategy. Real per-technique accounting is post-MVP.
      TODO (post-MVP): emit per-technique RU in wallet_operations metadata
        and aggregate here instead of using even-split placeholder.
    """
    user_id = str(current_user["id"])

    run = fetch_one(
        """SELECT id, status, started_at, finished_at, query, budget_plan
             FROM pipeline_runs
            WHERE id = %s AND user_id = %s""",
        (run_id, user_id),
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    # All wallet_operations for this run
    ops = fetch_all(
        """SELECT id, op, delta_ru, balance_after, held_after, reason, created_at, idempotency_key
             FROM wallet_operations
            WHERE run_id = %s
            ORDER BY created_at""",
        (run_id,),
    )

    # Total consumed = sum of absolute deltas of consume_* ops
    total_ru = sum(abs(int(o["delta_ru"])) for o in ops if o["op"].startswith("consume"))

    # by_phase: group consume_phase_N rows
    phase_map: dict[str, int] = {}
    for op in ops:
        if op["op"].startswith("consume_phase_"):
            phase_id = op["op"]  # e.g. "consume_phase_0"
            phase_map[phase_id] = phase_map.get(phase_id, 0) + abs(int(op["delta_ru"]))

    by_phase = [
        PhaseBreakdown(phase_id=pid, ru_consumed=ru, n_tacticians=1)
        for pid, ru in sorted(phase_map.items())
    ]

    # by_technique: MVP even-split placeholder
    # Pull technique names from budget_plan JSONB if present, otherwise use generic placeholder
    import json as _json
    technique_names: list[str] = []
    budget_plan = run.get("budget_plan")
    if budget_plan:
        try:
            bp = _json.loads(budget_plan) if isinstance(budget_plan, str) else budget_plan
            technique_names = bp.get("techniques", [])
        except Exception:
            pass

    if not technique_names:
        technique_names = ["web_search", "image_search", "prior_research"]

    n_techniques = len(technique_names)
    ru_per_technique = total_ru // n_techniques if n_techniques > 0 else 0
    remainder = total_ru - (ru_per_technique * n_techniques)

    by_technique = [
        TechniqueBreakdown(
            technique_id=t,
            calls=1,
            ru_estimate=ru_per_technique + (1 if i == 0 and remainder > 0 else 0),
        )
        for i, t in enumerate(technique_names)
    ]

    wallet_ops_out = [
        {
            "id": str(o["id"]),
            "op": o["op"],
            "delta_ru": int(o["delta_ru"]),
            "balance_after": int(o["balance_after"]),
            "held_after": int(o["held_after"]),
            "reason": o["reason"],
            "created_at": str(o["created_at"]),
        }
        for o in ops
    ]

    return RunCostBreakdown(
        run_id=run_id,
        total_ru=total_ru,
        status=run["status"],
        started_at=str(run["started_at"]) if run.get("started_at") else None,
        completed_at=str(run["finished_at"]) if run.get("finished_at") else None,
        by_phase=by_phase,
        by_technique=by_technique,
        wallet_operations=wallet_ops_out,
        by_technique_note=(
            "MVP placeholder: RU split evenly across techniques. "
            "TODO (post-MVP): emit per-technique RU in wallet_operations metadata "
            "for accurate per-technique accounting."
        ),
    )
