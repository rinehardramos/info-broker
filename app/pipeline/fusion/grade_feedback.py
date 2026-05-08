"""Grade → overlay feedback loop. Maps user A-F grades to strategy overlay actions."""

from __future__ import annotations
import logging

log = logging.getLogger(__name__)

# Grade → overlay action mapping
_GRADE_ACTIONS = {
    "A": {"overlay_type": "reinforce", "confidence": 0.95, "yield_rate": 0.9},
    "B": {"overlay_type": "reinforce", "confidence": 0.75, "yield_rate": 0.7},
    "C": None,  # Neutral — no overlay change
    "D": {"overlay_type": "prune", "confidence": 0.6, "yield_rate": 0.2},
    "E": {"overlay_type": "prune", "confidence": 0.8, "yield_rate": 0.1},
    "F": {"overlay_type": "prune", "confidence": 0.95, "yield_rate": 0.0, "flagged": True},
}


def grade_to_overlay_action(grade: str) -> dict | None:
    """Convert a letter grade to an overlay action dict, or None for neutral."""
    return _GRADE_ACTIONS.get(grade)


def apply_grade_feedback(
    entity_type: str,
    selector_type: str,
    tool_name: str,
    grade: str,
) -> None:
    """Apply a user grade to the strategy overlay system."""
    action = grade_to_overlay_action(grade)
    if action is None:
        return  # Neutral grade, no change

    # Build the pivot pattern string
    clean_tool = tool_name.replace("run_", "")
    pivot_pattern = f"{selector_type} -> {clean_tool}"

    overlay = {
        "entity_type": entity_type,
        "selector_type": selector_type,
        "pivot_pattern": pivot_pattern,
        "overlay_type": action["overlay_type"],
        "yield_rate": action["yield_rate"],
    }

    _upsert_overlay(overlay)

    if action.get("flagged"):
        log.warning(
            "Tool %s flagged by user (grade F) for entity_type=%s",
            tool_name,
            entity_type,
        )


def _upsert_overlay(overlay: dict) -> None:
    """Upsert an overlay signal to the database. Delegates to analyzer's upsert."""
    try:
        from app.pipeline.strategies.analyzer import _upsert_overlay as analyzer_upsert
        analyzer_upsert(overlay)
    except Exception as exc:
        log.warning("Grade feedback overlay upsert failed: %s", exc)
