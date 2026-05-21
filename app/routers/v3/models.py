from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(..., max_length=255)
    password: str = Field(..., max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: UUID
    username: str
    email: str | None
    is_active: bool
    is_admin: bool = False
    created_at: datetime
    password_set: bool = True
    oauth_provider: str | None = None
    avatar_url: str | None = None
    display_name: str | None = None
    timezone: str | None = None
    locale: str | None = None


class UserProfileIn(BaseModel):
    """PATCH /v3/users/me — non-admin self-service personalization."""
    display_name: str | None = None
    avatar_url: str | None = None
    timezone: str | None = None
    locale: str | None = None


class PreferencesIn(BaseModel):
    theme: str | None = None          # 'navy' | 'hacker'
    column_layout: dict | None = None
    agent_pipeline_id: str | None = None


class PreferencesOut(BaseModel):
    theme: str
    column_layout: dict
    agent_pipeline_id: str | None = None


class PluginConfigIn(BaseModel):
    config: dict


class PluginConfigOut(BaseModel):
    plugin_name: str
    config: dict


class CoreSettingIn(BaseModel):
    key: str = Field(..., max_length=255)
    value: str = Field(..., max_length=4000)
    is_secret: bool = False


class CoreSettingsOut(BaseModel):
    settings: dict[str, str | None]   # secrets returned as None


class MonitorIn(BaseModel):
    name: str = Field(..., max_length=255)
    type: str = Field(..., max_length=64)   # 'rss' | 'twitter' | 'facebook' | 'linkedin'
    target: str = Field(..., max_length=4000)
    poll_interval_minutes: int = 60


class MonitorOut(BaseModel):
    id: UUID
    name: str
    type: str
    target: str
    poll_interval_minutes: int
    last_polled_at: datetime | None
    last_item_count: int
    is_active: bool


class AgentMessageIn(BaseModel):
    message: str = Field(..., max_length=8000)
    session_id: str | None = None

    @field_validator("message")
    @classmethod
    def _sanitize_message(cls, v: str) -> str:
        from app.security import sanitize_user_input
        return sanitize_user_input(v, max_length=8000)
    context_job_id: str | None = None
    use_intelligent_search: bool = False
    parent_run_id: str | None = None
    # Mode id (e.g. "general", "kyc_edd"). Drives loop framing, source-class
    # weights, hypothesis seeds, output template. See app/modes/configs/.
    mode: str | None = None


class AgentMessageOut(BaseModel):
    job_id: str | None = None
    session_id: str = ""
    status: str = "pending"
    reply: str | None = None
    mode: str = "investigation"
    question: str | None = None           # PreFlight clarification question (mode="question")
    options: list[str] | None = None      # PreFlight answer options


class AgentSessionOut(BaseModel):
    id: str
    user_id: str
    genesis_query: str
    status: str
    created_at: datetime
    archived_at: datetime | None = None
    run_count: int = 0
    turn_count: int = 0
    accumulated_summary: str = ""
    conversation_thread: list[dict[str, Any]] = []
    key_findings: list[dict[str, Any]] = []
    entity_type: str = "unknown"


class AgentPipelineOut(BaseModel):
    pipeline_id: str
    pipeline_name: str
    is_system: bool


class JobOut(BaseModel):
    id: str
    status: str
    query: str
    created_at: datetime
    completed_at: datetime | None
    result_count: int


class ResultGradeIn(BaseModel):
    grade: str  # target | interesting | amazing | not_close | undecided


class StreamEvent(BaseModel):
    type: str
    job_id: str | None = None
    plugin: str | None = None
    status: str | None = None
    result_count: int | None = None
    message: str | None = None


class ApifyRunConfigOut(BaseModel):
    job_titles: list[str]
    locations: list[str]
    max_items: int
    scraper_mode: str
    auto_query_segmentation: bool
    auto_query_segmentation_levels: list[str]
    auto_query_segmentation_countries: list[str]
    recently_changed_jobs: bool
    recently_posted_on_linkedin: bool


class ApifyConfigOut(BaseModel):
    api_key: str | None        # None = not configured; masked bullet string = set
    actor_id: str | None
    run_config: ApifyRunConfigOut


class ApifyConfigIn(BaseModel):
    api_key: str | None = None
    actor_id: str | None = None
    job_titles: list[str] | None = None
    locations: list[str] | None = None
    max_items: int | None = None
    scraper_mode: str | None = None
    auto_query_segmentation: bool | None = None
    auto_query_segmentation_levels: list[str] | None = None
    auto_query_segmentation_countries: list[str] | None = None
    recently_changed_jobs: bool | None = None
    recently_posted_on_linkedin: bool | None = None


class ApifyRunIn(BaseModel):
    job_titles: list[str]
    locations: list[str]
    max_items: int = 300
    scraper_mode: str = "Full + email search"
    auto_query_segmentation: bool = False
    auto_query_segmentation_levels: list[str] = ["country", "industry", "seniority_level"]
    auto_query_segmentation_countries: list[str] = []
    recently_changed_jobs: bool = False
    recently_posted_on_linkedin: bool = False


class ApifyRunOut(BaseModel):
    id: UUID
    apify_run_id: str | None
    status: str
    item_count: int
    started_at: datetime
    finished_at: datetime | None


class ApifyRunStatusOut(BaseModel):
    status: str
    item_count: int
    apify_run_id: str | None


class LinkedInProfileOut(BaseModel):
    id: str
    first_name: str | None
    last_name: str | None
    headline: str | None
    about: str | None
    grade: str | None = None


class LinkedInProfileGradeIn(BaseModel):
    grade: str  # target | interesting | amazing | not_close | undecided


# --- Pipeline models ---

class PipelineNodeIn(BaseModel):
    id: UUID | None = None      # frontend-generated UUID; used as DB node ID
    node_type: str
    label: str
    config: dict = {}
    position_x: int = 0
    position_y: int = 0


class PipelineNodeOut(PipelineNodeIn):
    id: UUID
    category: str = ""


class PipelineEdgeIn(BaseModel):
    source_node_id: UUID
    target_node_id: UUID
    edge_type: str = "results"


class PipelineEdgeOut(PipelineEdgeIn):
    id: UUID


class PipelineIn(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = Field(None, max_length=4000)
    nodes: list[PipelineNodeIn] = []
    edges: list[PipelineEdgeIn] = []

    @field_validator("name")
    @classmethod
    def _sanitize_name(cls, v: str) -> str:
        from app.security import sanitize_user_input
        return sanitize_user_input(v, max_length=255)

    @field_validator("description")
    @classmethod
    def _sanitize_desc(cls, v: str | None) -> str | None:
        if v is None:
            return None
        from app.security import sanitize_user_input
        return sanitize_user_input(v, max_length=4000)


class PipelineOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_system: bool = False
    created_at: datetime
    updated_at: datetime


class PipelineDetailOut(PipelineOut):
    nodes: list[PipelineNodeOut]
    edges: list[PipelineEdgeOut]


class PipelineStepRunOut(BaseModel):
    id: UUID
    node_id: UUID
    status: str
    item_count: int
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None


class PipelineRunOut(BaseModel):
    id: UUID
    pipeline_id: UUID
    status: str
    trigger_type: str
    started_at: datetime
    finished_at: datetime | None
    error_message: str | None = None
    query: str | None = None


class ResearchTrailOut(BaseModel):
    query: str
    entity_type: str | None
    findings: list[dict]
    trail: dict | list
    tool_calls: int
    suggested_pipeline: dict | None = None
    analysis: dict | None = None


class PipelineRunDetailOut(PipelineRunOut):
    steps: list[PipelineStepRunOut]
    research: ResearchTrailOut | None = None


class PipelineRunSummaryOut(BaseModel):
    id: UUID
    pipeline_id: UUID
    pipeline_name: str
    status: str
    trigger_type: str
    started_at: datetime
    finished_at: datetime | None
    step_count: int
    steps_done: int
    error_message: str | None = None
    query: str | None = None


class NodeTypeOut(BaseModel):
    node_type: str
    display_name: str
    category: str
    config_schema: dict


class PluginRequestOut(BaseModel):
    id: UUID
    spec: dict
    status: str
    created_at: datetime
    reviewed_at: datetime | None


class PluginRequestStatusIn(BaseModel):
    status: str  # "approved" | "rejected" | "implemented"


class DefaultModeOut(BaseModel):
    """Resolved default mode plus its provenance, for the calling user's org."""
    resolved: str
    source: Literal["org", "global", "fallback"]
    org_value: str | None
    global_value: str | None


class DefaultModeIn(BaseModel):
    """Write-side payload for PUT [REDACTED:high-entropy-base64:25ch:hash=d1ee1236]."""
    value: str | None  # null clears the override at this scope
    scope: Literal["global", "org"]
