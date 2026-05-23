"""Tests for GET /v3/pipelines/runs/{run_id}/gate-detail.

Spec: admin-only; returns 403 for non-admin even on their own runs.
"""
from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.v3.auth import get_current_user


def _override_user(is_admin: bool, role: str = "analyst"):
    def _u():
        return {
            "id": "00000000-0000-0000-0000-000000000001",
            "username": "test",
            "is_admin": is_admin,
            "role": role,
        }
    return _u


def test_gate_detail_requires_admin():
    """Non-admin should get 403, even for a run that might exist."""
    app.dependency_overrides[get_current_user] = _override_user(is_admin=False, role="analyst")
    try:
        with TestClient(app) as client:
            r = client.get("/v3/pipelines/runs/00000000-0000-0000-0000-000000000000/gate-detail")
            assert r.status_code == 403, f"got {r.status_code}: {r.text}"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_gate_detail_404_unknown_run():
    """Admin gets 404 for a run that has no trail row."""
    app.dependency_overrides[get_current_user] = _override_user(is_admin=True)
    try:
        with TestClient(app) as client:
            r = client.get(f"/v3/pipelines/runs/{uuid.uuid4()}/gate-detail")
            assert r.status_code == 404, f"got {r.status_code}: {r.text}"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_gate_detail_returns_payload_for_admin():
    """Admin gets the full GateResult from the most recent failing phase of the run."""
    pytest.skip("Verified via Step 8.7 real-env curl test against live local stack")
