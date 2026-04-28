import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from tests.v3.test_auth import _register_user

pytestmark = pytest.mark.skipif(not os.getenv("POSTGRES_HOST"), reason="Requires Postgres")

client = TestClient(app)


def _auth_headers(username, password="pass"):
    _register_user(username, password)
    r = client.post("/v3/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_list_plugins():
    h = _auth_headers("plugintest1")
    r = client.get("/v3/plugins", headers=h)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_plugin_schema():
    h = _auth_headers("plugintest2")
    r = client.get("/v3/plugins/ddg/schema", headers=h)
    assert r.status_code == 200
    assert "type" in r.json()


def test_save_and_get_plugin_config():
    h = _auth_headers("plugintest3")
    r = client.put("/v3/plugins/ddg/config", json={"config": {"max_results": 10}}, headers=h)
    assert r.status_code == 200
    r2 = client.get("/v3/plugins/ddg/config", headers=h)
    assert r2.json()["config"]["max_results"] == 10
