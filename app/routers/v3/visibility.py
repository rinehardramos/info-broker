"""Visibility settings — admin toggles for which Modes / Templates users see (#107).

Storage reuses the existing key/value pattern:
  - core_settings.value (JSON-encoded dict) for the global default
  - org_settings.value (JSON-encoded dict) for per-org overrides

Resolution: org override → global default → all visible (missing key = visible).

Two kinds supported today: "mode" and "template". Adding a new kind only
requires updating KNOWN_KINDS and _kind_known_ids().
"""
from __future__ import annotations

import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_one


router = APIRouter(prefix="/v3/settings", tags=["v3-settings"])


# ---------------------------------------------------------------------------
# Kind registry
# ---------------------------------------------------------------------------

VisibilityKind = Literal["mode", "template"]
KNOWN_KINDS: tuple[VisibilityKind, ...] = ("mode", "template")


def _kind_known_ids(kind: VisibilityKind) -> set[str]:
    """Return the set of *valid* ids for a kind. Used to reject PUT requests
    that toggle visibility on unknown ids.
    """
    if kind == "mode":
        from app.routers.v3.preflight import valid_preflight_mode_ids
        return valid_preflight_mode_ids()
    if kind == "template":
        from app.routers.v3.investigation_templates import INVESTIGATION_TEMPLATES
        return {t["id"] for t in INVESTIGATION_TEMPLATES}
    return set()


def _settings_key(kind: VisibilityKind) -> str:
    return f"{kind}_visibility"


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _load(kind: VisibilityKind, org_id: Optional[str]) -> tuple[dict | None, dict | None]:
    """Return (org_value, global_value). Either may be None when unset."""
    key = _settings_key(kind)

    org_value: dict | None = None
    if org_id:
        row = fetch_one(
            "SELECT value FROM org_settings WHERE org_id = %s AND key = %s",
            (org_id, key),
        )
        if row and row.get("value"):
            try:
                org_value = json.loads(row["value"])
                if not isinstance(org_value, dict):
                    org_value = None
            except (json.JSONDecodeError, TypeError):
                org_value = None

    global_value: dict | None = None
    grow = fetch_one(
        "SELECT value FROM core_settings WHERE key = %s", (key,),
    )
    if grow and grow.get("value"):
        try:
            global_value = json.loads(grow["value"])
            if not isinstance(global_value, dict):
                global_value = None
        except (json.JSONDecodeError, TypeError):
            global_value = None

    return org_value, global_value


def _resolve(org_value: dict | None, global_value: dict | None) -> dict[str, bool]:
    """Merge org over global. Missing keys mean visible (= no entry)."""
    merged: dict[str, bool] = {}
    if global_value:
        merged.update({k: bool(v) for k, v in global_value.items()})
    if org_value:
        merged.update({k: bool(v) for k, v in org_value.items()})
    return merged


def is_id_visible(kind: VisibilityKind, item_id: str, org_id: Optional[str]) -> bool:
    """Convenience: True if the given id is visible for the org (or globally
    when org_id is None). Missing entry = visible.
    """
    org_value, global_value = _load(kind, org_id)
    resolved = _resolve(org_value, global_value)
    return resolved.get(item_id, True)


def filter_visible(
    kind: VisibilityKind,
    items: list[dict],
    org_id: Optional[str],
    id_key: str = "id",
) -> list[dict]:
    """Filter a list of {id, ...} dicts by resolved visibility for the org."""
    org_value, global_value = _load(kind, org_id)
    resolved = _resolve(org_value, global_value)
    if not resolved:
        return items
    return [it for it in items if resolved.get(it[id_key], True)]


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class VisibilityOut(BaseModel):
    kind: str
    org: dict[str, bool] | None
    global_: dict[str, bool] | None = Field(alias="global")
    resolved: dict[str, bool]
    known_ids: list[str]

    model_config = {"populate_by_name": True}


class VisibilityIn(BaseModel):
    scope: Literal["org", "global"]
    value: dict[str, bool] | None  # None clears the override


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _kind_or_404(kind: str) -> VisibilityKind:
    if kind not in KNOWN_KINDS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown visibility kind '{kind}'. Known: {sorted(KNOWN_KINDS)}",
        )
    return kind  # type: ignore[return-value]


@router.get("/{kind}_visibility", response_model=VisibilityOut)
def get_visibility(kind: str, user: dict = Depends(get_current_user)) -> VisibilityOut:
    k = _kind_or_404(kind)
    org_id = str(user["org_id"]) if user.get("org_id") else None
    org_value, global_value = _load(k, org_id)
    resolved = _resolve(org_value, global_value)
    return VisibilityOut(
        kind=k,
        org=org_value,
        **{"global": global_value},
        resolved=resolved,
        known_ids=sorted(_kind_known_ids(k)),
    )


@router.put("/{kind}_visibility", response_model=VisibilityOut)
def put_visibility(
    kind: str,
    body: VisibilityIn,
    user: dict = Depends(get_current_user),
) -> VisibilityOut:
    k = _kind_or_404(kind)

    # Authz mirrors put_default_mode: global requires is_admin, org requires role=admin.
    if body.scope == "global":
        if not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Global visibility requires admin")
    else:  # "org"
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Org visibility requires org admin role")
        if not user.get("org_id"):
            raise HTTPException(status_code=400, detail="User has no org")

    # Validate every id in the payload against the kind's known ids — prevents
    # typos persisting as silent no-ops.
    if body.value is not None:
        known = _kind_known_ids(k)
        unknown = sorted(set(body.value.keys()) - known)
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown {k} ids: {unknown}. Known: {sorted(known)}",
            )

    key = _settings_key(k)

    if body.scope == "global":
        if body.value is None:
            execute("DELETE FROM core_settings WHERE key = %s", (key,))
        else:
            execute(
                """INSERT INTO core_settings (key, value, is_secret)
                   VALUES (%s, %s, false)
                   ON CONFLICT (key) DO UPDATE
                   SET value = EXCLUDED.value, updated_at = now()""",
                (key, json.dumps(body.value)),
            )
    else:
        org_id = str(user["org_id"])
        if body.value is None:
            execute(
                "DELETE FROM org_settings WHERE org_id = %s AND key = %s",
                (org_id, key),
            )
        else:
            execute(
                """INSERT INTO org_settings (org_id, key, value)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (org_id, key) DO UPDATE
                   SET value = EXCLUDED.value, updated_at = now()""",
                (org_id, key, json.dumps(body.value)),
            )

    return get_visibility(kind=kind, user=user)
