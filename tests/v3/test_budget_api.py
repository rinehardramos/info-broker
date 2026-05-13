"""Budget API endpoint tests."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.routers.v3.auth import get_current_user

client = TestClient(app)

AUTH = {"Authorization": "Bearer test-token"}


def _mock_user():
    return {"id": "user-1", "org_id": "org-1", "role": "admin"}


def _override_user():
    return _mock_user()


@patch("app.routers.v3.budget.fetch_one", return_value=None)
def test_get_wallet_returns_default_when_no_wallet(mock_fetch):
    app.dependency_overrides[get_current_user] = _override_user
    try:
        resp = client.get("/v3/budget/wallet", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "balance_units" in data
    finally:
        app.dependency_overrides.clear()


def test_estimate_returns_cost_for_default_budget():
    app.dependency_overrides[get_current_user] = _override_user
    try:
        resp = client.post("/v3/budget/estimate", json={}, headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "estimated_cost_units" in data
        assert data["estimated_cost_units"] == pytest.approx(18.0)
    finally:
        app.dependency_overrides.clear()


def test_estimate_accepts_custom_budget():
    app.dependency_overrides[get_current_user] = _override_user
    try:
        resp = client.post(
            "/v3/budget/estimate",
            json={"resource": "heavy", "depth": "deep", "capability": "high"},
            headers=AUTH,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["estimated_cost_units"] > 18.0
    finally:
        app.dependency_overrides.clear()


@patch("app.routers.v3.budget.fetch_all", return_value=[])
def test_get_ledger_returns_empty_list(mock_fetch):
    app.dependency_overrides[get_current_user] = _override_user
    try:
        resp = client.get("/v3/budget/ledger", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        app.dependency_overrides.clear()
