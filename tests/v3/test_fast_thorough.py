"""Tests for fast+thorough settings gate."""
from unittest.mock import patch
from app.routers.v3.agent import _fast_thorough_enabled


def test_enabled_by_default_when_no_db_row():
    with patch("app.routers.v3.agent.fetch_one", return_value=None):
        assert _fast_thorough_enabled() is True


def test_disabled_when_setting_false():
    with patch("app.routers.v3.agent.fetch_one", return_value={"value": "false"}):
        assert _fast_thorough_enabled() is False


def test_enabled_when_set_true():
    with patch("app.routers.v3.agent.fetch_one", return_value={"value": "true"}):
        assert _fast_thorough_enabled() is True


def test_enabled_when_db_raises():
    with patch("app.routers.v3.agent.fetch_one", side_effect=Exception("DB down")):
        assert _fast_thorough_enabled() is True
