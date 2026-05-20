"""Tests for /v3/auth/set-password, /v3/users/me (GET + PATCH).

Email verification endpoints are gated behind EMAIL_VERIFY_ENABLED and
not user-facing today; their 404 behavior is covered by one test.
"""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.v3.db import execute, fetch_one

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_HOST"),
    reason="Requires Postgres",
)

client = TestClient(app)


def _make_user(username: str, *, password: str | None = "secretpass123", email: str | None = None) -> str:
    from passlib.context import CryptContext
    ctx = CryptContext(schemes=["argon2", "bcrypt"], deprecated=["bcrypt"])
    pwd_hash = ctx.hash(password) if password else None
    execute(
        """INSERT INTO ui_users (username, password_hash, email, is_active)
           VALUES (%s, %s, %s, true)
           ON CONFLICT (username) DO UPDATE
              SET password_hash = EXCLUDED.password_hash,
                  email = EXCLUDED.email""",
        (username, pwd_hash, email),
    )
    row = fetch_one("SELECT id FROM ui_users WHERE username = %s", (username,))
    return str(row["id"])


def _login(username: str, password: str) -> str:
    resp = client.post("/v3/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# ---------- /set-password ----------

def test_set_password_blocked_for_users_with_existing_hash():
    _make_user("sp_has_pwd", password="oldpassword12!")
    token = _login("sp_has_pwd", "oldpassword12!")
    resp = client.post(
        "/v3/auth/set-password",
        json={"new_password": "brandnewpw99!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "already" in resp.json()["detail"].lower()


def test_set_password_works_for_oauth_only_user():
    from app.routers.v3.auth import _make_access_token
    uid = _make_user("sp_oauth_only", password=None, email="sp_oauth@example.com")
    execute("UPDATE ui_users SET password_hash = NULL WHERE id = %s", (uid,))
    token = _make_access_token(uid)
    resp = client.post(
        "/v3/auth/set-password",
        json={"new_password": "freshpassword42!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    row = fetch_one("SELECT password_hash FROM ui_users WHERE id = %s", (uid,))
    assert row["password_hash"] is not None
    me = client.get("/v3/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["password_set"] is True


# ---------- /v3/users/me ----------

def test_me_returns_extended_fields():
    uid = _make_user("me_fields", email="me_fields@example.com")
    token = _login("me_fields", "secretpass123")
    resp = client.get("/v3/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["password_set"] is True
    for k in ("display_name", "timezone", "locale", "avatar_url"):
        assert k in body


def test_patch_me_updates_personalization():
    _make_user("pp_user", email="pp@example.com")
    token = _login("pp_user", "secretpass123")
    resp = client.patch(
        "/v3/users/me",
        json={
            "display_name": "  Patrick  ",
            "avatar_url":   "https://example.com/pp.png",
            "timezone":     "America/Los_Angeles",
            "locale":       "en-US",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["display_name"] == "Patrick"
    assert body["avatar_url"]   == "https://example.com/pp.png"
    assert body["timezone"]     == "America/Los_Angeles"
    assert body["locale"]       == "en-US"


def test_patch_me_partial_update_does_not_clear_other_fields():
    uid = _make_user("pp_partial", email="ppp@example.com")
    token = _login("pp_partial", "secretpass123")
    client.patch("/v3/users/me", json={"display_name": "Alice"}, headers={"Authorization": f"Bearer {token}"})
    client.patch("/v3/users/me", json={"locale": "fr"}, headers={"Authorization": f"Bearer {token}"})
    me = client.get("/v3/users/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["display_name"] == "Alice"
    assert me["locale"] == "fr"


# ---------- email-verify endpoints are gated off ----------

def test_email_verify_send_returns_404_when_disabled(monkeypatch):
    monkeypatch.delenv("EMAIL_VERIFY_ENABLED", raising=False)
    _make_user("ev_disabled", email="disabled@example.com")
    token = _login("ev_disabled", "secretpass123")
    resp = client.post("/v3/auth/me/email/send", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_email_verify_confirm_returns_404_when_disabled(monkeypatch):
    monkeypatch.delenv("EMAIL_VERIFY_ENABLED", raising=False)
    resp = client.post("/v3/auth/me/email/confirm", json={"token": "anything"})
    assert resp.status_code == 404
