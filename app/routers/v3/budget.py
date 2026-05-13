"""Budget API: wallet, topup, ledger, estimate endpoints."""
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends
from app.routers.v3.auth import get_current_user
from app.routers.v3.db import fetch_one, fetch_all, execute
from app.routers.v3.tenancy import user_org_id
from app.pipeline.budget import RunBudgetIn, plan_run_budget

router = APIRouter(prefix="/v3/budget", tags=["budget"])


@router.get("/wallet")
def get_wallet(user: dict = Depends(get_current_user)):
    uid = str(user["id"])
    org = user_org_id(user)
    row = fetch_one("SELECT * FROM user_budget_wallets WHERE user_id = %s", (uid,))
    if not row:
        return {
            "user_id": uid,
            "org_id": org,
            "balance_units": 10000,
            "reserved_units": 0,
            "spent_units_lifetime": 0,
            "low_balance_threshold_units": 100,
            "stop_threshold_units": 0,
            "auto_topup_enabled": False,
        }
    return dict(row)


@router.post("/topup")
def topup(body: dict, user: dict = Depends(get_current_user)):
    uid = str(user["id"])
    amount = float(body.get("amount_units", 1000))
    execute(
        """INSERT INTO budget_ledger_entries
           (id, user_id, org_id, entry_type, units, balance_after_units)
           VALUES (%s, %s, %s, 'topup', %s, %s)""",
        (str(uuid.uuid4()), uid, user_org_id(user), amount, amount),
    )
    return {"status": "ok", "credited_units": amount}


@router.get("/ledger")
def get_ledger(user: dict = Depends(get_current_user)):
    uid = str(user["id"])
    rows = fetch_all(
        "SELECT * FROM budget_ledger_entries WHERE user_id = %s ORDER BY created_at DESC LIMIT 100",
        (uid,),
    )
    return [dict(r) for r in rows]


@router.post("/estimate")
def estimate(body: dict, user: dict = Depends(get_current_user)):
    budget = RunBudgetIn(
        speed=body.get("speed", "normal"),
        capability=body.get("capability", "general"),
        resource=body.get("resource", "medium"),
        depth=body.get("depth", "search"),
        volume=body.get("volume", "normal"),
        optimization_mode=body.get("optimization_mode", "general"),
    )
    plan = plan_run_budget(budget)
    cost = plan.cost_estimate
    return {
        "estimated_cost_units": cost.estimated_cost_units,
        "estimated_runtime_band": cost.estimated_runtime_band,
        "estimated_effort_label": plan.effort_label,
        "execution_limits": {
            "max_depth": plan.execution_limits.max_depth,
            "max_branches": plan.execution_limits.max_branches,
            "max_tool_calls": plan.execution_limits.max_tool_calls,
            "timeout_seconds": plan.execution_limits.timeout_seconds,
        },
        "model_plan": {
            "planning_model": plan.model_plan.planning_model,
            "synthesis_model": plan.model_plan.synthesis_model,
        },
    }
