"""Run budget planner: maps RunBudgetIn dimensions to concrete ExecutionLimits."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

SpeedT = Literal["slow", "normal", "fast", "very_fast", "extreme"]
CapabilityT = Literal["light", "general", "high"]
ResourceT = Literal["tiny", "light", "medium", "heavy", "unlimited"]
DepthT = Literal["shallow", "search", "deep", "abyss"]
VolumeT = Literal["low", "normal", "rich", "exhaustive"]
OptModeT = Literal[
    "general", "lead_generation", "market_analysis", "data_retrieval",
    "investigation", "academic_research", "due_diligence", "monitoring",
    "tabular_enrichment", "competitor_research",
]


@dataclass
class RunBudgetIn:
    speed: SpeedT = "normal"
    capability: CapabilityT = "general"
    resource: ResourceT = "medium"
    depth: DepthT = "search"
    volume: VolumeT = "normal"
    optimization_mode: OptModeT = "general"


@dataclass
class ExecutionLimits:
    max_depth: int
    max_branches: int
    max_tool_calls: int
    max_parallel_tools: int
    max_passes_per_branch: int
    timeout_seconds: int
    require_corroboration: bool
    hard_stop_on_exhaustion: bool


@dataclass
class ModelPlan:
    planning_model: str
    branch_model: str
    synthesis_model: str


@dataclass
class CostEstimate:
    estimated_cost_units: float
    estimated_runtime_band: str
    estimated_effort_label: str


@dataclass
class BudgetPlan:
    budget: RunBudgetIn
    execution_limits: ExecutionLimits
    model_plan: ModelPlan
    cost_estimate: CostEstimate
    effort_label: str


DEFAULT_BUDGET = RunBudgetIn()

# resource → (max_branches, max_tool_calls)
_RESOURCE_MAP: dict[str, tuple[int, int]] = {
    "tiny":      (2,   6),
    "light":     (6,   15),
    "medium":    (10,  30),
    "heavy":     (20,  60),
    "unlimited": (40, 120),
}
_DEPTH_MAP: dict[str, int] = {"shallow": 2, "search": 4, "deep": 5, "abyss": 7}
_VOLUME_MAP: dict[str, int] = {"low": 1, "normal": 2, "rich": 3, "exhaustive": 4}
_TIMEOUT_MAP: dict[str, int] = {
    "extreme": 120, "very_fast": 180, "fast": 300, "normal": 600, "slow": 900,
}
_PARALLEL_MAP: dict[str, int] = {
    "extreme": 8, "very_fast": 6, "fast": 4, "normal": 3, "slow": 2,
}
_RUNTIME_BAND: dict[str, str] = {
    "extreme": "<30s", "very_fast": "30s-1min", "fast": "1-3min",
    "normal": "2-8min", "slow": "5-15min",
}

_CAPABILITY_WEIGHT: dict[str, float] = {"light": 1.0, "general": 2.0, "high": 4.0}
_RESOURCE_WEIGHT: dict[str, int]   = {"tiny": 1, "light": 2, "medium": 3, "heavy": 5, "unlimited": 8}
_DEPTH_WEIGHT: dict[str, int]      = {"shallow": 1, "search": 2, "deep": 3, "abyss": 5}
_VOLUME_WEIGHT: dict[str, float]   = {"low": 1.0, "normal": 1.5, "rich": 2.0, "exhaustive": 3.0}
_SPEED_WEIGHT: dict[str, float]    = {
    "extreme": 0.7, "very_fast": 0.8, "fast": 0.9, "normal": 1.0, "slow": 1.2,
}

_MODEL_MAP: dict[str, tuple[str, str, str]] = {
    "light":   ("claude-haiku-4-5", "claude-haiku-4-5", "claude-haiku-4-5"),
    "general": ("claude-sonnet-4-6", "claude-haiku-4-5", "claude-sonnet-4-6"),
    "high":    ("claude-opus-4-7", "claude-sonnet-4-6", "claude-opus-4-7"),
}


def estimate_cost(budget: RunBudgetIn) -> CostEstimate:
    units = (
        _CAPABILITY_WEIGHT[budget.capability]
        * _RESOURCE_WEIGHT[budget.resource]
        * _DEPTH_WEIGHT[budget.depth]
        * _VOLUME_WEIGHT[budget.volume]
        * _SPEED_WEIGHT[budget.speed]
    )
    label = f"{budget.speed}-{budget.capability}-{budget.resource}-{budget.depth}"
    return CostEstimate(
        estimated_cost_units=round(units, 4),
        estimated_runtime_band=_RUNTIME_BAND[budget.speed],
        estimated_effort_label=label,
    )


def plan_run_budget(budget: RunBudgetIn) -> BudgetPlan:
    max_branches, max_tool_calls = _RESOURCE_MAP[budget.resource]
    planning, branch, synthesis = _MODEL_MAP[budget.capability]
    cost = estimate_cost(budget)
    limits = ExecutionLimits(
        max_depth=_DEPTH_MAP[budget.depth],
        max_branches=max_branches,
        max_tool_calls=max_tool_calls,
        max_parallel_tools=_PARALLEL_MAP[budget.speed],
        max_passes_per_branch=_VOLUME_MAP[budget.volume],
        timeout_seconds=_TIMEOUT_MAP[budget.speed],
        require_corroboration=(budget.volume in ("rich", "exhaustive")),
        hard_stop_on_exhaustion=True,
    )
    effort = f"{budget.speed}-{budget.capability}-{budget.resource}-{budget.depth}"
    return BudgetPlan(
        budget=budget,
        execution_limits=limits,
        model_plan=ModelPlan(
            planning_model=planning,
            branch_model=branch,
            synthesis_model=synthesis,
        ),
        cost_estimate=cost,
        effort_label=effort,
    )
