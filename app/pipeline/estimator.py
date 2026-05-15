"""RU estimator for preflight — MVP heuristic with hand-tuned constants.

TODO (post-MVP): replace hand-tuned multipliers with calibrated values once
N>=100 real runs have been collected from agent_runs. See §12 of the design doc
(docs/intelligence/three-tier-brain-architecture.md).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.pipeline.catalogs.budget import BudgetEnvelope

# ---------------------------------------------------------------------------
# Base RU per strategy
# ---------------------------------------------------------------------------

_STRATEGY_BASE_RU: dict[str, int] = {
    "media_identification": 12,
}

_STRATEGY_BASE_TOOL_CALLS: dict[str, int] = {
    "media_identification": 10,
}

# ---------------------------------------------------------------------------
# Multiplier tables
# ---------------------------------------------------------------------------

_CAPABILITY_MULT: dict[str, float] = {
    "light": 0.5,
    "general": 1.0,
    "high": 1.8,
}

_HYPOTHESIS_MULT: dict[str, float] = {
    "single": 1.0,
    "paired": 1.5,
    "competing": 2.2,
    "adversarial": 3.5,
    "swarm": 5.5,
}

_DEPTH_MULT: dict[str, float] = {
    "shallow": 0.7,
    "search": 1.0,
    "deep": 1.6,
    "abyss": 2.5,
}

# Hypothesis count integer mapping (est_branches)
_HYPOTHESIS_INT: dict[str, int] = {
    "single": 1,
    "paired": 2,
    "competing": 3,
    "adversarial": 5,
    "swarm": 9,
}

# Average wall-time seconds per RU (rough baseline at general/search)
_WALL_TIME_PER_RU_S: float = 15.0


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class EstimateResult:
    estimated_ru: int
    estimated_ru_p90: int
    est_wall_time_s: int
    est_branches: int
    est_tool_calls: int


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_run(strategy_id: str, envelope: BudgetEnvelope) -> EstimateResult:
    """Return an EstimateResult for the given strategy + envelope.

    Formula:
        estimated_ru = base × cap_mult × hyp_mult × depth_mult
        estimated_ru_p90 = estimated_ru × 1.4
        est_branches = hypothesis_count integer
        est_tool_calls = base_tool_calls(strategy) × hyp_mult × 0.5
    """
    base_ru = _STRATEGY_BASE_RU.get(strategy_id, 12)
    base_tools = _STRATEGY_BASE_TOOL_CALLS.get(strategy_id, 10)

    cap_mult = _CAPABILITY_MULT.get(envelope.capability, 1.0)
    hyp_mult = _HYPOTHESIS_MULT.get(envelope.hypothesis_count, 2.2)
    depth_mult = _DEPTH_MULT.get(envelope.depth, 1.0)

    raw_ru = base_ru * cap_mult * hyp_mult * depth_mult
    estimated_ru = max(1, round(raw_ru))
    estimated_ru_p90 = max(estimated_ru + 1, round(raw_ru * 1.4))

    est_branches = _HYPOTHESIS_INT.get(envelope.hypothesis_count, 3)
    est_tool_calls = max(1, round(base_tools * hyp_mult * 0.5))
    est_wall_time_s = max(30, round(estimated_ru * _WALL_TIME_PER_RU_S))

    return EstimateResult(
        estimated_ru=estimated_ru,
        estimated_ru_p90=estimated_ru_p90,
        est_wall_time_s=est_wall_time_s,
        est_branches=est_branches,
        est_tool_calls=est_tool_calls,
    )
