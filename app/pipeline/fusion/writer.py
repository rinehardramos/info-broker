"""Write entities and relationships to the Knowledge Graph event store."""

from __future__ import annotations
import logging
import uuid

from app.pipeline.fusion.classification import rate_source

log = logging.getLogger(__name__)

# Map Admiralty source rating to confidence integer (0-100)
_RATING_TO_CONFIDENCE: dict[str, int] = {
    "A": 90,  # Completely Reliable
    "B": 75,  # Usually Reliable
    "C": 60,  # Fairly Reliable
    "D": 40,  # Not Usually Reliable
    "E": 20,  # Unreliable
    "F": 30,  # Cannot Be Judged
}

try:
    from app.routers.v3.db import execute
except ImportError:
    execute = None  # type: ignore


def _entity_ref(name: str, entity_type: str) -> str:
    """Build a canonical entity reference from name + type."""
    return f"{entity_type}:{name.strip().lower()}"


async def write_entities_to_kg(
    run_id: str,
    entities: list[dict],
    source_tool: str,
) -> int:
    """Write entity observations to the KG event store. Returns count written."""
    if not entities or execute is None:
        return 0

    rating = rate_source(source_tool)
    confidence = _RATING_TO_CONFIDENCE.get(rating, 30)
    count = 0

    for entity in entities:
        name = entity.get("name", "").strip()
        etype = entity.get("type", "unknown").strip().lower()
        if not name:
            continue

        ref = _entity_ref(name, etype)

        # Write name observation
        _write_entity_obs(ref, etype, "name", name, confidence, run_id, source_tool)
        count += 1

        # Write attribute observations
        for attr_key, attr_val in (entity.get("attributes") or {}).items():
            if attr_val:
                _write_entity_obs(ref, etype, attr_key, str(attr_val), confidence, run_id, source_tool)
                count += 1

    return count


async def write_relationships_to_kg(
    run_id: str,
    relationships: list[dict],
    source_tool: str,
) -> int:
    """Write relationship observations to the KG event store. Returns count written."""
    if not relationships or execute is None:
        return 0

    rating = rate_source(source_tool)
    confidence = _RATING_TO_CONFIDENCE.get(rating, 30)
    count = 0

    for rel in relationships:
        from_name = rel.get("from", "").strip()
        to_name = rel.get("to", "").strip()
        rel_type = rel.get("type", "linked_to").strip().lower()
        evidence = rel.get("evidence", "")

        if not from_name or not to_name:
            continue

        from_ref = _entity_ref(from_name, "unknown")
        to_ref = _entity_ref(to_name, "unknown")

        try:
            execute(
                """INSERT INTO relationship_observations
                    (id, from_entity_ref, to_entity_ref, relationship_type,
                     confidence, evidence, source_run_id, source_tool)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (str(uuid.uuid4()), from_ref, to_ref, rel_type,
                 confidence, evidence, run_id, source_tool),
            )
            count += 1
        except Exception as exc:
            log.warning("Failed to write relationship observation: %s", exc)

    return count


def _write_entity_obs(
    ref: str, etype: str, attribute: str, value: str,
    confidence: int, run_id: str, source_tool: str,
) -> None:
    """Insert a single entity observation row."""
    try:
        execute(
            """INSERT INTO entity_observations
                (id, entity_ref, entity_type, attribute, value,
                 confidence, source_run_id, source_tool)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (str(uuid.uuid4()), ref, etype, attribute, value,
             confidence, run_id, source_tool),
        )
    except Exception as exc:
        log.warning("Failed to write entity observation: %s", exc)
