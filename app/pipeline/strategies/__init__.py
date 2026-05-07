"""Investigation strategy modules — seed strategies per entity type.

Primary entry point: ``compile_strategy(entity_type)`` which returns
the seed strategy merged with learned overlays from the DB.
Use ``get_strategy(entity_type)`` for seed-only access.
"""
from __future__ import annotations

_STRATEGIES: dict[str, str] = {}

def get_strategy(entity_type: str) -> str:
    if not _STRATEGIES:
        _load_strategies()
    return _STRATEGIES.get(entity_type, "")

def _load_strategies() -> None:
    from app.pipeline.strategies.person import STRATEGY, ENTITY_TYPE
    _STRATEGIES[ENTITY_TYPE] = STRATEGY
