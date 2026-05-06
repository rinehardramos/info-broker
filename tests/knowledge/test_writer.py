from __future__ import annotations

import asyncio
from unittest.mock import patch


from app.knowledge.writer import _generate_entity_ref, kg_writer


def _arun(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# _generate_entity_ref
# ---------------------------------------------------------------------------


def test_generate_entity_ref():
    assert _generate_entity_ref("John Doe", "person") == "person::john-doe"
    assert (
        _generate_entity_ref("Acme Corp Inc.", "organization")
        == "organization::acme-corp-inc"
    )
    # "company" maps to "organization" via _TYPE_MAP
    assert _generate_entity_ref("Test LLC", "company") == "organization::test-llc"


# ---------------------------------------------------------------------------
# write_entities
# ---------------------------------------------------------------------------


def test_write_entity_observations():
    """2 entities: John Doe (2 attrs) + Acme Corp (2 attrs) → 6 INSERT calls."""
    entities = [
        {
            "name": "John Doe",
            "type": "person",
            "attributes": {"role": "CEO", "company": "Acme"},
            "evidence": [1, 3],
        },
        {
            "name": "Acme Corp",
            "type": "organization",
            "attributes": {"industry": "Tech", "founded": "2000"},
        },
    ]

    with patch("app.knowledge.writer.execute") as mock_exec:
        count = _arun(kg_writer.write_entities(entities))

    assert count == 6
    assert mock_exec.call_count == 6

    # Every call should INSERT into entity_observations
    for c in mock_exec.call_args_list:
        sql: str = c.args[0]
        assert "entity_observations" in sql
        assert "INSERT INTO" in sql


# ---------------------------------------------------------------------------
# write_relationships
# ---------------------------------------------------------------------------


def test_write_relationship_observations():
    """1 relationship → 1 INSERT into relationship_observations."""
    relationships = [
        {
            "from": "John Doe",
            "to": "Acme Corp",
            "type": "works_at",
            "evidence": "LinkedIn profile",
        }
    ]

    with patch("app.knowledge.writer.execute") as mock_exec:
        count = _arun(kg_writer.write_relationships(relationships))

    assert count == 1
    assert mock_exec.call_count == 1

    sql: str = mock_exec.call_args.args[0]
    assert "relationship_observations" in sql
    assert "INSERT INTO" in sql
