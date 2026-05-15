"""Backend tests for Enhancement 3.2 — saved query templates + per-user defaults."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Minimal environment stubs so app.main imports cleanly without live services
# ---------------------------------------------------------------------------
os.environ.setdefault("INFO_BROKER_API_KEY", "test-secret-key")
os.environ.setdefault("POSTGRES_DB", "info_broker")
os.environ.setdefault("POSTGRES_USER", "user")
os.environ.setdefault("POSTGRES_PASSWORD", "password")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6333")

sys.modules.setdefault("qdrant_client", MagicMock())
sys.modules.setdefault("qdrant_client.models", MagicMock())

from fastapi.testclient import TestClient  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_USER_A = str(uuid.uuid4())
_USER_B = str(uuid.uuid4())
_NOW = datetime.now(timezone.utc)
_TEMPLATE_ID = str(uuid.uuid4())

_ENVELOPE = {
    "speed": "normal",
    "capability": "general",
    "resource": "medium",
    "depth": "search",
    "hypothesis_count": "competing",
    "mode": None,
}

_TEMPLATE_ROW = {
    "id": uuid.UUID(_TEMPLATE_ID),
    "user_id": uuid.UUID(_USER_A),
    "name": "My Template",
    "query": "who is John Doe",
    "envelope": _ENVELOPE,
    "strategy_id": "media_identification",
    "last_used": None,
    "use_count": 0,
    "created_at": _NOW,
}

_TEMPLATE_ROW_USED = {
    **_TEMPLATE_ROW,
    "last_used": _NOW,
    "use_count": 1,
}

_DEFAULT_ENVELOPE_ROW = {"envelope": _ENVELOPE}


def _user(uid: str) -> dict:
    return {"id": uid, "username": "tester", "is_active": True, "role": "analyst", "is_admin": False}


def _make_client(user_id: str = _USER_A):
    from app.main import app
    from app.routers.v3.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _user(user_id)
    return TestClient(app)


_DB = "app.routers.v3.templates"


# ---------------------------------------------------------------------------
# test_create_template_returns_row
# ---------------------------------------------------------------------------

def test_create_template_returns_row():
    client = _make_client(_USER_A)
    with patch(f"{_DB}.fetch_one", return_value=_TEMPLATE_ROW):
        resp = client.post("/v3/templates", json={
            "name": "My Template",
            "query": "who is John Doe",
            "envelope": _ENVELOPE,
            "strategy_id": "media_identification",
        })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Template"
    assert data["query"] == "who is John Doe"
    assert data["strategy_id"] == "media_identification"
    assert data["use_count"] == 0
    assert data["last_used"] is None


# ---------------------------------------------------------------------------
# test_create_template_upserts_on_duplicate_name
# ---------------------------------------------------------------------------

def test_create_template_upserts_on_duplicate_name():
    """Second POST with the same name should still return 201 (upsert path)."""
    client = _make_client(_USER_A)
    updated_row = {**_TEMPLATE_ROW, "query": "updated query"}
    with patch(f"{_DB}.fetch_one", return_value=updated_row):
        resp = client.post("/v3/templates", json={
            "name": "My Template",
            "query": "updated query",
            "envelope": _ENVELOPE,
            "strategy_id": "media_identification",
        })
    assert resp.status_code == 201
    assert resp.json()["query"] == "updated query"


# ---------------------------------------------------------------------------
# test_list_templates_ordered_by_last_used
# ---------------------------------------------------------------------------

def test_list_templates_ordered_by_last_used():
    client = _make_client(_USER_A)
    template_b_id = str(uuid.uuid4())
    row_b = {**_TEMPLATE_ROW, "id": uuid.UUID(template_b_id), "name": "B", "last_used": _NOW}
    # row_b (last_used set) should come before _TEMPLATE_ROW (last_used=None)
    ordered_rows = [row_b, _TEMPLATE_ROW]
    with patch(f"{_DB}.fetch_all", return_value=ordered_rows):
        resp = client.get("/v3/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "B"  # most recently used first
    assert data[1]["name"] == "My Template"  # null last_used last


# ---------------------------------------------------------------------------
# test_use_template_bumps_last_used_and_count
# ---------------------------------------------------------------------------

def test_use_template_bumps_last_used_and_count():
    client = _make_client(_USER_A)
    with patch(f"{_DB}.fetch_one", return_value=_TEMPLATE_ROW_USED):
        resp = client.post(f"/v3/templates/{_TEMPLATE_ID}/use")
    assert resp.status_code == 200
    data = resp.json()
    assert data["use_count"] == 1
    assert data["last_used"] is not None


# ---------------------------------------------------------------------------
# test_delete_template_owner_only
# ---------------------------------------------------------------------------

def test_delete_template_owner_only():
    """User B cannot delete User A's template."""
    client_b = _make_client(_USER_B)
    existing = {**_TEMPLATE_ROW, "user_id": uuid.UUID(_USER_A)}
    with patch(f"{_DB}.fetch_one", return_value=existing):
        resp = client_b.delete(f"/v3/templates/{_TEMPLATE_ID}")
    assert resp.status_code == 403


def test_delete_template_owner_succeeds():
    """Owner can delete their own template."""
    client_a = _make_client(_USER_A)
    existing = {**_TEMPLATE_ROW, "user_id": uuid.UUID(_USER_A)}
    with patch(f"{_DB}.fetch_one", return_value=existing), \
         patch(f"{_DB}.execute"):
        resp = client_a.delete(f"/v3/templates/{_TEMPLATE_ID}")
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# test_get_defaults_returns_envelope
# ---------------------------------------------------------------------------

def test_get_defaults_returns_envelope():
    client = _make_client(_USER_A)
    with patch(f"{_DB}.fetch_one", return_value=_DEFAULT_ENVELOPE_ROW):
        resp = client.get("/v3/user/defaults")
    assert resp.status_code == 200
    data = resp.json()
    assert data["envelope"]["speed"] == "normal"
    assert data["envelope"]["capability"] == "general"


def test_get_defaults_returns_empty_when_not_set():
    """If no row exists yet, returns empty envelope dict."""
    client = _make_client(_USER_A)
    with patch(f"{_DB}.fetch_one", return_value=None):
        resp = client.get("/v3/user/defaults")
    assert resp.status_code == 200
    assert resp.json()["envelope"] == {}


# ---------------------------------------------------------------------------
# test_put_defaults_updates_envelope
# ---------------------------------------------------------------------------

def test_put_defaults_updates_envelope():
    client = _make_client(_USER_A)
    updated = {"envelope": {**_ENVELOPE, "speed": "fast"}}
    with patch(f"{_DB}.fetch_one", return_value=updated):
        resp = client.put("/v3/user/defaults", json={"envelope": {**_ENVELOPE, "speed": "fast"}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["envelope"]["speed"] == "fast"
