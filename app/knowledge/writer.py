from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone

from app.routers.v3.db import execute

logger = logging.getLogger(__name__)

# Maps LLM-emitted type names to canonical ontology types
_TYPE_MAP: dict[str, str] = {
    "company": "organization",
    "org": "organization",
    "organisation": "organization",
    "corporation": "organization",
    "corp": "organization",
    "firm": "organization",
    "role": "person",
    "title": "person",
    "individual": "person",
    "human": "person",
    "people": "person",
}


def _generate_entity_ref(name: str, entity_type: str) -> str:
    """Return ``{normalized_type}::{slugified_name}``."""
    normalized_type = _TYPE_MAP.get(entity_type.lower(), entity_type.lower())
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{normalized_type}::{slug}"


class KnowledgeGraphWriter:
    async def write_entities(
        self,
        entities: list[dict],
        source_run_id: str | None = None,
        source_tool: str = "analyzer",
        default_confidence: int = 70,
    ) -> int:
        """Write entity observations to the event store.

        For each entity one observation is written for the ``name`` attribute
        and one observation per key in ``attributes``.

        Returns the total number of observations written.
        """
        count = 0
        observed_at = datetime.now(timezone.utc)

        for entity in entities:
            name: str = entity.get("name", "")
            entity_type: str = entity.get("type", "unknown")
            attributes: dict = entity.get("attributes", {})
            confidence: int = entity.get("confidence", default_confidence)

            entity_ref = _generate_entity_ref(name, entity_type)
            normalized_type = _TYPE_MAP.get(entity_type.lower(), entity_type.lower())

            # Write the canonical "name" observation
            execute(
                """
                INSERT INTO entity_observations
                    (id, entity_ref, entity_type, attribute, value,
                     confidence, source_run_id, source_tool, observed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    entity_ref,
                    normalized_type,
                    "name",
                    name,
                    confidence,
                    source_run_id,
                    source_tool,
                    observed_at,
                ),
            )
            count += 1

            # Write one observation per attribute
            for attr_key, attr_value in attributes.items():
                execute(
                    """
                    INSERT INTO entity_observations
                        (id, entity_ref, entity_type, attribute, value,
                         confidence, source_run_id, source_tool, observed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()),
                        entity_ref,
                        normalized_type,
                        attr_key,
                        str(attr_value),
                        confidence,
                        source_run_id,
                        source_tool,
                        observed_at,
                    ),
                )
                count += 1

        logger.debug("write_entities: wrote %d observations", count)
        return count

    async def write_relationships(
        self,
        relationships: list[dict],
        source_run_id: str | None = None,
        source_tool: str = "analyzer",
        default_confidence: int = 60,
    ) -> int:
        """Write relationship observations to the event store.

        Returns the number of observations written.
        """
        count = 0
        observed_at = datetime.now(timezone.utc)

        for rel in relationships:
            from_name: str = rel.get("from", "")
            to_name: str = rel.get("to", "")
            rel_type: str = rel.get("type", "related_to")
            confidence: int = rel.get("confidence", default_confidence)
            evidence = rel.get("evidence")

            # Derive entity refs; type unknown at relationship level
            from_ref = _generate_entity_ref(from_name, "unknown")
            to_ref = _generate_entity_ref(to_name, "unknown")

            # Normalise evidence to str if it isn't already
            if evidence is not None and not isinstance(evidence, str):
                evidence = str(evidence)

            execute(
                """
                INSERT INTO relationship_observations
                    (id, from_entity_ref, to_entity_ref, relationship_type,
                     confidence, evidence, source_run_id, source_tool, observed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    from_ref,
                    to_ref,
                    rel_type,
                    confidence,
                    evidence,
                    source_run_id,
                    source_tool,
                    observed_at,
                ),
            )
            count += 1

        logger.debug("write_relationships: wrote %d observations", count)
        return count

    async def write_from_analyzer(
        self,
        analyzer_output: dict,
        source_run_id: str | None = None,
    ) -> dict:
        """Bridge analyzer output to the observation event store.

        Expects ``analyzer_output`` with optional ``entities`` and
        ``relationships`` lists (same format as AnalyzerNode output).

        Returns ``{"entity_observations": int, "relationship_observations": int}``.
        """
        entity_count = await self.write_entities(
            analyzer_output.get("entities", []),
            source_run_id=source_run_id,
        )
        rel_count = await self.write_relationships(
            analyzer_output.get("relationships", []),
            source_run_id=source_run_id,
        )
        return {
            "entity_observations": entity_count,
            "relationship_observations": rel_count,
        }


kg_writer = KnowledgeGraphWriter()
