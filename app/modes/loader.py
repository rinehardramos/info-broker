"""
Mode loader — finds bundled YAML configs at app/modes/configs/, validates against
Mode schema, caches the parsed result.

Resolution: id → bundled YAML. (User-authored Modes from the DB will overlay
this in slice A2 when the admin surface ships.)

Unknown mode_id falls back to 'general' with a warning, never raises — the loop
must keep running even if a Mode reference is stale.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml

from app.modes.schema import Mode

log = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent / "configs"
_DEFAULT_MODE_ID = "general"


def list_modes() -> list[Mode]:
    """Enumerate all bundled Modes. Used by the dispatcher + UI picker."""
    out: list[Mode] = []
    for p in sorted(_CONFIG_DIR.glob("*.yaml")):
        try:
            out.append(_load_file(p))
        except Exception as exc:
            log.warning("mode loader: %s failed validation: %s", p.name, exc)
    return out


@lru_cache(maxsize=32)
def get_mode(mode_id: str | None) -> Mode:
    """Load a Mode by id. Falls back to 'general' on unknown id."""
    requested = (mode_id or _DEFAULT_MODE_ID).strip().lower()
    candidate = _CONFIG_DIR / f"{requested}.yaml"
    if not candidate.exists():
        if requested != _DEFAULT_MODE_ID:
            log.warning(
                "mode loader: requested '%s' not found, falling back to '%s'",
                requested, _DEFAULT_MODE_ID,
            )
        candidate = _CONFIG_DIR / f"{_DEFAULT_MODE_ID}.yaml"
    try:
        return _load_file(candidate)
    except Exception as exc:
        log.error(
            "mode loader: default '%s' failed to load (%s) — returning empty Mode",
            _DEFAULT_MODE_ID, exc,
        )
        return Mode(id=_DEFAULT_MODE_ID, label="General (fallback)")


def _load_file(path: Path) -> Mode:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Mode.model_validate(raw)


_PREFLIGHT_DEFAULT_MODE_ID = "investigation"


def get_default_mode_id(org_id: str | None) -> str:
    """Resolve the default preflight mode id for an org. Order: org → global → 'investigation'.

    Validated against the preflight mode catalog (the one the picker renders),
    NOT against the bundled YAML loop modes — they are separate concepts.
    Invalid stored ids fall through to the next tier and ultimately to
    'investigation' so the picker never preselects nothing.
    """
    from app.routers.v3.db import fetch_one  # local import avoids circulars
    from app.routers.v3.preflight import valid_preflight_mode_ids

    valid_ids = valid_preflight_mode_ids()

    if org_id:
        row = fetch_one(
            "SELECT value FROM org_settings WHERE org_id = %s AND key = 'default_mode_id'",
            (org_id,),
        )
        if row and row.get("value") and row["value"] in valid_ids:
            return row["value"]

    row = fetch_one(
        "SELECT value FROM core_settings WHERE key = 'default_mode_id'",
        (),
    )
    if row and row.get("value") and row["value"] in valid_ids:
        return row["value"]

    return _PREFLIGHT_DEFAULT_MODE_ID
