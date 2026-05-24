import os
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app

pytestmark = pytest.mark.skipif(not os.getenv("POSTGRES_HOST"), reason="Requires Postgres")

client = TestClient(app)


def _register_admin(username: str, password: str) -> None:
    """Insert a test user with is_admin=True via direct DB access."""
    import uuid as _uuid
    from passlib.context import CryptContext
    from app.routers.v3.db import execute
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    org_id = str(_uuid.uuid4())
    execute(
        "INSERT INTO ui_users (username, password_hash, is_admin, org_id) VALUES (%s, %s, true, %s) "
        "ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash, is_admin = true",
        (username, ctx.hash(password), org_id),
    )


def _auth_headers(username):
    _register_admin(username, "pass")
    r = client.post("/v3/auth/login", json={"username": username, "password": "pass"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_set_and_get_non_secret_setting():
    h = _auth_headers(f"settingstest1_{uuid.uuid4().hex[:8]}")
    r = client.put("/v3/settings/core", json=[{"key": "llm.active_provider", "value": "gemini", "is_secret": False}], headers=h)
    assert r.status_code == 200
    r2 = client.get("/v3/settings/core", headers=h)
    assert r2.json()["settings"]["llm.active_provider"] == "gemini"


def test_secret_setting_masked_on_get():
    h = _auth_headers(f"settingstest2_{uuid.uuid4().hex[:8]}")
    client.put("/v3/settings/core", json=[{"key": "llm.openai.api_key", "value": "sk-test", "is_secret": True}], headers=h)
    r = client.get("/v3/settings/core", headers=h)
    assert r.json()["settings"]["llm.openai.api_key"] is None  # masked
