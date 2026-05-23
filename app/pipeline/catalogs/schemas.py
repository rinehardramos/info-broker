"""Pydantic v2 schemas for the four catalogs: Strategy, Tactic, Technique, OptimizationMode.

Design references:
- §4 (Four Catalogs) of docs/intelligence/three-tier-brain-architecture.md
- §5.2 (Five Dials) — BudgetEnvelope imported from .budget
- §7 (Runtime Roles) — isolation contracts encoded in unit_of_work_contract / task specs

NOTE: This module defines the schema for the *new* catalog system only.
It does NOT touch app/pipeline/strategies/ (existing prose strategies) or
app/pipeline/budget.py (wallet ops).
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Shared leaf schemas
# ---------------------------------------------------------------------------


class CheckSpec(BaseModel):
    """A single gate check encoded as kind + params dict.

    Examples::

        CheckSpec(kind="distinct_identity_count", params={"min": 3})
        CheckSpec(kind="live_source_per_hypothesis", params={"required": True})
    """

    kind: str
    params: dict[str, Any] = {}


class GateSpec(BaseModel):
    """Gate that runs after a phase completes.

    on_fail drives the strategist's replan authority (§8.2):
    - ``replan``      — strategist emits a new phase plan
    - ``swap_tactic`` — tactician retries with a different tactic
    - ``ask_user``    — surface disambiguation to the user
    - ``terminate``   — hard stop, return partial results
    """

    checks: list[CheckSpec]
    on_fail: Literal["replan", "swap_tactic", "ask_user", "terminate"]


# ---------------------------------------------------------------------------
# Strategy catalog schemas
# ---------------------------------------------------------------------------


class PhaseSpec(BaseModel):
    """Specification for a single phase in a strategy's DAG.

    ``depends_on`` ids must not form a cycle — enforced by Strategy's validator.
    ``hypothesis_count_policy`` controls how many parallel tacticians the
    strategist spawns for this phase.

    ``preferred_tactic_id`` is an optional override telling the resolver
    which tactic to pick for this phase, bypassing the default preference
    logic. The cross-reference check (does the tactic exist and declare
    phase_compatibility for this phase?) happens at startup audit time —
    see app/pipeline/catalogs/audit.py.
    """

    id: str
    depends_on: list[str] = []
    unit_of_work_contract: dict[str, Any]
    hypothesis_count_policy: Literal["from_dial", "fixed:1", "fixed:2", "fixed:3",
                                     "fixed:4", "fixed:5", "from_prior_phase"]
    gate: GateSpec
    preferred_tactic_id: str | None = None    # NEW

    @field_validator("hypothesis_count_policy", mode="before")
    @classmethod
    def _allow_fixed_n(cls, v: str) -> str:
        """Allow any ``fixed:N`` value while keeping the Literal base set."""
        if isinstance(v, str) and v.startswith("fixed:"):
            parts = v.split(":", 1)
            if len(parts) == 2 and parts[1].isdigit() and int(parts[1]) > 0:
                return v
        return v

    @field_validator("preferred_tactic_id")
    @classmethod
    def _validate_tactic_id_format(cls, v: str | None) -> str | None:
        """Format-only validation. Cross-reference happens in the startup audit."""
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("preferred_tactic_id, if set, must be a non-empty string after strip()")
        return v


class Strategy(BaseModel):
    """Top-level strategy catalog entry (§4.1).

    ``applies_to`` is a dict of query-classifier signals that select this
    strategy (e.g. ``{"entity_type": "media", "query_type": "identification"}``).

    ``budget_minimums`` is a plain dict keyed by the five dial names;
    specific enforcement is handled at runtime by the estimator.
    Storing as dict keeps the schema independent of BudgetEnvelope so
    catalog files can be validated without importing the budget module.
    """

    id: str
    applies_to: dict[str, Any]
    phases: list[PhaseSpec]
    default_mode: str
    budget_minimums: dict[str, Any]
    ach_signals: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("phases")
    @classmethod
    def _phases_not_empty(cls, v: list[PhaseSpec]) -> list[PhaseSpec]:
        if not v:
            raise ValueError("Strategy must define at least one phase")
        return v

    @model_validator(mode="after")
    def _no_dependency_cycles(self) -> "Strategy":
        """Topological sort — raises ValueError on cyclic depends_on."""
        phase_ids = {p.id for p in self.phases}
        # Check all depends_on references exist
        for phase in self.phases:
            for dep in phase.depends_on:
                if dep not in phase_ids:
                    raise ValueError(
                        f"Phase '{phase.id}' depends_on unknown phase '{dep}'"
                    )
        # Kahn's algorithm
        in_degree: dict[str, int] = {p.id: 0 for p in self.phases}
        adjacency: dict[str, list[str]] = {p.id: [] for p in self.phases}
        for phase in self.phases:
            for dep in phase.depends_on:
                adjacency[dep].append(phase.id)
                in_degree[phase.id] += 1

        queue = [pid for pid, deg in in_degree.items() if deg == 0]
        visited = 0
        while queue:
            node = queue.pop()
            visited += 1
            for neighbor in adjacency[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(self.phases):
            raise ValueError(
                "Strategy phase DAG contains a cycle in depends_on references"
            )
        return self


# ---------------------------------------------------------------------------
# Tactic catalog schemas
# ---------------------------------------------------------------------------


class TaskSpec(BaseModel):
    """A single task emitted by a tactician for a specialist to execute (§4.2).

    ``budget_ru`` is the estimated cost in Research Units for this task.
    ``fail_modes`` lists expected failure shapes (mirrors Technique.failure_modes).
    """

    technique_id: str
    params_template: dict[str, Any] = {}
    expect_schema: dict[str, Any] = {}
    fail_modes: list[str] = []
    budget_ru: int = 1


class Tactic(BaseModel):
    """Tactic catalog entry (§4.2).

    ``phase_compatibility`` is a list of phase ids this tactic may be used in.
    ``accepts`` is the unit_of_work_contract shape this tactic consumes.
    ``enforcement`` encodes tactic-level invariants (e.g. min_distinct_outputs).
    """

    id: str
    phase_compatibility: list[str]
    accepts: dict[str, Any]
    produces: list[TaskSpec]
    cost_class: Literal["cheap", "moderate", "expensive"]
    required_techniques: list[str] = []
    enforcement: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Technique catalog schemas
# ---------------------------------------------------------------------------


class Technique(BaseModel):
    """Technique catalog entry (§4.3).

    Wraps a single MCP tool with typed input/output contracts.
    Specialist validates the task spec, calls the tool, validates the response.
    No reasoning at this layer.
    """

    id: str
    tool_name: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    cost_class: str
    failure_modes: list[str] = []
    retry_policy: dict[str, Any] = {}
    actor_slug: str = ""
    cost_per_call_ru: int = 0


# ---------------------------------------------------------------------------
# Optimization mode catalog schemas
# ---------------------------------------------------------------------------


class OptimizationMode(BaseModel):
    """Optimization mode catalog entry (§4.4).

    ``dial_defaults`` maps the five dial names to their default values for
    this mode. Stored as a plain dict for the same reason as Strategy.budget_minimums.

    ``tactic_bias`` maps tactic ids to float selector weights (higher = preferred).
    ``strategy_suggestions`` is an ordered list of strategy ids the classifier
    should suggest when this mode is active.
    """

    id: str
    dial_defaults: dict[str, Any]
    tactic_bias: dict[str, float] = {}
    strategy_suggestions: list[str] = []
