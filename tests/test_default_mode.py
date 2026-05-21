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
    assert get_default_mode_id(None) == "general"
    assert get_default_mode_id(str(uuid.uuid4())) == "general"


def test_resolution_uses_global(clean_settings):
    execute(
        "INSERT INTO core_settings (key, value, is_secret) VALUES ('default_mode_id', 'kyc_edd', false)",
        (),
    )
    assert get_default_mode_id(None) == "kyc_edd"
    assert get_default_mode_id(str(uuid.uuid4())) == "kyc_edd"


def test_org_overrides_global(clean_settings):
    org_id = str(uuid.uuid4())
    execute(
        "INSERT INTO core_settings (key, value, is_secret) VALUES ('default_mode_id', 'general', false)",
        (),
    )
    execute(
        "INSERT INTO org_settings (org_id, key, value) VALUES (%s, 'default_mode_id', 'lead_gen')",
        (org_id,),
    )
    assert get_default_mode_id(org_id) == "lead_gen"


def test_invalid_org_value_falls_through_to_global(clean_settings):
    org_id = str(uuid.uuid4())
    execute(
        "INSERT INTO core_settings (key, value, is_secret) VALUES ('default_mode_id', 'lead_gen', false)",
        (),
    )
    execute(
        "INSERT INTO org_settings (org_id, key, value) VALUES (%s, 'default_mode_id', 'bogus_id')",
        (org_id,),
    )
    assert get_default_mode_id(org_id) == "lead_gen"


def test_invalid_global_value_falls_through_to_general(clean_settings):
    execute(
        "INSERT INTO core_settings (key, value, is_secret) VALUES ('default_mode_id', 'bogus_id', false)",
        (),
    )
    assert get_default_mode_id(None) == "general"
