from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from app.knowledge.neo4j_client import Neo4jClient, _LABEL_MAP, _REL_MAP


def _make_client() -> Neo4jClient:
    """Create a Neo4jClient with a mocked driver (bypasses real connection)."""
    client = Neo4jClient.__new__(Neo4jClient)
    client._driver = MagicMock()
    return client


class TestLabelAndRelMaps:
    def test_label_map_has_25_entries(self):
        assert len(_LABEL_MAP) == 25

    def test_rel_map_has_25_entries(self):
        assert len(_REL_MAP) == 25

    def test_known_entity_labels(self):
        assert _LABEL_MAP["person"] == "Person"
        assert _LABEL_MAP["organization"] == "Organization"
        assert _LABEL_MAP["threat_actor"] == "ThreatActor"
        assert _LABEL_MAP["financial_entity"] == "FinancialEntity"
        assert _LABEL_MAP["geopolitical_event"] == "GeopoliticalEvent"

    def test_known_rel_types(self):
        assert _REL_MAP["works_at"] == "WORKS_AT"
        assert _REL_MAP["subsidiary_of"] == "SUBSIDIARY_OF"
        assert _REL_MAP["attributed_to"] == "ATTRIBUTED_TO"
        assert _REL_MAP["participated_in"] == "PARTICIPATED_IN"


class TestUpsertEntity:
    def test_upsert_entity_creates_merge_query(self):
        client = _make_client()
        mock_session = MagicMock()
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        client.upsert_entity(
            ref="person:123",
            entity_type="person",
            name="Alice Smith",
            confidence=80,
        )

        mock_session.run.assert_called_once()
        cypher_arg = mock_session.run.call_args[0][0]
        assert "MERGE" in cypher_arg
        assert "Person" in cypher_arg
        assert "ref" in cypher_arg

    def test_upsert_entity_uses_correct_label(self):
        client = _make_client()
        mock_session = MagicMock()
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        client.upsert_entity(
            ref="ta:001",
            entity_type="threat_actor",
            name="APT29",
        )

        cypher_arg = mock_session.run.call_args[0][0]
        assert "ThreatActor" in cypher_arg

    def test_upsert_entity_passes_correct_params(self):
        client = _make_client()
        mock_session = MagicMock()
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        client.upsert_entity(
            ref="org:42",
            entity_type="organization",
            name="Acme Corp",
            confidence=75,
            attributes={"industry": "tech"},
            aliases=["Acme", "ACME Corporation"],
            observation_count=3,
        )

        _, kwargs = mock_session.run.call_args
        assert kwargs["ref"] == "org:42"
        assert kwargs["name"] == "Acme Corp"
        assert kwargs["confidence"] == 75
        # attributes are JSON-serialised before being sent to Cypher
        assert kwargs["attributes"] == '{"industry": "tech"}'
        assert kwargs["aliases"] == ["Acme", "ACME Corporation"]
        assert kwargs["observation_count"] == 3

    def test_upsert_entity_on_create_on_match_in_cypher(self):
        client = _make_client()
        mock_session = MagicMock()
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        client.upsert_entity(ref="loc:1", entity_type="location", name="London")

        cypher_arg = mock_session.run.call_args[0][0]
        assert "ON CREATE SET" in cypher_arg
        assert "ON MATCH SET" in cypher_arg
        assert "apoc.map.merge" in cypher_arg

    def test_upsert_entity_sets_valid_from_on_create(self):
        client = _make_client()
        mock_session = MagicMock()
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        client.upsert_entity(ref="loc:2", entity_type="location", name="Paris")

        cypher_arg = mock_session.run.call_args[0][0]
        assert "valid_from" in cypher_arg
        assert "valid_to" in cypher_arg
        # ON CREATE sets valid_from = $first_seen and valid_to = null
        assert "n.valid_from = $first_seen" in cypher_arg
        assert "n.valid_to = null" in cypher_arg

    def test_upsert_entity_valid_from_uses_earliest_on_match(self):
        client = _make_client()
        mock_session = MagicMock()
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
        client.upsert_entity(ref="loc:3", entity_type="location", name="Berlin", first_seen=ts)

        cypher_arg = mock_session.run.call_args[0][0]
        # ON MATCH must update valid_from only when the new value is earlier
        assert "$first_seen < n.valid_from" in cypher_arg

    def test_upsert_entity_first_seen_iso_format(self):
        client = _make_client()
        mock_session = MagicMock()
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        client.upsert_entity(ref="person:99", entity_type="person", name="Jane", first_seen=ts)

        _, kwargs = mock_session.run.call_args
        assert kwargs["first_seen"] == ts.isoformat()


