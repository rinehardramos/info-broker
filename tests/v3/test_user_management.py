"""Tests for admin user management endpoints (no Postgres required)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.v3.auth import get_current_user, require_admin


def _admin():
    return {"id": "admin-1", "is_admin": True, "is_active": True}


def _non_admin():
    return {"id": "user-1", "is_admin": False, "is_active": True}


def test_list_users_requires_admin():
    """Non-admin should get 403 when listing users."""
    from fastapi import HTTPException

    def raise_403():
        raise HTTPException(status_code=403, detail="Admin required")

    app.dependency_overrides[get_current_user] = _non_admin
    app.dependency_overrides[require_admin] = raise_403
    try:
        client = TestClient(app)
        resp = client.get("/v3/auth/users")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(require_admin, None)


def test_cannot_self_demote():
    """Admin cannot remove their own admin status."""
    from unittest.mock import patch

    app.dependency_overrides[get_current_user] = _admin
    app.dependency_overrides[require_admin] = _admin
    user_id = "admin-1"
    url = "/v3/auth/users/" + user_id
    try:
        with patch("app.routers.v3.auth.fetch_one", return_value=None):
            client = TestClient(app)
            resp = client.patch(url, json={"is_admin": False})
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(require_admin, None)
