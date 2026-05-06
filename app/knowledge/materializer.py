from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from app.routers.v3.db import execute, fetch_all, fetch_one
from app.knowledge.entity_resolution import resolve_entity_ref, create_alias

logger = logging.getLogger(__name__)


class GraphMaterializer:
    def __init__(self, neo4j_client=None) -> None:
        self._neo4j = neo4j_client

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_checkpoint(self, key: str) -> Optional[datetime]:
        row = fetch_one(f"SELECT {key} FROM graph_materializer_state WHERE id = 1")
        if row and row.get(key):
            val = row[key]
            # psycopg2 returns aware datetime directly for TIMESTAMPTZ
            return val
        return None

    def _update_checkpoint(self, key: str, ts: datetime) -> None:
        execute(
            f"UPDATE graph_materializer_state SET {key} = %s WHERE id = 1",
            (ts,),
        )

    # ------------------------------------------------------------------
    # materialize_entities
    # ------------------------------------------------------------------

    async def materialize_entities(self) -> int:
        checkpoint = self._get_checkpoint("last_entity_obs_at")

        if checkpoint:
            rows = fetch_all(
                """
                SELECT entity_ref, entity_type, attribute, value, confidence,
                       observed_at, created_at
                FROM entity_observations
                WHERE created_at > %s
                ORDER BY created_at ASC
                """,
                (checkpoint,),
            )
        else:
            rows = fetch_all(
                """
                SELECT entity_ref, entity_type, attribute, value, confidence,
                       observed_at, created_at
                FROM entity_observations
                ORDER BY created_at ASC
                """
            )

        if not rows:
            return 0

        # Group by entity_ref
        groups: dict[str, list[dict]] = {}
        for row in rows:
            groups.setdefault(row["entity_ref"], []).append(row)

        upsert_count = 0
        latest_created_at: Optional[datetime] = None

        for entity_ref, obs_list in groups.items():
            # Resolve ref via alias lookup — use the first obs for type/name hints
            first_obs = obs_list[0]
            entity_type = first_obs["entity_type"]

            # Extract name from observations (attribute == "name")
            name_obs = [o for o in obs_list if o["attribute"] == "name"]
            if name_obs:
                # Pick highest confidence name
                best_name_obs = max(name_obs, key=lambda o: o["confidence"])
                entity_name = best_name_obs["value"]
            else:
                entity_name = entity_ref

            canonical_ref = resolve_entity_ref(entity_ref, entity_type, entity_name)

            # Build attributes: highest confidence wins per attribute key
            attr_map: dict[str, tuple[str, int]] = {}  # key -> (value, confidence)
            for obs in obs_list:
                attr = obs["attribute"]
                conf = obs["confidence"]
                if attr not in attr_map or conf > attr_map[attr][1]:
                    attr_map[attr] = (obs["value"], conf)

            attributes = {k: v for k, (v, _) in attr_map.items() if k != "name"}
            best_confidence = max(c for _, c in attr_map.values()) if attr_map else 50

            # Compute time bounds
            observed_ats = [
                o["observed_at"] for o in obs_list if o.get("observed_at")
            ]
            first_seen = min(observed_ats) if observed_ats else None
            last_seen = max(observed_ats) if observed_ats else None

            self._neo4j.upsert_entity(
                ref=canonical_ref,
                entity_type=entity_type,
                name=entity_name,
                attributes=attributes,
                confidence=best_confidence,
                first_seen=first_seen,
                last_seen=last_seen,
                observation_count=len(obs_list),
            )
            upsert_count += 1

            # Track latest created_at for checkpoint
            for obs in obs_list:
                obs_created = obs.get("created_at")
                if obs_created:
                    if latest_created_at is None or obs_created > latest_created_at:
                        latest_created_at = obs_created

        if latest_created_at:
            self._update_checkpoint("last_entity_obs_at", latest_created_at)

        return upsert_count

    # ------------------------------------------------------------------
    # materialize_relationships
    # ------------------------------------------------------------------

    async def materialize_relationships(self) -> int:
        checkpoint = self._get_checkpoint("last_rel_obs_at")

        if checkpoint:
            rows = fetch_all(
                """
                SELECT from_entity_ref, to_entity_ref, relationship_type,
                       confidence, evidence, observed_at, created_at
                FROM relationship_observations
                WHERE created_at > %s
                ORDER BY created_at ASC
                """,
                (checkpoint,),
            )
        else:
            rows = fetch_all(
                """
                SELECT from_entity_ref, to_entity_ref, relationship_type,
                       confidence, evidence, observed_at, created_at
                FROM relationship_observations
                ORDER BY created_at ASC
                """
            )

        if not rows:
            return 0

        latest_created_at: Optional[datetime] = None

        for row in rows:
            self._neo4j.upsert_relationship(
                from_ref=row["from_entity_ref"],
                to_ref=row["to_entity_ref"],
                rel_type=row["relationship_type"],
                confidence=row["confidence"],
                evidence=row.get("evidence"),
                first_seen=row.get("observed_at"),
                last_seen=row.get("observed_at"),
            )

            obs_created = row.get("created_at")
            if obs_created:
                if latest_created_at is None or obs_created > latest_created_at:
                    latest_created_at = obs_created

        if latest_created_at:
            self._update_checkpoint("last_rel_obs_at", latest_created_at)

        return len(rows)

    # ------------------------------------------------------------------
    # run_once
    # ------------------------------------------------------------------

    async def run_once(self) -> dict:
        entities = await self.materialize_entities()
        relationships = await self.materialize_relationships()
        return {"entities": entities, "relationships": relationships}


# ---------------------------------------------------------------------------
# Background loop
# ---------------------------------------------------------------------------


async def materializer_loop(interval_seconds: int = 5) -> None:
    """Run the graph materializer in a background loop.

    If Neo4j is unavailable, logs a warning and returns without crashing.
    """
    from app.knowledge.neo4j_client import Neo4jClient

    try:
        neo4j_client = Neo4jClient()
        neo4j_client.ensure_constraints()
    except Exception as exc:
        logger.warning("Neo4j not available — graph materializer disabled: %s", exc)
        return

    materializer = GraphMaterializer(neo4j_client=neo4j_client)

    while True:
        try:
            result = await materializer.run_once()
            if result["entities"] or result["relationships"]:
                logger.info(
                    "Materializer run: entities=%d relationships=%d",
                    result["entities"],
                    result["relationships"],
                )
        except Exception as exc:
            logger.exception("Materializer run failed: %s", exc)

        await asyncio.sleep(interval_seconds)
