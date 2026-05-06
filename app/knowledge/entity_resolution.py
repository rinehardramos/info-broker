from __future__ import annotations

import logging

from app.routers.v3.db import execute, fetch_one

logger = logging.getLogger(__name__)

# Maps LLM-emitted type names to canonical ontology types (mirrors writer.py)
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


def normalize_entity_type(raw_type: str) -> str:
    """Return canonical entity type for a raw/LLM-emitted type string."""
    return _TYPE_MAP.get(raw_type.lower(), raw_type.lower())


def resolve_entity_ref(entity_ref: str, entity_type: str, entity_name: str) -> str:
    """Resolve an entity_ref to its canonical ref via the entity_aliases table.

    Checks for an alias match first by ref, then by name (case-insensitive).
    Returns the canonical_ref if found, otherwise returns entity_ref unchanged.
    """
    # Check by alias ref exact match
    row = fetch_one(
        "SELECT canonical_ref FROM entity_aliases WHERE alias = %s LIMIT 1",
        (entity_ref,),
    )
    if row:
        return row["canonical_ref"]

    # Check by name case-insensitive match
    if entity_name:
        row = fetch_one(
            "SELECT canonical_ref FROM entity_aliases WHERE lower(alias) = lower(%s) LIMIT 1",
            (entity_name,),
        )
        if row:
            return row["canonical_ref"]

    return entity_ref


def create_alias(
    canonical_ref: str,
    alias: str,
    alias_type: str = "name",
    created_by: str = "materializer",
) -> None:
    """Insert an alias for a canonical entity ref. Silently ignores duplicates."""
    execute(
        """
        INSERT INTO entity_aliases (canonical_ref, alias, alias_type, created_by)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (canonical_ref, alias, alias_type, created_by),
    )
