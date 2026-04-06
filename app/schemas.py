"""Pydantic request/response models for the info-broker API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProfileSummary(BaseModel):
    id: str
    first_name: str | None = None
    last_name: str | None = None
    headline: str | None = None


class ProfileDetail(ProfileSummary):
    about: str | None = None
    research_status: str | None = None
    is_smb: bool | None = None
    research_summary: str | None = None
    system_confidence_score: int | None = None
    user_grade: int | None = None


class ProfileRaw(BaseModel):
    id: str
    raw_data: dict[str, Any] | None = None


class IngestRequest(BaseModel):
    overwrite: bool = False


class IngestResponse(BaseModel):
    fetched: int
    inserted: int
    skipped: int
    errors: int


class ResearchRequest(BaseModel):
    limit: int = Field(default=5, ge=1, le=50)


class ResearchResponse(BaseModel):
    processed: int
    succeeded: int
    failed: int


class GradeRequest(BaseModel):
    grade: int = Field(..., ge=1, le=5)
    feedback: str | None = None


class GradeResponse(BaseModel):
    profile_id: str
    grade: int
    saved: bool


class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=100)


class SearchHit(BaseModel):
    id: str
    first_name: str | None = None
    last_name: str | None = None
    headline: str | None = None
    score: float | None = None


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
