"""Budget planning and enforcement for pipeline runs.

Phase 1: BudgetPlan / plan_run_budget() — cost estimation.
Phase 2: reserve_budget(), release_budget(), check_admission() — enforcement gates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


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
# Phase 2 — wallet enforcement helpers
# ---------------------------------------------------------------------------

def estimate_run_cost(budget: RunBudgetIn) -> float:
    """Return estimated cost units for a run."""
    return estimate_cost(budget).estimated_cost_units


def reserve_budget(user_id: str, org_id: str, estimated_units: float) -> bool:
    """Attempt to reserve budget from user wallet. Returns True if successful.

    Auto-provisions a wallet with 1000 units on first use. Uses an atomic
    UPDATE with a WHERE guard so two concurrent runs cannot both succeed if
    the balance is only sufficient for one.
    """
    from app.routers.v3.db import fetch_one, execute
    try:
        execute(
            "INSERT INTO user_budget_wallets (user_id, org_id) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING",
            (user_id, org_id),
        )
        row = fetch_one(
            """UPDATE user_budget_wallets
               SET reserved_units = reserved_units + %s,
                   updated_at = now()
               WHERE user_id = %s
                 AND (balance_units - reserved_units) >= %s
               RETURNING balance_units, reserved_units""",
            (estimated_units, user_id, estimated_units),
        )
        return row is not None
    except Exception:
        # Non-fatal: if DB is unreachable, allow run
        return True


def release_budget(user_id: str, run_id: str, estimated_units: float, actual_units: float) -> None:
    """Release reservation and debit actual spend at run completion."""
    from app.routers.v3.db import execute
    try:
        execute(
            """UPDATE user_budget_wallets
               SET reserved_units        = GREATEST(0, reserved_units - %s),
                   balance_units         = GREATEST(0, balance_units - %s),
                   spent_units_lifetime  = spent_units_lifetime + %s,
                   updated_at            = now()
               WHERE user_id = %s""",
            (estimated_units, actual_units, actual_units, user_id),
        )
    except Exception:
        pass  # Non-fatal


def check_admission(user_id: str, run_id: str, tool_call_count: int, max_tool_calls: int) -> bool:
    """Return False when the tool-call limit is exceeded for this run."""
    return tool_call_count < max_tool_calls
