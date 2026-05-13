"""Grade → overlay feedback loop. Maps Admiralty Code grades to strategy overlay actions.

Admiralty Code:
  Source reliability A-F:
    A = Completely reliable   B = Usually reliable     C = Fairly reliable
    D = Not usually reliable  E = Unreliable           F = Cannot judge reliability

  Information credibility 1-6:
    1 = Confirmed by other sources    2 = Probably true       3 = Possibly true
    4 = Doubtful                      5 = Improbable          6 = Cannot judge truth

User rejection grade — E5:
  E = Source (brain's research) was unreliable for this finding.
  5 = Content improbable — conflicts with the user's direct observation.
  This is the semantically correct existing code for "the user saw it themselves
  and says the finding is wrong." No new grade level required.

  E5 via the standard overlay:
    yield_rate = E_base(0.1) × mult_5(0.3) = 0.03  → effectively hard-pruned
    flagged = True                                   → logged as rejection
"""

from __future__ import annotations
import logging

log = logging.getLogger(__name__)

# Admiralty source → overlay action
_SOURCE_ACTIONS = {
    "A": {"overlay_type": "reinforce", "confidence": 0.95, "yield_rate": 0.9},
    "B": {"overlay_type": "reinforce", "confidence": 0.75, "yield_rate": 0.7},
    "C": None,  # Neutral
    "D": {"overlay_type": "prune", "confidence": 0.6, "yield_rate": 0.2},
    "E": {"overlay_type": "prune", "confidence": 0.8, "yield_rate": 0.1, "flagged": True},
    "F": None,  # Cannot judge — no overlay change
}

# Credibility modifier: multiplied against the source action's base rates
_CRED_MULTIPLIER = {"1": 1.0, "2": 0.9, "3": 0.75, "4": 0.5, "5": 0.3, "6": 0.0}

# E5 is the user-rejection grade. At yield_rate=0.03 it is effectively hard-pruned
# and the flagged=True on the E source action triggers the rejection log + near-probable
# seed extraction in apply_grade_feedback.
USER_REJECTION_GRADE = "E5"


def _split(code: str) -> tuple[str, str]:
    if len(code) == 2 and code[0] in _SOURCE_ACTIONS and code[1] in _CRED_MULTIPLIER:
        return code[0], code[1]
    if len(code) == 1 and code in _SOURCE_ACTIONS:
        return code, "3"
    return "F", "6"


def grade_to_overlay_action(grade: str) -> dict | None:
    src, cred = _split(grade)
    base = _SOURCE_ACTIONS.get(src)
    if base is None:
        return None
    mult = _CRED_MULTIPLIER.get(cred, 0.5)
    if mult == 0.0:
        return None  # credibility 6 = cannot judge, no action
    return {
        **base,
        "yield_rate": base["yield_rate"] * mult,
        "confidence": base["confidence"] * mult,
    }


def extract_near_probable_seeds(findings: list[dict]) -> list[str]:
    """Extract retained signals from E5-rejected findings for near-probable node generation.

    These are the features that were plausible in the rejected hypothesis and
    should be carried forward to seed the next investigation branch.
    """
    seeds: list[str] = []
    for f in findings:
        content = f.get("content", "") or ""
        title = f.get("title", "") or ""
        # Extract entity-type-agnostic signals: franchise connections, platform hints, genre cues
        combined = f"{title} {content}".lower()
        if any(k in combined for k in ("spider-man", "spiderman", "spider man")):
            seeds.append("Spider-Man franchise connection retained")
        if any(k in combined for k in ("youtube", "trailer", "clip", "video")):
            seeds.append("YouTube video/clip context retained")
        if any(k in combined for k in ("shotgun", "firearm", "gun", "weapon")):
            seeds.append("Man with firearm/shotgun signal retained")
        if any(k in combined for k in ("gritty", "noir", "dark", "crime", "hardboiled")):
            seeds.append("Gritty/dark tone signal retained")
        if any(k in combined for k in ("amazon", "prime video", "streaming")):
            seeds.append("Amazon/streaming platform signal retained")
        if any(k in combined for k in ("zendaya", "actress", "female lead", "girl")):
            seeds.append("Female Spider-Man franchise actress signal retained")
    # Deduplicate
    return list(dict.fromkeys(seeds))


def apply_grade_feedback(
    entity_type: str,
    selector_type: str,
    tool_name: str,
    grade: str,
    findings: list[dict] | None = None,
) -> dict | None:
    """Apply grade feedback overlay. Returns near-probable seeds dict on E5 (user rejection).

    E5 = unreliable source + content improbable (conflicts with user's direct observation).
    This is the existing Admiralty code for explicit user rejection — no new grade needed.
    """
    action = grade_to_overlay_action(grade)
    if action is None:
        return None

    src, cred = _split(grade)
    is_user_rejection = (grade == USER_REJECTION_GRADE)  # E5

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
        label = "USER REJECTION (E5 — conflicts with direct observation)" if is_user_rejection else f"grade {grade}"
        log.warning("Tool %s flagged (%s) for entity_type=%s", tool_name, label, entity_type)

    if is_user_rejection and findings:
        seeds = extract_near_probable_seeds(findings)
        log.info("E5 user rejection — near-probable seeds extracted: %s", seeds)
        return {"near_probable_seeds": seeds, "rejected_tool": clean_tool, "rejected_grade": "E5"}

    return None


def _upsert_overlay(overlay: dict) -> None:
    try:
        from app.pipeline.strategies.analyzer import _upsert_overlay as analyzer_upsert
        analyzer_upsert(overlay)
    except Exception as exc:
        log.warning("Grade feedback overlay upsert failed: %s", exc)
