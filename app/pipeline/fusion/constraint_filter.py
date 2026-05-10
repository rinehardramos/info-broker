"""Hard TMDB gender check for lead character — deterministic, no LLM."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from app.pipeline.retrieval.tmdb_client import get_top_cast

log = logging.getLogger(__name__)

_FEMALE = {"girl", "woman", "female", "lady", "actress", "she", "her"}
_MALE   = {"boy", "man", "male", "guy", "actor", "he", "him"}


@dataclass
class PrimarySignal:
    entity: str
    gender: Literal["female", "male", "unknown"]
    role: Literal["lead", "supporting", "unknown"]


@dataclass
class ConstraintResult:
    passed: bool
    reason: str
    evidence: dict


def extract_primary_signal(primary_text: str) -> PrimarySignal:
    lower = primary_text.lower()
    gender: Literal["female", "male", "unknown"] = "unknown"
    if any(w in lower for w in _FEMALE):
        gender = "female"
    elif any(w in lower for w in _MALE):
        gender = "male"
    return PrimarySignal(entity=primary_text, gender=gender, role="lead")


async def passes_lead_constraint(
    candidate_title: str,
    candidate_tmdb_id: int | None,
    candidate_type: str,
    primary_signal: PrimarySignal,
) -> ConstraintResult:
    """Return False if top-billed actor gender contradicts PRIMARY. TMDB: 1=female, 2=male."""
    if primary_signal.gender == "unknown":
        return ConstraintResult(passed=True, reason="no gender constraint", evidence={})
    if not candidate_tmdb_id:
        return ConstraintResult(passed=True, reason="no TMDB id",
                                evidence={"warning": "unverified"})
    try:
        cast = await get_top_cast(candidate_tmdb_id, media_type=candidate_type or "tv")
    except Exception as exc:
        log.warning("constraint_filter TMDB error for %s: %s", candidate_title, exc)
        return ConstraintResult(passed=True, reason=f"TMDB error: {exc}", evidence={})
    if not cast:
        return ConstraintResult(passed=True, reason="no cast data", evidence={})
    top = cast[0]
    top_gender = top.get("gender", 0)
    top_name   = top.get("name", "unknown")
    if primary_signal.gender == "female" and top_gender == 2:
        return ConstraintResult(
            passed=False,
            reason=f"Lead actor {top_name!r} is male (TMDB gender=2) but PRIMARY requires female lead",
            evidence={"top_actor": top_name, "tmdb_gender": top_gender},
        )
    if primary_signal.gender == "male" and top_gender == 1:
        return ConstraintResult(
            passed=False,
            reason=f"Lead actor {top_name!r} is female (TMDB gender=1) but PRIMARY requires male lead",
            evidence={"top_actor": top_name, "tmdb_gender": top_gender},
        )
    return ConstraintResult(
        passed=True,
        reason=f"Lead actor {top_name!r} matches PRIMARY gender constraint",
        evidence={"top_actor": top_name, "tmdb_gender": top_gender},
    )
