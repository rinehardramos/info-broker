from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class EntityObservationIn(BaseModel):
    entity_ref: str = Field(..., max_length=512)
    entity_type: str = Field(..., max_length=64)
    attribute: str = Field(..., max_length=128)
    value: str
    confidence: int = Field(..., ge=0, le=100)
    source_run_id: Optional[str] = None
    source_tool: str = Field(..., max_length=128)
    source_url: Optional[str] = None
    observed_at: Optional[datetime] = None


class RelationshipObservationIn(BaseModel):
    from_entity_ref: str = Field(..., max_length=512)
    to_entity_ref: str = Field(..., max_length=512)
    relationship_type: str = Field(..., max_length=64)
    confidence: int = Field(..., ge=0, le=100)
    evidence: Optional[str] = None
    source_run_id: Optional[str] = None
    source_tool: str = Field(..., max_length=128)
    observed_at: Optional[datetime] = None


class McpToolCallIn(BaseModel):
    tool_name: str = Field(..., max_length=128)
    node_type: Optional[str] = Field(None, max_length=64)
    call_id: str
    parent_call_id: Optional[str] = None
    caller_identity: str = Field(..., max_length=256)
    session_id: Optional[str] = None
    input_params: Optional[dict] = None


class EntityOut(BaseModel):
    ref: str
    entity_type: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    confidence: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    attributes: dict = Field(default_factory=dict)
    observation_count: int = 0


class RelationshipOut(BaseModel):
    from_ref: str
    to_ref: str
    relationship_type: str
    confidence: int = 0
    evidence: Optional[str] = None
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    observation_count: int = 0


class McpSessionOut(BaseModel):
    id: str
    caller_identity: str
    session_type: str
    status: str
    tool_call_count: int = 0
    context: dict = Field(default_factory=dict)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
