"""Admin CRUD endpoints for llm_pricing — /v3/admin/llm-pricing."""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.routers.v3.auth import require_admin
from app.routers.v3.db import execute, fetch_all, fetch_one

router = APIRouter(prefix="/v3/admin/llm-pricing", tags=["v3-admin-pricing"])
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class PricingRowIn(BaseModel):
    model_id: str
    provider: str
    input_usd_per_1m: float
    output_usd_per_1m: float
    cache_creation_usd_per_1m: Optional[float] = None
    cache_read_usd_per_1m: Optional[float] = None
    notes: Optional[str] = None


class PricingRowOut(BaseModel):
    id: str
    model_id: str
    provider: str
    input_usd_per_1m: float
    output_usd_per_1m: float
    cache_creation_usd_per_1m: Optional[float] = None
    cache_read_usd_per_1m: Optional[float] = None
    effective_from: str
    updated_at: str
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _row_to_out(row: dict) -> dict:
    """Convert a DB row dict to a serialisable dict matching PricingRowOut."""
    return {
        "id": str(row["id"]),
        "model_id": row["model_id"],
        "provider": row["provider"],
        "input_usd_per_1m": float(row["input_usd_per_1m"]),
        "output_usd_per_1m": float(row["output_usd_per_1m"]),
        "cache_creation_usd_per_1m": (
            float(row["cache_creation_usd_per_1m"])
            if row.get("cache_creation_usd_per_1m") is not None else None
        ),
        "cache_read_usd_per_1m": (
            float(row["cache_read_usd_per_1m"])
            if row.get("cache_read_usd_per_1m") is not None else None
        ),
        "effective_from": row["effective_from"].isoformat() if hasattr(row["effective_from"], "isoformat") else str(row["effective_from"]),
        "updated_at": row["updated_at"].isoformat() if hasattr(row["updated_at"], "isoformat") else str(row["updated_at"]),
        "notes": row.get("notes"),
    }


def _invalidate_cache(model_id: str) -> None:
    """Invalidate the in-process PricingResolver cache for model_id."""
    try:
        import app.observability.pricing_ref as _pricing_ref
        resolver = _pricing_ref._resolver
        if resolver is not None:
            resolver.invalidate(model_id)
    except Exception as exc:  # pragma: no cover
        log.warning("pricing cache invalidation failed for %r: %s", model_id, exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/history", response_model=list[PricingRowOut])
def get_pricing_history(
    model_id: str = Query(..., description="Model ID to fetch history for"),
    _user: dict = Depends(require_admin),
):
    """Return all pricing rows for a given model_id, newest effective_from first."""
    rows = fetch_all(
        """
        SELECT id, model_id, provider,
               input_usd_per_1m, output_usd_per_1m,
               cache_creation_usd_per_1m, cache_read_usd_per_1m,
               effective_from, updated_at, notes
        FROM llm_pricing
        WHERE model_id = %s
        ORDER BY effective_from DESC
        """,
        (model_id,),
    )
    return [_row_to_out(r) for r in rows]


@router.get("", response_model=list[PricingRowOut])
def list_current_pricing(_user: dict = Depends(require_admin)):
    """Return the current (newest effective_from <= now()) price row per model."""
    rows = fetch_all(
        """
        SELECT DISTINCT ON (model_id)
               id, model_id, provider,
               input_usd_per_1m, output_usd_per_1m,
               cache_creation_usd_per_1m, cache_read_usd_per_1m,
               effective_from, updated_at, notes
        FROM llm_pricing
        WHERE effective_from <= now()
        ORDER BY model_id, effective_from DESC
        """,
    )
    return [_row_to_out(r) for r in rows]


@router.post("", response_model=PricingRowOut, status_code=status.HTTP_201_CREATED)
def create_pricing_row(body: PricingRowIn, user: dict = Depends(require_admin)):
    """Insert a new llm_pricing row and invalidate the in-process cache."""
    row = fetch_one(
        """
        INSERT INTO llm_pricing
            (model_id, provider, input_usd_per_1m, output_usd_per_1m,
             cache_creation_usd_per_1m, cache_read_usd_per_1m, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, model_id, provider,
                  input_usd_per_1m, output_usd_per_1m,
                  cache_creation_usd_per_1m, cache_read_usd_per_1m,
                  effective_from, updated_at, notes
        """,
        (
            body.model_id,
            body.provider,
            body.input_usd_per_1m,
            body.output_usd_per_1m,
            body.cache_creation_usd_per_1m,
            body.cache_read_usd_per_1m,
            body.notes,
        ),
    )
    if row is None:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Insert failed")

    _invalidate_cache(body.model_id)
    log.info(
        "audit: llm_pricing row created id=%s model_id=%r by user=%s",
        row["id"],
        body.model_id,
        user.get("id"),
    )
    return _row_to_out(row)


@router.delete("/{pricing_id}", status_code=status.HTTP_200_OK)
def delete_pricing_row(pricing_id: str, user: dict = Depends(require_admin)):
    """Delete an llm_pricing row by ID. Returns 404 if not found."""
    row = fetch_one(
        "SELECT id, model_id FROM llm_pricing WHERE id = %s",
        (pricing_id,),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Pricing row not found")

    model_id = row["model_id"]
    execute("DELETE FROM llm_pricing WHERE id = %s", (pricing_id,))

    _invalidate_cache(model_id)
    log.info(
        "audit: llm_pricing row deleted id=%s model_id=%r by user=%s",
        pricing_id,
        model_id,
        user.get("id"),
    )
    return {"deleted": pricing_id, "model_id": model_id}
