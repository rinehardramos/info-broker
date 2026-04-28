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


class StreamEvent(BaseModel):
    type: str
    job_id: str | None = None
    plugin: str | None = None
    status: str | None = None
    result_count: int | None = None
    message: str | None = None
