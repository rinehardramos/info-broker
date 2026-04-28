import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from tests.v3.test_auth import _register_user

pytestmark = pytest.mark.skipif(not os.getenv("POSTGRES_HOST"), reason="Requires Postgres")

client = TestClient(app)


def _auth_headers(username):
    _register_user(username, "pass")
    r = client.post("/v3/auth/login", json={"username": username, "password": "pass"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_set_and_get_non_secret_setting():
    h = _auth_headers("settingstest1")
    r = client.put("/v3/settings/core", json=[{"key": "llm.active_provider", "value": "gemini", "is_secret": False}], headers=h)
    assert r.status_code == 200
    r2 = client.get("/v3/settings/core", headers=h)
    assert r2.json()["settings"]["llm.active_provider"] == "gemini"


def test_secret_setting_masked_on_get():
    h = _auth_headers("settingstest2")
    client.put("/v3/settings/core", json=[{"key": "llm.openai.api_key", "value": "sk-test", "is_secret": True}], headers=h)
    r = client.get("/v3/settings/core", headers=h)
    assert r.json()["settings"]["llm.openai.api_key"] is None  # masked
