from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

MAX_BUDGET = 20


class SearchJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TokenRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    deep_search: bool = False
    max_parallel: int | None = None
    max_budget: int = Field(default=5, ge=1, le=20)
    plugins: list[str] | None = None
    callback_url: str | None = None

    @field_validator("max_budget", mode="before")
    @classmethod
    def clamp_budget(cls, v: int) -> int:
        if isinstance(v, int) and v > MAX_BUDGET:
            return MAX_BUDGET
        return v


class SearchSubmitResponse(BaseModel):
    job_id: uuid.UUID
    status: SearchJobStatus
    status_url: str
    results_url: str


class SearchJobResponse(BaseModel):
    job_id: uuid.UUID
    status: SearchJobStatus
    query: str
    total_results: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class SearchResultItem(BaseModel):
    id: uuid.UUID
    plugin: str
    title: str
    url: str | None = None
    snippet: str
    published_at: datetime | None = None
    is_deep_child: bool = False
    scores: dict[str, float]
    feedback: dict[str, Any] | None = None


class SearchResultsResponse(BaseModel):
    job_id: uuid.UUID
    query: str
    status: SearchJobStatus
    total_results: int
    results: list[SearchResultItem]
    aggregate_confidence: dict[str, Any] | None = None


class SearchHistoryItem(BaseModel):
    job_id: uuid.UUID
    query: str
    status: SearchJobStatus
    total_results: int | None = None
    aggregate_confidence: dict[str, Any] | None = None
    created_at: datetime


class SearchHistoryResponse(BaseModel):
    jobs: list[SearchHistoryItem]
    total: int
    page: int
    per_page: int


class SearchFeedbackRequest(BaseModel):
    interest: int = Field(ge=1, le=5)
    relevance: int = Field(ge=1, le=5)
    usefulness: int = Field(ge=1, le=5)
    comment: str | None = None


class SearchFeedbackResponse(BaseModel):
    id: uuid.UUID
    result_id: uuid.UUID
    saved: bool
