"""Multi-branch retrieval orchestrator for media identification queries."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Literal

log = logging.getLogger(__name__)

BRANCH_QUOTA = 5

_BRANCH_LABELS = {
    "character_in_universe": "Branch A - Character-in-Spider-Man-Universe",
    "actor_career":          "Branch B - Actress-from-Spider-Man-in-New-Series",
    "genre_signal":          "Branch C - Young-Female-Lead-Franchise-Blind",
}


@dataclass
class BranchHit:
    title: str
    year: int | None
    type: Literal["tv", "movie", "other"]
    tmdb_id: int | None
    top_billed_cast: list[str]
    top_billed_genders: list[int]
    overview: str
    source: Literal["tmdb", "web", "news"]
    branch: str
    actor_connection: str | None = None


@dataclass
class BranchEvidence:
    branches: dict[str, list[BranchHit]]
    balanced: bool

    def to_prompt_block(self) -> str:
        if not self.branches:
            return ""
        lines = ["## PRE-RETRIEVED EVIDENCE (do not re-search - work from this corpus)\n"]
        for key, label in _BRANCH_LABELS.items():
            hits = self.branches.get(key, [])
            lines.append(f"### {label}")
            if not hits:
                lines.append("*(no results)*")
            else:
                for i, h in enumerate(hits, 1):
                    cast_str = ", ".join(h.top_billed_cast[:3]) if h.top_billed_cast else "unknown"
                    conn = f" [{h.actor_connection}]" if h.actor_connection else ""
                    lines.append(
                        f"{i}. **{h.title}** ({h.year or '?'}) "
                        f"- top cast: {cast_str}{conn}\n   {h.overview[:120]}"
                    )
            lines.append("")
        lines.append(
            "**YOU MUST produce >= 1 candidate from each non-empty branch before ranking.**\n"
            'State "no viable candidate" for any branch you cannot satisfy.'
        )
        return "\n".join(lines)


async def prefetch_branches(signals: dict, classification: str) -> BranchEvidence:
    """Run 3 parallel TMDB branches. Returns empty BranchEvidence for non-media queries."""
    if classification != "media_identification":
        return BranchEvidence(branches={}, balanced=True)
    if not signals.get("primary") and not signals.get("context"):
        return BranchEvidence(branches={}, balanced=True)

    from app.pipeline.retrieval.branches.media_identification import (
        branch_character_in_universe, branch_actor_career, branch_genre_signal,
    )
    raw = await asyncio.gather(
        branch_character_in_universe(signals),
        branch_actor_career(signals),
        branch_genre_signal(signals),
        return_exceptions=True,
    )
    keys = ["character_in_universe", "actor_career", "genre_signal"]
    branches: dict[str, list[BranchHit]] = {}
    for key, result in zip(keys, raw):
        if isinstance(result, Exception):
            log.warning("Branch %s failed (non-fatal): %s", key, result)
            branches[key] = []
        else:
            branches[key] = list(result)[:BRANCH_QUOTA]

    return BranchEvidence(
        branches=branches,
        balanced=all(len(v) >= 1 for v in branches.values()),
    )
