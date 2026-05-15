"""Catalog-driven execution layer for the three-tier brain architecture.

Exposes four typed catalogs (Strategy, Tactic, Technique, OptimizationMode)
plus a BudgetEnvelope dataclass for the five dials.

Usage::

    from app.pipeline.catalogs.schemas import Strategy, Tactic, Technique, OptimizationMode
    from app.pipeline.catalogs.budget import BudgetEnvelope, default_envelope
    from app.pipeline.catalogs.loader import load_catalog

This package is independent of the existing ``app/pipeline/strategies/``
and ``app/pipeline/budget.py`` — it runs in parallel with them.
"""
from __future__ import annotations

from app.pipeline.catalogs.schemas import (
    CheckSpec,
    GateSpec,
    OptimizationMode,
    PhaseSpec,
    Strategy,
    TaskSpec,
    Tactic,
    Technique,
)
from app.pipeline.catalogs.budget import BudgetEnvelope, default_envelope
from app.pipeline.catalogs.loader import CatalogValidationError, load_catalog

__all__ = [
    "CheckSpec",
    "GateSpec",
    "OptimizationMode",
    "PhaseSpec",
    "Strategy",
    "TaskSpec",
    "Tactic",
    "Technique",
    "BudgetEnvelope",
    "default_envelope",
    "CatalogValidationError",
    "load_catalog",
]