class TestUpsertRelationship:
    def test_upsert_relationship_match_merge_in_cypher(self):
        client = _make_client()
        mock_session = MagicMock()
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        client.upsert_relationship(
            from_ref="person:1",
            to_ref="org:1",
            rel_type="works_at",
            confidence=90,
        )

        mock_session.run.assert_called_once()
        cypher_arg = mock_session.run.call_args[0][0]
        assert "MATCH" in cypher_arg
        assert "MERGE" in cypher_arg
        assert "WORKS_AT" in cypher_arg

    def test_upsert_relationship_uses_rel_map(self):
        client = _make_client()
        mock_session = MagicMock()
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        client.upsert_relationship(
            from_ref="org:1",
            to_ref="org:2",
            rel_type="subsidiary_of",
        )

        cypher_arg = mock_session.run.call_args[0][0]
        assert "SUBSIDIARY_OF" in cypher_arg

    def test_upsert_relationship_passes_correct_params(self):
        client = _make_client()
        mock_session = MagicMock()
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        client.upsert_relationship(
            from_ref="person:5",
            to_ref="org:10",
            rel_type="founded",
            confidence=95,
            evidence="Wikipedia",
        )

        _, kwargs = mock_session.run.call_args
        assert kwargs["from_ref"] == "person:5"
        assert kwargs["to_ref"] == "org:10"
        assert kwargs["confidence"] == 95
        assert kwargs["evidence"] == "Wikipedia"

    def test_upsert_relationship_on_create_on_match_in_cypher(self):
        client = _make_client()
        mock_session = MagicMock()
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        client.upsert_relationship(
            from_ref="a",
            to_ref="b",
            rel_type="controls",
        )

        cypher_arg = mock_session.run.call_args[0][0]
        assert "ON CREATE SET" in cypher_arg
        assert "ON MATCH SET" in cypher_arg

    def test_upsert_relationship_sets_valid_from_on_create(self):
        client = _make_client()
        mock_session = MagicMock()
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        client.upsert_relationship(from_ref="x", to_ref="y", rel_type="targets")

        cypher_arg = mock_session.run.call_args[0][0]
        assert "valid_from" in cypher_arg
        assert "valid_to" in cypher_arg
        assert "r.valid_from = $first_seen" in cypher_arg
        assert "r.valid_to = null" in cypher_arg

    def test_upsert_relationship_valid_from_uses_earliest_on_match(self):
        client = _make_client()
        mock_session = MagicMock()
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        ts = datetime(2023, 3, 1, tzinfo=timezone.utc)
        client.upsert_relationship(
            from_ref="p", to_ref="q", rel_type="funds", first_seen=ts
        )

        cypher_arg = mock_session.run.call_args[0][0]
        assert "$first_seen < r.valid_from" in cypher_arg

    def test_upsert_relationship_first_seen_iso_format(self):
        client = _make_client()
        mock_session = MagicMock()
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        ts = datetime(2025, 5, 10, 8, 0, 0, tzinfo=timezone.utc)
        client.upsert_relationship(
            from_ref="org:1", to_ref="org:2", rel_type="acquired", first_seen=ts
        )

        _, kwargs = mock_session.run.call_args
        assert kwargs["first_seen"] == ts.isoformat()


class TestGetSubgraph:
    def test_get_subgraph_variable_length_path_query(self):
        client = _make_client()
        mock_session = MagicMock()
        mock_session.run.return_value = iter([])
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        client.get_subgraph(ref="person:99", hops=3)

        mock_session.run.assert_called_once()
        cypher_arg = mock_session.run.call_args[0][0]
        # variable-length path pattern
        assert "*1..3" in cypher_arg
        assert "LIMIT 200" in cypher_arg

    def test_get_subgraph_caps_hops_at_5(self):
        client = _make_client()
        mock_session = MagicMock()
        mock_session.run.return_value = iter([])
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        client.get_subgraph(ref="person:1", hops=10)

        cypher_arg = mock_session.run.call_args[0][0]
        assert "*1..5" in cypher_arg

    def test_get_subgraph_default_hops_2(self):
        client = _make_client()
        mock_session = MagicMock()
        mock_session.run.return_value = iter([])
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        client.get_subgraph(ref="org:7")

        cypher_arg = mock_session.run.call_args[0][0]
        assert "*1..2" in cypher_arg

    def test_get_subgraph_returns_list(self):
        client = _make_client()
        mock_session = MagicMock()
        mock_record = MagicMock()
        mock_record.__iter__ = MagicMock(return_value=iter([("nds", []), ("rels", [])]))
        mock_session.run.return_value = iter([mock_record])
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        result = client.get_subgraph(ref="person:1")
        assert isinstance(result, list)


class TestSearchEntities:
    def test_search_entities_no_filter(self):
        client = _make_client()
        mock_session = MagicMock()
        mock_session.run.return_value = iter([])
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        client.search_entities(query="alice")

        cypher_arg = mock_session.run.call_args[0][0]
        assert "toLower" in cypher_arg
        assert "CONTAINS" in cypher_arg

    def test_search_entities_with_entity_type(self):
        client = _make_client()
        mock_session = MagicMock()
        mock_session.run.return_value = iter([])
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        client.search_entities(query="apt", entity_type="threat_actor")

        cypher_arg = mock_session.run.call_args[0][0]
        assert "ThreatActor" in cypher_arg


class TestGetEntity:
    def test_get_entity_returns_none_when_not_found(self):
        client = _make_client()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        result = client.get_entity("nonexistent:ref")
        assert result is None

    def test_get_entity_query_uses_ref(self):
        client = _make_client()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        client.get_entity("person:42")

        _, kwargs = mock_session.run.call_args
        assert kwargs["ref"] == "person:42"


class TestGetEntityRelationships:
    def test_get_entity_relationships_returns_list(self):
        client = _make_client()
        mock_session = MagicMock()
        mock_session.run.return_value = iter([])
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        result = client.get_entity_relationships("person:1")
        assert isinstance(result, list)

    def test_get_entity_relationships_query_includes_direction(self):
        client = _make_client()
        mock_session = MagicMock()
        mock_session.run.return_value = iter([])
        client._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)

        client.get_entity_relationships("org:5")

        cypher_arg = mock_session.run.call_args[0][0]
        # Should return direction info (startNode/endNode)
        assert "startNode" in cypher_arg
        assert "endNode" in cypher_arg
