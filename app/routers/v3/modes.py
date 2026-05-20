"""
GET /v3/modes — enumerate bundled Modes for the UI picker.

Slice A1: read-only. User-authored Modes + admin CRUD ship in slice A2.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.modes.loader import list_modes

router = APIRouter(prefix="/v3/modes", tags=["v3-modes"])


class ModeSummary(BaseModel):
    id: str
    label: str
    description: str
    version: int


@router.get("", response_model=list[ModeSummary])
async def get_modes() -> list[ModeSummary]:
    """Return all bundled Modes, ordered by id."""
    return [
        ModeSummary(
            id=m.id,
            label=m.label,
            description=m.description,
            version=m.version,
        )
        for m in list_modes()
    ]
