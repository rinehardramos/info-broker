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
    from app.pipeline.strategies.lead import STRATEGY as LS, ENTITY_TYPE as LT
    from app.pipeline.strategies.researcher import STRATEGY as RS, ENTITY_TYPE as RT2
    from app.pipeline.strategies.company import STRATEGY as CS, ENTITY_TYPE as CT
    from app.pipeline.strategies.due_diligence import STRATEGY as DDS, ENTITY_TYPE as DDT
    _STRATEGIES[PT] = PS
    _STRATEGIES[GT] = GS
    _STRATEGIES[ET] = ES
    _STRATEGIES[PRT] = PRS
    _STRATEGIES[ST] = SS
    _STRATEGIES[LT] = LS
    _STRATEGIES[RT2] = RS
    _STRATEGIES[CT] = CS
    _STRATEGIES[DDT] = DDS
