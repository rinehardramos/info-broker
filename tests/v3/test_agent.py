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


def test_agent_message_returns_job_id():
    h = _auth_headers("agenttest1")
    r = client.post("/v3/agent/message", json={"message": "find CTOs in Manila"}, headers=h)
    assert r.status_code == 202
    data = r.json()
    assert "job_id" in data
    assert data["status"] == "pending"


def test_get_job_after_message():
    h = _auth_headers("agenttest2")
    r = client.post("/v3/agent/message", json={"message": "find news about fintech"}, headers=h)
    job_id = r.json()["job_id"]
    r2 = client.get(f"/v3/jobs/{job_id}", headers=h)
    assert r2.status_code == 200
    assert r2.json()["id"] == job_id


def test_list_jobs():
    h = _auth_headers("agenttest3")
    client.post("/v3/agent/message", json={"message": "test query"}, headers=h)
    r = client.get("/v3/jobs", headers=h)
    assert r.status_code == 200
    assert len(r.json()) >= 1
