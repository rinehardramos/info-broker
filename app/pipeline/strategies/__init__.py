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
    from app.pipeline.strategies.person import STRATEGY as PS, ENTITY_TYPE as PT
    from app.pipeline.strategies.generation import STRATEGY as GS, ENTITY_TYPE as GT
    from app.pipeline.strategies.explanation import STRATEGY as ES, ENTITY_TYPE as ET
    from app.pipeline.strategies.prediction import STRATEGY as PRS, ENTITY_TYPE as PRT
    from app.pipeline.strategies.synthesis import STRATEGY as SS, ENTITY_TYPE as ST
    _STRATEGIES[PT] = PS
    _STRATEGIES[GT] = GS
    _STRATEGIES[ET] = ES
    _STRATEGIES[PRT] = PRS
    _STRATEGIES[ST] = SS
