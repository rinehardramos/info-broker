"""Startup audit for strategy/tactic catalog alignment.

Per spec 2026-05-23-research-skeleton-tactic-completion-design.md, the audit
ensures that:
  1. Every tactic declares only LEGAL_PHASE_IDS in its phase_compatibility.
  2. Every strategy phase has at least one compatible tactic.
  3. Every strategy phase's preferred_tactic_id (if set) refers to a tactic
     that IS compatible with that phase.

Failure modes are fail-CLOSED: run_audit_or_fail() raises and the API does
not boot until the catalog is fixed.

Pattern mirrors 629c161's gate-check audit (app/pipeline/strategist.py
audit_strategy_gates), but this audit is unconditionally strict — no
env-var escape hatch — because phase/tactic misalignment yields 0-work
runs that are user-facing failures (per PR #116).
"""
from __future__ import annotations

from typing import Any

from app.pipeline.catalogs.constants import LEGAL_PHASE_IDS


class StrategyTacticAuditError(RuntimeError):
    """Raised when the catalog has misaligned strategies/tactics at boot."""


def audit_strategy_tactic_alignment(
    strategies: dict[str, Any],
    tactics_catalog: dict[str, Any],
) -> list[str]:
    """Return a list of error strings. Empty list = audit passes.

    Args:
        strategies: dict mapping strategy_id → strategy object with .id and
            .phases (each phase has .id, .preferred_tactic_id).
        tactics_catalog: dict mapping tactic_id → tactic object with .id
            and .phase_compatibility (a list of phase ids).
    """
    errors: list[str] = []

    # Check 1: every tactic declares only legal phase ids
    for tid, tactic in tactics_catalog.items():
        phase_compat = _get_phase_compatibility(tactic)
        illegal = set(phase_compat) - LEGAL_PHASE_IDS
        if illegal:
            errors.append(
                f"tactic={tid}: phase_compatibility contains illegal ids "
                f"{sorted(illegal)}. Legal: {sorted(LEGAL_PHASE_IDS)}. "
                f"Hint: legacy phase ids (signal_extraction/broaden/red_team/"
                f"rank_verify) were retired in spec 2026-05-23."
            )

    # Check 2 & 3: every strategy phase has a compatible tactic + preferred_tactic_id valid
    for sid, strategy in strategies.items():
        phases = _get_phases(strategy)
        for phase in phases:
            phase_id = _get_phase_id(phase)
            preferred = _get_preferred_tactic_id(phase)
            compatible = sorted([
                tid for tid, t in tactics_catalog.items()
                if phase_id in _get_phase_compatibility(t)
            ])
            if not compatible:
                errors.append(
                    f"strategy={sid} phase={phase_id}: zero compatible tactics. "
                    f"Register a tactic whose phase_compatibility includes "
                    f"{phase_id!r} in app/pipeline/catalogs/registries/tactics/."
                )
            if preferred and preferred not in compatible:
                errors.append(
                    f"strategy={sid} phase={phase_id}: preferred_tactic_id="
                    f"{preferred!r} is not in the compatible set {compatible}. "
                    f"Either register {preferred} with phase_compatibility=[{phase_id!r}, ...] "
                    f"or remove the preferred_tactic_id override."
                )

    return errors


def run_audit_or_fail(
    strategies: dict[str, Any],
    tactics_catalog: dict[str, Any],
) -> None:
    """Raise StrategyTacticAuditError if the catalog is broken.

    Called at API boot from app/main.py. Logs and raises with a multi-line
    operator-actionable message.
    """
    errors = audit_strategy_tactic_alignment(strategies, tactics_catalog)
    if errors:
        msg = (
            "Strategy/tactic catalog audit FAILED (fail-CLOSED — see spec "
            "2026-05-23-research-skeleton-tactic-completion):\n\n"
            + "\n\n".join(f"  ✗ {e}" for e in errors)
            + "\n\nAPI will not start until the above are fixed."
        )
        raise StrategyTacticAuditError(msg)


# ---------------------------------------------------------------------------
# Helpers: accept both dict-style (legacy tactics) and dataclass-style
# (newer tactics use the `Tactic` Pydantic model). Some existing files
# declare TACTIC as a dict; others as a Tactic instance. Be tolerant.
# ---------------------------------------------------------------------------

def _get_phase_compatibility(tactic: Any) -> list[str]:
    if hasattr(tactic, "phase_compatibility"):
        return list(tactic.phase_compatibility)
    if isinstance(tactic, dict):
        return list(tactic.get("phase_compatibility", []))
    return []


def _get_phases(strategy: Any) -> list[Any]:
    if hasattr(strategy, "phases"):
        return list(strategy.phases)
    if isinstance(strategy, dict):
        return list(strategy.get("phases", []))
    return []


def _get_phase_id(phase: Any) -> str:
    if hasattr(phase, "id"):
        return phase.id
    if isinstance(phase, dict):
        return phase.get("id", "")
    return ""


def _get_preferred_tactic_id(phase: Any) -> str | None:
    if hasattr(phase, "preferred_tactic_id"):
        return phase.preferred_tactic_id
    if isinstance(phase, dict):
        return phase.get("preferred_tactic_id")
    return None
