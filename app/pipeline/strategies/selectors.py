"""Category selector lists for all 5 Universal Research Engine research types.

``CATEGORY_SELECTORS`` maps each category name to its ordered list of
selector strings.  ``get_selectors`` is the primary access point and
falls back to the person list for any unrecognised category.
"""
from __future__ import annotations

CATEGORY_SELECTORS: dict[str, list[str]] = {
    "person": ["full_name", "email", "phone", "username", "employer", "address", "photo"],
    "generation": ["problem_statement", "concept", "technique", "prior_art", "researcher", "constraint", "gap"],
    "prediction": ["signal", "trend", "driver", "uncertainty", "scenario", "weak_signal", "actor", "constraint"],
    "explanation": ["symptom", "hypothesis", "variable", "cause", "root_cause", "feedback_loop", "leverage_point", "evidence"],
    "synthesis": ["study", "framework", "criterion", "claim", "evidence", "perspective", "option"],
}

_FALLBACK = "person"


def get_selectors(entity_type: str, substrategy: str | None = None) -> list[str]:
    """Return the selector list for *entity_type*.

    If substrategy is provided, returns the domain-specific selector list
    when available, falling back to the base category selectors.
    Falls back to the ``person`` selector list for unknown categories.
    """
    if substrategy and substrategy != "none":
        from app.pipeline.strategies.domains.registry import get_substrategy_selectors
        sels = get_substrategy_selectors(entity_type, substrategy)
        if sels:
            return sels
    return CATEGORY_SELECTORS.get(entity_type, CATEGORY_SELECTORS[_FALLBACK])
