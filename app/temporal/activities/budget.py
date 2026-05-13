"""Budget reservation/release activities."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from temporalio import activity

log = logging.getLogger(__name__)


@dataclass
class ReserveBudgetInput:
    run_id: str
    user_id: str
    org_id: str
    budget: dict  # raw RunBudgetIn payload


@dataclass
class ReservationResult:
    ok: bool
    reason: str = ""


@dataclass
class AbortInput:
    run_id: str
    user_id: str
    org_id: str
    reason: str
    callback_url: str | None = None


@activity.defn(name="reserve_budget")
async def reserve_budget(inp: ReserveBudgetInput) -> ReservationResult:
    """Reserve budget. Idempotent — short-circuits if already reserved."""
    from app.routers.v3.db import fetch_one
    # Idempotency check
    row = fetch_one(
        "SELECT budget_status FROM pipeline_runs WHERE id = %s",
        (inp.run_id,),
    )
    if row and row.get("budget_status") == "reserved":
        return ReservationResult(ok=True, reason="already_reserved")
    try:
        from app.pipeline.budget import RunBudgetIn, estimate_run_cost
        from app.pipeline.budget import reserve_budget as _reserve
        budget_in = RunBudgetIn(**inp.budget) if inp.budget else RunBudgetIn()
        estimated = estimate_run_cost(budget_in)
        ok = _reserve(inp.user_id, inp.org_id, estimated)
        return ReservationResult(ok=ok, reason="" if ok else "insufficient_balance")
    except Exception as exc:
        log.warning("reserve_budget failed (non-fatal): %s", exc)
        return ReservationResult(ok=True, reason="wallet_error_allow")


@activity.defn(name="release_budget_and_mark_failed")
async def release_budget_and_mark_failed(inp: AbortInput) -> None:
    """Release budget reservation and mark run as failed. Idempotent."""
    from app.routers.v3.db import execute, fetch_one
    row = fetch_one("SELECT status FROM pipeline_runs WHERE id = %s", (inp.run_id,))
    if row and row.get("status") in ("succeeded", "failed", "cancelled"):
        return  # Already terminal
    execute(
        """UPDATE pipeline_runs SET status = 'failed', finished_at = now(),
           error_message = %s, budget_status = 'released' WHERE id = %s""",
        (inp.reason, inp.run_id),
    )
    try:
        from app.pipeline.budget import release_budget as _release
        _release(inp.user_id, inp.run_id, 0, 0)
    except Exception:
        pass
    if inp.callback_url:
        try:
            from app.services.webhook import deliver_webhook
            import asyncio
            asyncio.create_task(deliver_webhook(
                inp.run_id, {"run_id": inp.run_id, "status": "failed", "reason": inp.reason},
                inp.callback_url,
            ))
        except Exception:
            pass
