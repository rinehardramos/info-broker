from __future__ import annotations
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


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
    created_at: datetime


class PreferencesIn(BaseModel):
    theme: str | None = None          # 'navy' | 'hacker'
    column_layout: dict | None = None


class PreferencesOut(BaseModel):
    theme: str
    column_layout: dict


class PluginConfigIn(BaseModel):
    config: dict


class PluginConfigOut(BaseModel):
    plugin_name: str
    config: dict


class CoreSettingIn(BaseModel):
    key: str
    value: str
    is_secret: bool = False


class CoreSettingsOut(BaseModel):
    settings: dict[str, str | None]   # secrets returned as None


class MonitorIn(BaseModel):
    name: str
    type: str                          # 'rss' | 'twitter' | 'facebook' | 'linkedin'
    target: str
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
    message: str
    context_job_id: str | None = None


class AgentMessageOut(BaseModel):
    job_id: str
    status: str = "pending"


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
