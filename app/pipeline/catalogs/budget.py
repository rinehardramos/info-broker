"""BudgetEnvelope — the five-dial typed envelope for a single run.

This is NOT app/pipeline/budget.py (wallet operations / cost estimation for
existing pipeline runs).  This module encodes the user-facing dial semantics
from §5.2 of the three-tier brain architecture design.

The five dials:
    speed            slow | normal | fast | very_fast | extreme
    capability       light | general | high
    resource         tiny | light | medium | heavy | unlimited
    depth            shallow | search | deep | abyss
    hypothesis_count single | paired | competing | adversarial | swarm

Derived fields on BudgetEnvelope are estimated quantities computed by the
estimator (§5.3); they are filled in at preflight and frozen for the run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Allowed values per dial — single source of truth
# ---------------------------------------------------------------------------

SPEED_LEVELS: tuple[str, ...] = ("slow", "normal", "fast", "very_fast", "extreme")
CAPABILITY_LEVELS: tuple[str, ...] = ("light", "general", "high")
RESOURCE_LEVELS: tuple[str, ...] = ("tiny", "light", "medium", "heavy", "unlimited")
DEPTH_LEVELS: tuple[str, ...] = ("shallow", "search", "deep", "abyss")
HYPOTHESIS_COUNT_LEVELS: tuple[str, ...] = (
    "single",
    "paired",
    "competing",
    "adversarial",
    "swarm",
)

_DIAL_DOMAINS: dict[str, tuple[str, ...]] = {
    "speed": SPEED_LEVELS,
    "capability": CAPABILITY_LEVELS,
    "resource": RESOURCE_LEVELS,
    "depth": DEPTH_LEVELS,
    "hypothesis_count": HYPOTHESIS_COUNT_LEVELS,
}

# ---------------------------------------------------------------------------
# BudgetEnvelope
# ---------------------------------------------------------------------------


@dataclass
class BudgetEnvelope:
    """Typed envelope for the five dials + derived estimator fields.

    The five *dial* fields are validated at construction.
    The *derived* fields (estimated_ru, estimated_ru_p90, …) are populated by
    the preflight estimator and default to 0 / None until computed.

    Raises:
        ValueError: if any dial value is outside its allowed domain.
    """

    # ---- five dials --------------------------------------------------------
    speed: str = "normal"
    capability: str = "general"
    resource: str = "medium"
    depth: str = "search"
    hypothesis_count: str = "competing"

    # ---- optional mode label (from OptimizationMode.id) -------------------
    mode: Optional[str] = None

    # ---- derived / estimator fields ----------------------------------------
    estimated_ru: int = 0
    estimated_ru_p90: int = 0
    est_wall_time_s: int = 0
    est_branches: int = 0
    est_tool_calls: int = 0
    est_recurse_rounds: int = 0
    effort_score: float = 0.0
    cu_ceiling: int = 500           # hard cap in RU; default §5.4
    wall_clock_s: int = 1800        # hard wall-clock cap; default §5.4 (30 min)

    def __post_init__(self) -> None:
        self._validate_dials()

    def _validate_dials(self) -> None:
        for dial, domain in _DIAL_DOMAINS.items():
            value = getattr(self, dial)
            if value not in domain:
                raise ValueError(
                    f"Invalid value for dial '{dial}': '{value}'. "
                    f"Allowed: {domain}"
                )

    def as_dict(self) -> dict[str, object]:
        """Return the five dial values as a plain dict (for catalog serialization)."""
        return {
            "speed": self.speed,
            "capability": self.capability,
            "resource": self.resource,
            "depth": self.depth,
            "hypothesis_count": self.hypothesis_count,
        }


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def default_envelope() -> BudgetEnvelope:
    """Return the default BudgetEnvelope: (normal, general, medium, search, competing).

    This matches the preflight UI defaults shown in §6 of the design doc.
    """
    return BudgetEnvelope(
        speed="normal",
        capability="general",
        resource="medium",
        depth="search",
        hypothesis_count="competing",
    )
