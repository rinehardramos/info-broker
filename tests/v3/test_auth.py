import os
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_HOST"),
    reason="Requires Postgres"
)

client = TestClient(app)


def _register_user(username: str, password: str):
    """Helper: insert a test user directly via db.

    Uses ON CONFLICT DO UPDATE so a re-registration with a different password
    always refreshes the hash instead of silently keeping a stale one.  This
    prevents KeyError: 'access_token' when the same username is reused across
    test runs with a different password.

    A random org_id is assigned so that org-scoped queries (e.g. list_pipelines)
    work correctly for users created by this helper.
    """
    import uuid as _uuid
    from passlib.context import CryptContext
    from app.routers.v3.db import execute
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    org_id = str(_uuid.uuid4())
    execute(
        "INSERT INTO ui_users (username, password_hash, org_id) VALUES (%s, %s, %s) "
        "ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash",
        (username, ctx.hash(password), org_id),
    )


def _unique_user(prefix: str = "u") -> str:
    """Return a username that is unique per test invocation."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def test_login_returns_tokens():
    username = _unique_user("testuser")
    _register_user(username, "secret123")
    resp = client.post("/v3/auth/login", json={"username": username, "password": "secret123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_wrong_password():
    username = _unique_user("testuser2")
    _register_user(username, "correct")
    resp = client.post("/v3/auth/login", json={"username": username, "password": "wrong"})
    assert resp.status_code == 401


def test_protected_route_without_token():
    resp = client.get("/v3/users/me")
    # Endpoint returns 401 when no token present; some configs return 403.
    assert resp.status_code in (401, 403)


def test_protected_route_with_token():
    username = _unique_user("testuser3")
    _register_user(username, "pass123")
    login = client.post("/v3/auth/login", json={"username": username, "password": "pass123"})
    token = login.json()["access_token"]
    resp = client.get("/v3/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == username
