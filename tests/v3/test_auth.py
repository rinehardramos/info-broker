import os
import pytest
from fastapi.testclient import TestClient
from app.main import app

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_HOST"),
    reason="Requires Postgres"
)

client = TestClient(app)


def _register_user(username: str, password: str):
    """Helper: insert a test user directly via db."""
    from passlib.context import CryptContext
    from app.routers.v3.db import execute
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    execute(
        "INSERT INTO ui_users (username, password_hash) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (username, ctx.hash(password)),
    )


def test_login_returns_tokens():
    _register_user("testuser", "secret123")
    resp = client.post("/v3/auth/login", json={"username": "testuser", "password": "secret123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_wrong_password():
    _register_user("testuser2", "correct")
    resp = client.post("/v3/auth/login", json={"username": "testuser2", "password": "wrong"})
    assert resp.status_code == 401


def test_protected_route_without_token():
    resp = client.get("/v3/users/me")
    assert resp.status_code == 403


def test_protected_route_with_token():
    _register_user("testuser3", "pass123")
    login = client.post("/v3/auth/login", json={"username": "testuser3", "password": "pass123"})
    token = login.json()["access_token"]
    resp = client.get("/v3/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "testuser3"
