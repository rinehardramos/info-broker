"""Tests for the pre-run admission gate (D1)."""
import importlib
import os
from unittest.mock import patch

import pytest

# GATE_* env keys these tests mutate via _set_gate(). The autouse fixture below
# snapshots + restores them (and reloads the module) so an enabled-gate config
# doesn't bleed into later tests in the full suite — previously this left
# GATE_ENABLED="true" set, causing /v3/agent/message tests to 429 (see #130).
_GATE_ENV_KEYS = (
    "GATE_GLOBAL_MAX_CONCURRENT",
    "GATE_PER_USER_MAX_CONCURRENT",
    "GATE_DAILY_RUN_CAP",
    "GATE_ENABLED",
    "GATE_BYPASS_USER_IDS",
)


@pytest.fixture(autouse=True)
def _restore_gate_env():
    saved = {k: os.environ.get(k) for k in _GATE_ENV_KEYS}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    # Reload so the module-level GATE_ENABLED reflects the restored (bypassed) env.
    from app.services import admission_gate
    importlib.reload(admission_gate)


def _set_gate(global_max=2, per_user=1, daily=30, enabled=True, bypass=""):
    os.environ["GATE_GLOBAL_MAX_CONCURRENT"] = str(global_max)
    os.environ["GATE_PER_USER_MAX_CONCURRENT"] = str(per_user)
    os.environ["GATE_DAILY_RUN_CAP"] = str(daily)
    os.environ["GATE_ENABLED"] = "true" if enabled else "false"
    os.environ["GATE_BYPASS_USER_IDS"] = bypass
    # Re-import to pick up new env values
    import importlib
    from app.services import admission_gate
    importlib.reload(admission_gate)
    return admission_gate


def _fake_counts(global_active, user_active, user_runs_today):
    return {
        "global_active": global_active,
        "user_active": user_active,
        "user_runs_today": user_runs_today,
    }


def test_admits_when_under_all_limits():
    g = _set_gate()
    with patch.object(g, "_count_active_and_recent", return_value=_fake_counts(0, 0, 0)):
        decision = g.check_admission("user-A")
    assert decision.admitted is True
    assert decision.reason is None


def test_rejects_on_global_concurrency():
    g = _set_gate(global_max=2)
    with patch.object(g, "_count_active_and_recent", return_value=_fake_counts(2, 0, 0)):
        decision = g.check_admission("user-A")
    assert decision.admitted is False
    assert decision.reason == "global_concurrency_exhausted"
    assert decision.retry_after_seconds >= 30


def test_rejects_on_per_user_concurrency():
    g = _set_gate(global_max=10, per_user=1)
    with patch.object(g, "_count_active_and_recent", return_value=_fake_counts(1, 1, 0)):
        decision = g.check_admission("user-A")
    assert decision.admitted is False
    assert decision.reason == "per_user_concurrency_exhausted"


def test_rejects_on_daily_cap():
    g = _set_gate(global_max=10, per_user=5, daily=30)
    with patch.object(g, "_count_active_and_recent", return_value=_fake_counts(0, 0, 30)):
        decision = g.check_admission("user-A")
    assert decision.admitted is False
    assert decision.reason == "daily_cap_exhausted"
    assert decision.retry_after_seconds == 3600


def test_global_check_runs_before_per_user():
    """If both limits are exceeded, global wins (more honest message)."""
    g = _set_gate(global_max=2, per_user=1)
    with patch.object(g, "_count_active_and_recent", return_value=_fake_counts(2, 1, 0)):
        decision = g.check_admission("user-A")
    assert decision.reason == "global_concurrency_exhausted"


def test_disabled_gate_always_admits():
    g = _set_gate(enabled=False)
    with patch.object(g, "_count_active_and_recent", return_value=_fake_counts(100, 100, 100)):
        decision = g.check_admission("user-A")
    assert decision.admitted is True


def test_bypass_user_id_always_admits():
    g = _set_gate(bypass="admin-uuid")
    with patch.object(g, "_count_active_and_recent", return_value=_fake_counts(100, 100, 100)):
        decision = g.check_admission("admin-uuid")
        assert decision.admitted is True
        decision2 = g.check_admission("regular-user")
        assert decision2.admitted is False
        assert decision2.reason == "global_concurrency_exhausted"


def test_db_failure_fails_open():
    """If the count query raises, the gate admits (safer than blocking)."""
    g = _set_gate()
    with patch.object(g, "fetch_one", side_effect=RuntimeError("db down")):
        decision = g.check_admission("user-A")
    assert decision.admitted is True


def test_gate_stats_reports_config():
    g = _set_gate(global_max=3, per_user=1, daily=50)
    stats = g.gate_stats()
    assert stats["enabled"] is True
    assert stats["limits"]["global_max_concurrent"] == 3
    assert stats["limits"]["per_user_max_concurrent"] == 1
    assert stats["limits"]["daily_run_cap"] == 50
