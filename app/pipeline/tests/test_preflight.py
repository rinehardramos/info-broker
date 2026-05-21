"""Backend tests for MVP-M8 — preflight router + estimator."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Estimator unit tests (no DB, no app)
# ---------------------------------------------------------------------------

from app.pipeline.estimator import estimate_run
from app.pipeline.catalogs.budget import BudgetEnvelope


def _make_envelope(**kwargs) -> BudgetEnvelope:
    defaults = dict(capability="general", hypothesis_count="competing", depth="search",
                    speed="normal", resource="medium")
    defaults.update(kwargs)
    return BudgetEnvelope(**defaults)


def test_estimator_p90_is_strictly_greater_than_estimate():
    env = _make_envelope()
    result = estimate_run("media_identification", env)
    assert result.estimated_ru_p90 > result.estimated_ru, (
        f"p90={result.estimated_ru_p90} must be > estimate={result.estimated_ru}"
    )


def test_estimator_scales_with_hypothesis_count():
    env_competing = _make_envelope(hypothesis_count="competing")
    env_adversarial = _make_envelope(hypothesis_count="adversarial")
    r_c = estimate_run("media_identification", env_competing)
    r_a = estimate_run("media_identification", env_adversarial)
    assert r_a.estimated_ru > r_c.estimated_ru, (
        "adversarial should cost more RU than competing"
    )
    assert r_a.est_branches > r_c.est_branches


def test_estimator_scales_with_capability():
    env_light = _make_envelope(capability="light")
    env_high = _make_envelope(capability="high")
    r_l = estimate_run("media_identification", env_light)
    r_h = estimate_run("media_identification", env_high)
    assert r_h.estimated_ru > r_l.estimated_ru


# ---------------------------------------------------------------------------
# App-level tests — mock auth + wallet
# ---------------------------------------------------------------------------

_FAKE_USER = {"id": str(uuid.uuid4()), "username": "testuser", "is_admin": False}

_FAKE_WALLET_ROW = {"balance_ru": 200, "held_ru": 10}


def _wallet_row_side_effect(query, params):
    """Return a fake wallet row for wallet SELECT queries, None for others."""
    if "user_budget_wallets" in query:
        return _FAKE_WALLET_ROW
    return None


def _make_client():
    from app.main import app
    from app.routers.v3.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    from app.main import app
    app.dependency_overrides.clear()


@patch("app.routers.v3.preflight.fetch_one", side_effect=_wallet_row_side_effect)
def test_preflight_returns_estimate_with_envelope(mock_fetch):
    client = _make_client()
    resp = client.post("/v3/preflight", json={"query": "asian girl with curling iron ad"})
    assert resp.status_code == 200
    data = resp.json()
    assert "estimate" in data
    assert data["estimate"]["estimated_ru"] > 0
    assert data["estimate"]["estimated_ru_p90"] > data["estimate"]["estimated_ru"]
    assert "envelope" in data
    assert "wallet" in data


@patch("app.routers.v3.preflight.fetch_one", side_effect=_wallet_row_side_effect)
def test_preflight_classifier_returns_media_identification(mock_fetch):
    """A real media-id query must route to media_identification, not the
    generic fallback. Uses a phrase that hits the media_identification
    signal list (orchestrator._CATEGORY_SIGNALS)."""
    client = _make_client()
    resp = client.post(
        "/v3/preflight",
        json={"query": "what show is the girl in the new netflix series"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["suggested_strategy"] == "media_identification"
    assert data["classifier_output"] == "media_identification"


@patch("app.routers.v3.preflight.fetch_one", side_effect=_wallet_row_side_effect)
def test_preflight_enforces_strategy_budget_minimums(mock_fetch):
    """hypothesis_count='single' gets upgraded to 'competing' for
    media_identification (which sets a 'competing' floor in budget_minimums)."""
    client = _make_client()
    resp = client.post("/v3/preflight", json={
        "query": "what show is the girl in the new netflix series",
        "dials": {"hypothesis_count": "single", "capability": "general", "depth": "search"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["envelope"]["hypothesis_count"] == "competing"
    assert any("upgraded" in w for w in data["warnings"])


@patch("app.routers.v3.preflight.wallet")
@patch("app.routers.v3.preflight.fetch_one", side_effect=_wallet_row_side_effect)
def test_confirm_creates_hold_and_returns_hold_id(mock_fetch, mock_wallet):
    hold_id = str(uuid.uuid4())
    mock_wallet.hold.return_value = MagicMock(ok=True, hold_id=hold_id, held_ru=17)
    client = _make_client()
    resp = client.post("/v3/preflight/confirm", json={
        "query": "asian girl with mole",
        "envelope": {"capability": "general", "hypothesis_count": "competing", "depth": "search"},
        "strategy_id": "media_identification",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["hold_id"] == hold_id
    assert data["held_ru"] == 17
    assert "run_id" in data


@patch("app.routers.v3.preflight.wallet")
@patch("app.routers.v3.preflight.fetch_one", side_effect=_wallet_row_side_effect)
def test_confirm_rejects_when_insufficient(mock_fetch, mock_wallet):
    mock_wallet.hold.return_value = MagicMock(ok=False, hold_id=None, held_ru=0, reason="insufficient")
    client = _make_client()
    resp = client.post("/v3/preflight/confirm", json={
        "query": "who is this actress",
        "envelope": {"capability": "high", "hypothesis_count": "swarm", "depth": "abyss"},
        "strategy_id": "media_identification",
    })
    assert resp.status_code == 402
    detail = resp.json()["detail"]
    assert detail["error"] == "insufficient_ru"
