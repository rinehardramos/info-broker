import pytest
from pydantic import ValidationError

from app.knowledge.models import (
    EntityObservationIn,
    McpToolCallIn,
    RelationshipObservationIn,
)


def test_entity_observation_requires_fields():
    with pytest.raises(ValidationError):
        EntityObservationIn()

    obs = EntityObservationIn(
        entity_ref="person:john-doe",
        entity_type="person",
        attribute="full_name",
        value="John Doe",
        confidence=80,
        source_tool="ddg_search",
    )
    assert obs.entity_ref == "person:john-doe"
    assert obs.confidence == 80


def test_entity_observation_confidence_bounds():
    base = dict(
        entity_ref="person:jane",
        entity_type="person",
        attribute="full_name",
        value="Jane",
        source_tool="ddg_search",
    )

    with pytest.raises(ValidationError):
        EntityObservationIn(**base, confidence=101)

    with pytest.raises(ValidationError):
        EntityObservationIn(**base, confidence=-1)


def test_relationship_observation_requires_fields():
    with pytest.raises(ValidationError):
        RelationshipObservationIn()

    rel = RelationshipObservationIn(
        from_entity_ref="person:john-doe",
        to_entity_ref="org:acme-corp",
        relationship_type="works_at",
        confidence=75,
        source_tool="linkedin_profile",
    )
    assert rel.relationship_type == "works_at"
    assert rel.evidence is None


def test_mcp_tool_call_log_requires_fields():
    call = McpToolCallIn(
        tool_name="ddg_search",
        call_id="call-abc-123",
        caller_identity="agent/default",
    )
    assert call.tool_name == "ddg_search"
    assert call.node_type is None
    assert call.input_params is None
