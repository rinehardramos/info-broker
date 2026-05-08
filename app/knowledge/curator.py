"""KG Curator — Memory Phase 3, Task 3.

Responsibilities
----------------
- Detect contradictory observations for the same entity+attribute.
- Auto-resolve contradictions via confidence / recency heuristics.
- Flag stale observations based on per-attribute TTL rules.
- Provide an async loop (run_curator_loop) for continuous background curation.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.memory.value_normalizer import values_equivalent
from app.routers.v3.db import execute, fetch_all, fetch_one

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Staleness TTL (days).  0 means "never stale".
# ---------------------------------------------------------------------------

STALENESS_TTL: dict[str, int] = {
    "role": 180,
    "title": 180,
    "company": 365,
    "email": 365,
    "phone": 180,
    "location": 365,
    "name": 0,
}

_DEFAULT_TTL = 365

# ---------------------------------------------------------------------------
# Pure helper
# ---------------------------------------------------------------------------


def pick_winner(
    conf_a: int,
    at_a: datetime,
    conf_b: int,
    at_b: datetime,
) -> tuple[str, str]:
    """Return (winner, status) where winner is 'a' or 'b'.

    Rules
    -----
    1. Confidence gap >= 15 → higher confidence wins, status = "auto_resolved".
    2. Confidence gap < 15 and NOT (same conf AND within 7 days of each other)
       → more recent wins, status = "auto_resolved".
    3. Same confidence AND observations within 7 days of each other
       → more recent wins, status = "needs_review".
    """
    gap = abs(conf_a - conf_b)

    if gap >= 15:
        winner = "a" if conf_a >= conf_b else "b"
        return winner, "auto_resolved"

    # gap < 15 — recency decides
    same_conf = conf_a == conf_b
    # Normalise to UTC-aware datetimes for safe subtraction
    _at_a = at_a if at_a.tzinfo else at_a.replace(tzinfo=timezone.utc)
    _at_b = at_b if at_b.tzinfo else at_b.replace(tzinfo=timezone.utc)
    days_apart = abs((_at_a - _at_b).total_seconds()) / 86400

    winner = "b" if _at_b >= _at_a else "a"

    if same_conf and days_apart <= 7:
        return winner, "needs_review"

    return winner, "auto_resolved"


# ---------------------------------------------------------------------------
# Curator class
# ---------------------------------------------------------------------------


class KGCurator:
    """Encapsulates all KG curation logic."""

    # ------------------------------------------------------------------
    # Contradiction detection
    # ------------------------------------------------------------------

    def detect_contradictions(self) -> dict:
        """Find conflicting observations, auto-resolve, and persist.

        Returns
        -------
        {"contradictions_found": int, "auto_resolved": int, "needs_review": int}
        """
        sql = """
            SELECT
                a.id            AS id_a,
                b.id            AS id_b,
                a.entity_ref,
                a.attribute,
                a.value         AS value_a,
                b.value         AS value_b,
                a.confidence    AS confidence_a,
                b.confidence    AS confidence_b,
                a.observed_at   AS observed_at_a,
                b.observed_at   AS observed_at_b,
                a.source_run_id AS source_run_a,
                b.source_run_id AS source_run_b
            FROM entity_observations a
            JOIN entity_observations b
              ON a.entity_ref = b.entity_ref
             AND a.attribute  = b.attribute
             AND a.value     <> b.value
             AND a.id         < b.id
             AND b.observed_at >= a.observed_at - INTERVAL '1 year'
        """
        rows = fetch_all(sql)

        found = 0
        auto_resolved = 0
        needs_review = 0

        for row in rows:
            attribute = row["attribute"]
            value_a = row["value_a"]
            value_b = row["value_b"]

            # Skip if values are semantically equivalent after normalisation
            if values_equivalent(attribute, value_a, value_b):
                continue

            entity_ref = row["entity_ref"]

            # Deduplicate: skip if already recorded (by entity+attribute+sorted values)
            sorted_vals = sorted([value_a, value_b])
            existing = fetch_one(
                """
                SELECT id FROM kg_contradictions
                WHERE entity_ref = %s
                  AND attribute  = %s
                  AND value_a    = %s
                  AND value_b    = %s
                """,
                (entity_ref, attribute, sorted_vals[0], sorted_vals[1]),
            )
            if existing:
                continue

            found += 1

            winner_key, status = pick_winner(
                row["confidence_a"],
                row["observed_at_a"],
                row["confidence_b"],
                row["observed_at_b"],
            )
            winner_value = value_a if winner_key == "a" else value_b

            execute(
                """
                INSERT INTO kg_contradictions (
                    entity_ref, attribute,
                    value_a, value_b,
                    confidence_a, confidence_b,
                    observed_at_a, observed_at_b,
                    source_run_a, source_run_b,
                    observation_id_a, observation_id_b,
                    winner, status, resolved_by, resolved_at
                ) VALUES (
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, 'system', now()
                )
                """,
                (
                    entity_ref, attribute,
                    sorted_vals[0], sorted_vals[1],
                    row["confidence_a"], row["confidence_b"],
                    row["observed_at_a"], row["observed_at_b"],
                    row["source_run_a"], row["source_run_b"],
                    row["id_a"], row["id_b"],
                    winner_value, status,
                ),
            )

            if status == "auto_resolved":
                auto_resolved += 1
            else:
                needs_review += 1

        return {
            "contradictions_found": found,
            "auto_resolved": auto_resolved,
            "needs_review": needs_review,
        }

    # ------------------------------------------------------------------
    # Staleness detection
    # ------------------------------------------------------------------

    def _fetch_stale_for_attribute(self, attribute: str, ttl_days: int) -> list[dict]:
        """Return observations for *attribute* older than *ttl_days* with no
        more-recent observation for the same entity+attribute."""
        sql = """
            SELECT o.id, o.entity_ref, o.attribute, o.value, o.observed_at
            FROM entity_observations o
            WHERE o.attribute = %s
              AND o.observed_at < now() - INTERVAL '%s days'
              AND NOT EXISTS (
                  SELECT 1 FROM entity_observations newer
                  WHERE newer.entity_ref = o.entity_ref
                    AND newer.attribute  = o.attribute
                    AND newer.observed_at > o.observed_at
              )
        """
        return fetch_all(sql, (attribute, ttl_days))

    def detect_staleness(self) -> dict:
        """Flag stale observations in kg_stale_flags.

        Returns
        -------
        {"stale_flagged": int}
        """
        stale_flagged = 0

        for attribute, ttl_days in STALENESS_TTL.items():
            if ttl_days == 0:
                # TTL=0 means never stale (e.g. 'name')
                continue

            rows = self._fetch_stale_for_attribute(attribute, ttl_days)
            for row in rows:
                entity_ref = row["entity_ref"]

                # Dedup: skip if already flagged as stale
                existing = fetch_one(
                    """
                    SELECT id FROM kg_stale_flags
                    WHERE entity_ref = %s
                      AND attribute  = %s
                      AND status     = 'stale'
                    """,
                    (entity_ref, attribute),
                )
                if existing:
                    continue

                execute(
                    """
                    INSERT INTO kg_stale_flags (
                        entity_ref, attribute,
                        current_value, observation_id,
                        observed_at, ttl_days, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'stale')
                    """,
                    (
                        entity_ref,
                        attribute,
                        row["value"],
                        row["id"],
                        row["observed_at"],
                        ttl_days,
                    ),
                )
                stale_flagged += 1

        return {"stale_flagged": stale_flagged}

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    async def run_curator_loop(self, interval_seconds: int = 600) -> None:
        """Run contradiction + staleness detection on a fixed interval."""
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                c_summary = self.detect_contradictions()
                s_summary = self.detect_staleness()
                logger.info(
                    "KG curator cycle complete — contradictions: %s, stale: %s",
                    c_summary,
                    s_summary,
                )
            except Exception:
                logger.exception("KG curator loop encountered an error")
