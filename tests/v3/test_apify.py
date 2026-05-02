import os
import pytest
from fastapi.testclient import TestClient
from app.main import app

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_HOST"),
    reason="Requires Postgres"
)

client = TestClient(app)


def _register_and_login(username: str, pw: str) -> str:
    from passlib.context import CryptContext
    from app.routers.v3.db import execute
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    execute(
        "INSERT INTO ui_users (username, password_hash) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (username, ctx.hash(pw)),
    )
    creds = {"username": username, "password": pw}
    resp = client.post("/v3/auth/login", json=creds)
    return resp.json()["access_token"]


def test_apify_tables_exist():
    from app.routers.v3.db import fetch_one
    r1 = fetch_one(
        "SELECT table_name FROM information_schema.tables WHERE table_name = 'apify_run_configs'"
    )
    assert r1 is not None, "apify_run_configs table missing"
    r2 = fetch_one(
        "SELECT table_name FROM information_schema.tables WHERE table_name = 'apify_runs'"
    )
    assert r2 is not None, "apify_runs table missing"


_MASKED = "\u2022" * 8


def test_get_config_empty():
    from app.routers.v3.db import execute as _exec
    _exec("DELETE FROM core_settings WHERE key IN ('apify_api_key', 'apify_actor_id')")
    token = _register_and_login("apify_cfg", "pass")
    resp = client.get("/v3/apify/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["api_key"] is None
    assert data["actor_id"] is None
    assert data["run_config"]["job_titles"] == []
    assert data["run_config"]["max_items"] == 300


def test_save_config_masks_api_key():
    token = _register_and_login("apify_save", "pass")
    body = {
        "api_key": "real-secret-key",
        "actor_id": "myactor~id",
        "job_titles": ["CEO", "CTO"],
        "locations": ["United States"],
        "max_items": 150,
        "scraper_mode": "Full",
    }
    resp = client.post("/v3/apify/config", json=body, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["api_key"] == _MASKED
    assert data["actor_id"] == "myactor~id"
    assert data["run_config"]["job_titles"] == ["CEO", "CTO"]
    assert data["run_config"]["max_items"] == 150


def test_start_run_missing_credentials():
    # Ensure no global apify credentials exist for this assertion
    from app.routers.v3.db import execute as _exec
    _exec("DELETE FROM core_settings WHERE key IN ('apify_api_key', 'apify_actor_id')")
    token = _register_and_login("apify_nokey", "pass")
    resp = client.post(
        "/v3/apify/run",
        json={"job_titles": ["CEO"], "locations": ["US"], "max_items": 10, "scraper_mode": "Full"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "must be configured" in resp.json()["detail"]


def test_start_run_calls_apify():
    from unittest.mock import MagicMock, patch

    token = _register_and_login("apify_run", "pass")
    client.post(
        "/v3/apify/config",
        json={"api_key": "mykey", "actor_id": "myactor"},
        headers={"Authorization": f"Bearer {token}"},
    )
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"id": "apify-run-abc123"}}
    mock_resp.raise_for_status = MagicMock()

    with patch("app.routers.v3.apify.requests.post", return_value=mock_resp):
        resp = client.post(
            "/v3/apify/run",
            json={"job_titles": ["CEO"], "locations": ["United States"], "max_items": 50, "scraper_mode": "Full"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 202
    data = resp.json()
    assert data["apify_run_id"] == "apify-run-abc123"
    assert data["status"] == "queued"


def test_list_runs_empty():
    token = _register_and_login("apify_list", "pass")
    resp = client.get("/v3/apify/runs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_run_status_not_found():
    token = _register_and_login("apify_404", "pass")
    resp = client.get(
        "/v3/apify/runs/00000000-0000-0000-0000-000000000000/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_apify_map_item_harvestapi_shape():
    from app.pipeline.nodes.apify_actor import ApifyActorNode
    node = ApifyActorNode()
    item = {
        "profileUrl": "https://linkedin.com/in/johndoe",
        "firstName": "John",
        "lastName": "Doe",
        "fullName": "John Doe",
        "headline": "CEO at Acme",
        "location": "New York",
        "summary": "Experienced executive",
        "currentPosition": [{"companyName": "Acme", "title": "CEO"}],
    }
    result = node._map_item(item)
    assert result["id"] == "https://linkedin.com/in/johndoe"
    assert result["full_name"] == "John Doe"
    assert result["company"] == "Acme"
    assert result["title"] == "CEO"
    assert result["source"] == "apify"


def test_get_run_status_polls_apify():
    from unittest.mock import MagicMock, patch

    token = _register_and_login("apify_poll", "pass")
    client.post(
        "/v3/apify/config",
        json={"api_key": "k", "actor_id": "a"},
        headers={"Authorization": f"Bearer {token}"},
    )
    start_mock = MagicMock()
    start_mock.json.return_value = {"data": {"id": "run-xyz"}}
    start_mock.raise_for_status = MagicMock()
    with patch("app.routers.v3.apify.requests.post", return_value=start_mock):
        run_resp = client.post(
            "/v3/apify/run",
            json={"job_titles": ["CEO"], "locations": ["US"], "max_items": 5, "scraper_mode": "Full"},
            headers={"Authorization": f"Bearer {token}"},
        )
    run_id = run_resp.json()["id"]

    poll_mock = MagicMock()
    poll_mock.json.return_value = {"data": {"status": "RUNNING", "defaultDatasetId": None}}
    poll_mock.raise_for_status = MagicMock()
    with patch("app.routers.v3.apify.requests.get", return_value=poll_mock):
        status_resp = client.get(
            f"/v3/apify/runs/{run_id}/status",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "running"
