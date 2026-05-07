from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

from app.knowledge.materializer import GraphMaterializer


def _arun(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_TS = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
_TS2 = datetime(2025, 1, 1, 13, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# materialize_entities — groups two observations for same ref into one upsert
# ---------------------------------------------------------------------------


def test_materialize_entities_processes_new_observations():
    """Two observations sharing entity_ref produce exactly one upsert_entity call."""
    obs = [
        {
            "entity_ref": "person::john-doe",
            "entity_type": "person",
            "attribute": "name",
            "value": "John Doe",
            "confidence": 80,
            "observed_at": _TS,
            "created_at": _TS,
        },
        {
            "entity_ref": "person::john-doe",
            "entity_type": "person",
            "attribute": "role",
            "value": "CEO",
            "confidence": 70,
            "observed_at": _TS2,
            "created_at": _TS2,
        },
    ]

    neo4j_mock = MagicMock()

    with (
        patch("app.knowledge.materializer.fetch_one", return_value={"last_entity_obs_at": None}),
        patch("app.knowledge.materializer.fetch_all", return_value=obs),
        patch("app.knowledge.materializer.execute") as mock_exec,
        patch(
            "app.knowledge.entity_resolution.fetch_one",
            return_value=None,
        ),
    ):
        materializer = GraphMaterializer(neo4j_client=neo4j_mock)
        count = _arun(materializer.materialize_entities())

    assert count == 1
    neo4j_mock.upsert_entity.assert_called_once()

    call_kwargs = neo4j_mock.upsert_entity.call_args
    assert call_kwargs.kwargs["ref"] == "person::john-doe"
    assert call_kwargs.kwargs["name"] == "John Doe"
    assert call_kwargs.kwargs["attributes"] == {"role": "CEO"}
    assert call_kwargs.kwargs["observation_count"] == 2


# ---------------------------------------------------------------------------
# materialize_relationships
# ---------------------------------------------------------------------------


def test_materialize_relationships():
    """One relationship observation results in one upsert_relationship call."""
    rel_obs = [
        {
            "from_entity_ref": "person::john-doe",
            "to_entity_ref": "organization::acme",
            "relationship_type": "works_at",
            "confidence": 75,
            "evidence": "Source article",
            "observed_at": _TS,
            "created_at": _TS,
        }
    ]

    neo4j_mock = MagicMock()

    # materialize_relationships calls fetch_all twice:
    # 1st call returns relationship observations, 2nd returns entity refs for slug resolution
    with (
        patch("app.knowledge.materializer.fetch_one", return_value={"last_rel_obs_at": None}),
        patch("app.knowledge.materializer.fetch_all", side_effect=[rel_obs, []]),
        patch("app.knowledge.materializer.execute"),
    ):
        materializer = GraphMaterializer(neo4j_client=neo4j_mock)
        count = _arun(materializer.materialize_relationships())

    assert count == 1
    neo4j_mock.upsert_relationship.assert_called_once()

    call_kwargs = neo4j_mock.upsert_relationship.call_args
    assert call_kwargs.kwargs["from_ref"] == "person::john-doe"
    assert call_kwargs.kwargs["to_ref"] == "organization::acme"
    assert call_kwargs.kwargs["rel_type"] == "works_at"
