"""Tests for default mode resolution (org → global → fallback)."""
from __future__ import annotations

import uuid

import pytest

from app.modes.loader import get_default_mode_id
from app.routers.v3.db import execute, fetch_one


@pytest.fixture
def clean_settings():
    """Wipe default_mode_id rows before and after each test."""
    execute("DELETE FROM core_settings WHERE key = 'default_mode_id'", ())
    execute("DELETE FROM org_settings WHERE key = 'default_mode_id'", ())
    yield
    execute("DELETE FROM core_settings WHERE key = 'default_mode_id'", ())
    execute("DELETE FROM org_settings WHERE key = 'default_mode_id'", ())


def test_resolution_falls_back_to_general(clean_settings):
    assert get_default_mode_id(None) == "investigation"
    assert get_default_mode_id(str(uuid.uuid4())) == "investigation"


def test_resolution_uses_global(clean_settings):
    execute(
        "INSERT INTO core_settings (key, value, is_secret) VALUES ('default_mode_id', 'quick_lookup', false)",
        (),
    )
    assert get_default_mode_id(None) == "quick_lookup"
    assert get_default_mode_id(str(uuid.uuid4())) == "quick_lookup"


def test_org_overrides_global(clean_settings):
    org_id = str(uuid.uuid4())
    execute(
        "INSERT INTO core_settings (key, value, is_secret) VALUES ('default_mode_id', 'investigation', false)",
        (),
    )
    execute(
        "INSERT INTO org_settings (org_id, key, value) VALUES (%s, 'default_mode_id', 'leads_generation')",
        (org_id,),
    )
    assert get_default_mode_id(org_id) == "leads_generation"


def test_invalid_org_value_falls_through_to_global(clean_settings):
    org_id = str(uuid.uuid4())
    execute(
        "INSERT INTO core_settings (key, value, is_secret) VALUES ('default_mode_id', 'leads_generation', false)",
        (),
    )
    execute(
        "INSERT INTO org_settings (org_id, key, value) VALUES (%s, 'default_mode_id', 'bogus_id')",
        (org_id,),
    )
    assert get_default_mode_id(org_id) == "leads_generation"


def test_invalid_global_value_falls_through_to_general(clean_settings):
    execute(
        "INSERT INTO core_settings (key, value, is_secret) VALUES ('default_mode_id', 'bogus_id', false)",
        (),
    )
    assert get_default_mode_id(None) == "investigation"


from fastapi.testclient import TestClient


def _client_with_user(is_admin: bool = False, role: str = "analyst", org_id: str | None = None):
    """Build a TestClient + a Bearer token for a freshly created test user."""
    from app.main import app
    from app.routers.v3.auth import _make_access_token
    from app.routers.v3.db import execute

    user_id = str(uuid.uuid4())
    org = org_id or str(uuid.uuid4())
    execute(
        """INSERT INTO ui_users (id, username, email, password_hash, is_active, is_admin, role, org_id)
           VALUES (%s, %s, %s, '', true, %s, %s, %s)""",
        (user_id, f"u-{user_id[:8]}", f"{user_id[:8]}@ex.com", is_admin, role, org),
    )
    token = _make_access_token(user_id)
    client = TestClient(app)
    return client, {"Authorization": f"Bearer {token}"}, user_id, org


def test_get_default_mode_returns_fallback(clean_settings):
    client, headers, _, _ = _client_with_user()
    r = client.get("/v3/settings/default_mode", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "resolved": "investigation",
        "source": "fallback",
        "org_value": None,
        "global_value": None,
    }


def test_get_default_mode_returns_global_when_set(clean_settings):
    execute(
        "INSERT INTO core_settings (key, value, is_secret) VALUES ('default_mode_id', 'leads_generation', false)",
        (),
    )
    client, headers, _, _ = _client_with_user()
    r = client.get("/v3/settings/default_mode", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["resolved"] == "leads_generation"
    assert body["source"] == "global"
    assert body["org_value"] is None
    assert body["global_value"] == "leads_generation"


def test_get_default_mode_returns_org_override(clean_settings):
    client, headers, _, org_id = _client_with_user()
    execute(
        "INSERT INTO core_settings (key, value, is_secret) VALUES ('default_mode_id', 'investigation', false)",
        (),
    )
    execute(
        "INSERT INTO org_settings (org_id, key, value) VALUES (%s, 'default_mode_id', 'quick_lookup')",
        (org_id,),
    )
    r = client.get("/v3/settings/default_mode", headers=headers)
    body = r.json()
    assert body == {
        "resolved": "quick_lookup",
        "source": "org",
        "org_value": "quick_lookup",
        "global_value": "investigation",
    }


def test_put_global_requires_is_admin(clean_settings):
    client, headers, _, _ = _client_with_user(is_admin=False, role="admin")
    r = client.put(
        "/v3/settings/default_mode",
        headers=headers,
        json={"value": "leads_generation", "scope": "global"},
    )
    assert r.status_code == 403


def test_put_org_requires_org_admin_role(clean_settings):
    client, headers, _, _ = _client_with_user(is_admin=False, role="analyst")
    r = client.put(
        "/v3/settings/default_mode",
        headers=headers,
        json={"value": "leads_generation", "scope": "org"},
    )
    assert r.status_code == 403


def test_put_rejects_unknown_mode_id(clean_settings):
    client, headers, _, _ = _client_with_user(is_admin=True)
    r = client.put(
        "/v3/settings/default_mode",
        headers=headers,
        json={"value": "totally_made_up", "scope": "global"},
    )
    assert r.status_code == 400


def test_put_global_persists_value(clean_settings):
    client, headers, _, _ = _client_with_user(is_admin=True)
    r = client.put(
        "/v3/settings/default_mode",
        headers=headers,
        json={"value": "quick_lookup", "scope": "global"},
    )
    assert r.status_code == 200
    row = fetch_one("SELECT value FROM core_settings WHERE key = 'default_mode_id'", ())
    assert row["value"] == "quick_lookup"


def test_put_org_persists_value(clean_settings):
    client, headers, _, org_id = _client_with_user(is_admin=False, role="admin")
    r = client.put(
        "/v3/settings/default_mode",
        headers=headers,
        json={"value": "leads_generation", "scope": "org"},
    )
    assert r.status_code == 200
    row = fetch_one(
        "SELECT value FROM org_settings WHERE org_id = %s AND key = 'default_mode_id'",
        (org_id,),
    )
    assert row["value"] == "leads_generation"


def test_put_org_null_clears_override(clean_settings):
    client, headers, _, org_id = _client_with_user(is_admin=False, role="admin")
    execute(
        "INSERT INTO org_settings (org_id, key, value) VALUES (%s, 'default_mode_id', 'leads_generation')",
        (org_id,),
    )
    r = client.put(
        "/v3/settings/default_mode",
        headers=headers,
        json={"value": None, "scope": "org"},
    )
    assert r.status_code == 200
    row = fetch_one(
        "SELECT value FROM org_settings WHERE org_id = %s AND key = 'default_mode_id'",
        (org_id,),
    )
    assert row is None
