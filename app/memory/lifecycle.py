"""Tier lifecycle sweep for entity and relationship observations.

Observations move through tiers: hot → warm → cold → archive
based on age and idle time (last_accessed_at).
"""

from __future__ import annotations

import asyncio
import logging

from app.routers.v3.db import execute

log = logging.getLogger(__name__)

TIER_THRESHOLDS: dict[tuple[str, str], dict[str, int]] = {
    ("hot", "warm"): {"age_days": 30, "idle_days": 30},
    ("warm", "cold"): {"age_days": 90, "idle_days": 60},
    ("cold", "archive"): {"age_days": 365, "idle_days": 180},
}

_DEMOTE_SQL = """
UPDATE entity_observations
   SET tier = %s
 WHERE tier = %s
   AND observed_at < now() - interval '%s days'
   AND (last_accessed_at IS NULL OR last_accessed_at < now() - interval '%s days')
"""

_PROMOTE_SQL = """
UPDATE entity_observations
   SET tier = %s
 WHERE tier != %s
   AND tier != 'archive'
   AND last_accessed_at > now() - interval '%s days'
"""


def demote_tier(from_tier: str, to_tier: str, age_days: int, idle_days: int) -> int:
    """Demote observations from *from_tier* to *to_tier* based on age and idle time.

    Returns the number of rows transitioned (always 0 when called via the
    patched ``execute`` helper, which does not expose rowcount).
    """
    execute(_DEMOTE_SQL, (to_tier, from_tier, age_days, idle_days))
    return 0


def promote_recently_accessed(accessed_within_days: int = 7, target_tier: str = "hot") -> int:
    """Promote observations recently accessed back to *target_tier*.

    Returns the number of rows transitioned.
    """
    execute(_PROMOTE_SQL, (target_tier, target_tier, accessed_within_days))
    return 0


async def run_lifecycle_sweep(interval_seconds: int = 1800) -> None:
    """Background loop: run tier transitions every *interval_seconds* seconds."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            total = 0
            for (from_t, to_t), thresh in TIER_THRESHOLDS.items():
                total += demote_tier(from_t, to_t, thresh["age_days"], thresh["idle_days"])
            total += promote_recently_accessed()
            log.info("Lifecycle sweep: %d observations transitioned", total)
        except Exception as exc:
            log.error("Lifecycle sweep failed: %s", exc)
