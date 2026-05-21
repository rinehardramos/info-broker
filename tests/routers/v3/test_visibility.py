"""Tests for mode/template visibility settings (#107)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_one


ADMIN = {
    "id": "00000000-0000-0000-0000-000000000001",
    "username": "admin",
    "is_admin": True,
    "role": "admin",
    "org_id": None,
}
NON_ADMIN = {
    "id": "00000000-0000-0000-0000-000000000002",
    "username": "user",
    "is_admin": False,
    "role": "analyst",
    "org_id": None,
}


@pytest.fixture
def clean_settings():
    keys = ('mode_visibility', 'template_visibility', 'default_mode_id')
    execute(f"DELETE FROM core_settings WHERE key = ANY(%s)", (list(keys),))
    yield
    execute(f"DELETE FROM core_settings WHERE key = ANY(%s)", (list(keys),))


def _as_user(u):
    app.dependency_overrides[get_current_user] = lambda: u


@pytest.fixture
def client():
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Visibility CRUD
# ---------------------------------------------------------------------------

def test_get_visibility_default_empty(client, clean_settings):
    _as_user(ADMIN)
    r = client.get('/v3/settings/mode_visibility')
    assert r.status_code == 200
    body = r.json()
    assert body['kind'] == 'mode'
    assert body['resolved'] == {}
    assert 'investigation' in body['known_ids']


def test_get_visibility_unknown_kind_404(client, clean_settings):
    _as_user(ADMIN)
    r = client.get('/v3/settings/bogus_visibility')
    assert r.status_code == 404


def test_put_global_visibility_persists(client, clean_settings):
    _as_user(ADMIN)
    r = client.put(
        '/v3/settings/mode_visibility',
        json={'scope': 'global', 'value': {'academic_research': False}},
    )
    assert r.status_code == 200
    assert r.json()['resolved'] == {'academic_research': False}

    # Round-trip
    r2 = client.get('/v3/settings/mode_visibility')
    assert r2.json()['resolved'] == {'academic_research': False}


def test_put_visibility_rejects_unknown_id(client, clean_settings):
    _as_user(ADMIN)
    r = client.put(
        '/v3/settings/mode_visibility',
        json={'scope': 'global', 'value': {'totally_made_up': False}},
    )
    assert r.status_code == 422


def test_put_visibility_non_admin_forbidden(client, clean_settings):
    _as_user(NON_ADMIN)
    r = client.put(
        '/v3/settings/mode_visibility',
        json={'scope': 'global', 'value': {}},
    )
    assert r.status_code == 403


def test_put_visibility_clears_with_null_value(client, clean_settings):
    _as_user(ADMIN)
    client.put('/v3/settings/mode_visibility',
               json={'scope': 'global', 'value': {'investigation': False}})
    r = client.put('/v3/settings/mode_visibility',
                   json={'scope': 'global', 'value': None})
    assert r.status_code == 200
    assert r.json()['resolved'] == {}
    assert fetch_one("SELECT value FROM core_settings WHERE key = 'mode_visibility'", ()) is None


# ---------------------------------------------------------------------------
# Filter behavior on consuming endpoints
# ---------------------------------------------------------------------------

def test_list_modes_admin_sees_all_even_when_hidden(client, clean_settings):
    _as_user(ADMIN)
    client.put('/v3/settings/mode_visibility',
               json={'scope': 'global', 'value': {'academic_research': False}})
    r = client.get('/v3/preflight/modes')
    ids = [m['id'] for m in r.json()]
    assert 'academic_research' in ids


def test_list_modes_non_admin_filtered(client, clean_settings):
    _as_user(ADMIN)
    client.put('/v3/settings/mode_visibility',
               json={'scope': 'global', 'value': {'academic_research': False}})
    _as_user(NON_ADMIN)
    r = client.get('/v3/preflight/modes')
    ids = [m['id'] for m in r.json()]
    assert 'academic_research' not in ids
    assert 'investigation' in ids  # not hidden


def test_list_investigation_templates_non_admin_filtered(client, clean_settings):
    _as_user(ADMIN)
    client.put('/v3/settings/template_visibility',
               json={'scope': 'global', 'value': {'kyc-individual': False}})
    _as_user(NON_ADMIN)
    r = client.get('/v3/investigation-templates')
    ids = [t['id'] for t in r.json()]
    assert 'kyc-individual' not in ids


# ---------------------------------------------------------------------------
# Default-mode interaction
# ---------------------------------------------------------------------------

def test_set_default_mode_rejects_hidden(client, clean_settings):
    _as_user(ADMIN)
    client.put('/v3/settings/mode_visibility',
               json={'scope': 'global', 'value': {'academic_research': False}})
    r = client.put('/v3/settings/default_mode',
                   json={'scope': 'global', 'value': 'academic_research'})
    assert r.status_code == 422


def test_set_default_mode_accepts_visible(client, clean_settings):
    _as_user(ADMIN)
    client.put('/v3/settings/mode_visibility',
               json={'scope': 'global', 'value': {'academic_research': False}})
    r = client.put('/v3/settings/default_mode',
                   json={'scope': 'global', 'value': 'investigation'})
    assert r.status_code == 200
