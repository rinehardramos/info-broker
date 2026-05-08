"""Investigation strategy modules — seed strategies per entity type.

Primary entry point: ``compile_strategy(entity_type)`` which returns
the seed strategy merged with learned overlays from the DB.
Use ``get_strategy(entity_type)`` for seed-only access.
"""
from __future__ import annotations

_STRATEGIES: dict[str, str] = {}

def get_strategy(entity_type: str, substrategy: str | None = None) -> str:
    if substrategy and substrategy != "none":
        from app.pipeline.strategies.domains.registry import get_substrategy
        text = get_substrategy(entity_type, substrategy)
        if text:
            return text
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
    # Generation variants
    from app.pipeline.strategies.product_innovation import STRATEGY as PRIS, ENTITY_TYPE as PRIT
    from app.pipeline.strategies.scientific_discovery import STRATEGY as SCDS, ENTITY_TYPE as SCDT
    from app.pipeline.strategies.engineering_rd import STRATEGY as ERDS, ENTITY_TYPE as ERDT
    # Prediction variants
    from app.pipeline.strategies.technology_forecast import STRATEGY as TFCS, ENTITY_TYPE as TFCT
    from app.pipeline.strategies.market_forecast import STRATEGY as MFCS, ENTITY_TYPE as MFCT
    # Explanation variants
    from app.pipeline.strategies.root_cause_analysis import STRATEGY as RCAS, ENTITY_TYPE as RCAT
    from app.pipeline.strategies.systems_analysis import STRATEGY as SYAS, ENTITY_TYPE as SYAT
    # Synthesis variants
    from app.pipeline.strategies.systematic_review import STRATEGY as SYRS, ENTITY_TYPE as SYRT
    from app.pipeline.strategies.strategic_assessment import STRATEGY as STAS, ENTITY_TYPE as STAT
    from app.pipeline.strategies.decision_analysis import STRATEGY as DAS, ENTITY_TYPE as DAT
    _STRATEGIES[PT] = PS
    _STRATEGIES[GT] = GS
    _STRATEGIES[ET] = ES
    _STRATEGIES[PRT] = PRS
    _STRATEGIES[ST] = SS
    _STRATEGIES[LT] = LS
    _STRATEGIES[RT2] = RS
    _STRATEGIES[CT] = CS
    _STRATEGIES[DDT] = DDS
    _STRATEGIES[PRIT] = PRIS
    _STRATEGIES[SCDT] = SCDS
    _STRATEGIES[ERDT] = ERDS
    _STRATEGIES[TFCT] = TFCS
    _STRATEGIES[MFCT] = MFCS
    _STRATEGIES[RCAT] = RCAS
    _STRATEGIES[SYAT] = SYAS
    _STRATEGIES[SYRT] = SYRS
    _STRATEGIES[STAT] = STAS
    _STRATEGIES[DAT] = DAS

    # Also register all sub-strategies discovered via the domains registry.
    # This populates _STRATEGIES with domain sub-strategy names so callers
    # using get_strategy("company") also resolve via the registry's STRATEGY text.
    _load_registry_strategies()

def _load_registry_strategies() -> None:
    """Load all sub-strategies from the domains registry into _STRATEGIES."""
    try:
        from app.pipeline.strategies.domains.registry import _get_registry
        registry = _get_registry()
        for _category, entries in registry.items():
            for name, entry in entries.items():
                # Only register if not already present (flat imports take precedence)
                if name not in _STRATEGIES:
                    _STRATEGIES[name] = entry["strategy"]
    except Exception:
        # Registry load is best-effort; flat imports already covered core strategies
        pass
