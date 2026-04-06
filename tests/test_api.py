"""FastAPI TestClient tests for the info-broker REST API.

These tests stub out psycopg2 and qdrant_client at import time so the
app can be exercised without a live database. Real DB integration is
covered by the existing top-level tests, which mock at a finer grain.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

# Stub heavy/external imports BEFORE importing the app, so that even
# `from app.deps import get_db_conn` doesn't try to talk to real services.
sys.modules.setdefault("qdrant_client", MagicMock())
sys.modules.setdefault("qdrant_client.models", MagicMock())

os.environ.setdefault("INFO_BROKER_API_KEY", "test-secret-key")
os.environ.setdefault("POSTGRES_DB", "info_broker")
os.environ.setdefault("POSTGRES_USER", "user")
os.environ.setdefault("POSTGRES_PASSWORD", "password")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6333")

from fastapi.testclient import TestClient  # noqa: E402

from app.deps import get_db_conn  # noqa: E402
from app.main import app  # noqa: E402

API_KEY = "test-secret-key"


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.last_sql = None
        self.last_params = None

    def execute(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConn:
    def __init__(self, rows):
        self._cursor = FakeCursor(rows)

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def close(self):
        pass


def override_db(rows):
    def _gen():
        yield FakeConn(rows)
    return _gen


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


client = TestClient(app)


def test_healthz_no_auth_required():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_profiles_requires_api_key():
    r = client.get("/profiles")
    assert r.status_code == 401


def test_profiles_wrong_api_key():
    r = client.get("/profiles", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_profiles_correct_key_returns_list():
    rows = [
        ("id-1", "Ada", "Lovelace", "Mathematician"),
        ("id-2", "Alan", "Turing", "Computer Scientist"),
    ]
    app.dependency_overrides[get_db_conn] = override_db(rows)
    r = client.get("/profiles", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["id"] == "id-1"
    assert body[0]["first_name"] == "Ada"


def test_profile_detail_404_when_missing():
    app.dependency_overrides[get_db_conn] = override_db([])
    r = client.get("/profiles/nope", headers={"X-API-Key": API_KEY})
    assert r.status_code == 404


def test_profile_detail_200():
    rows = [(
        "id-1", "Ada", "Lovelace", "Mathematician", "Notes on the engine.",
        "completed", True, "Summary text", 8, 5,
    )]
    app.dependency_overrides[get_db_conn] = override_db(rows)
    r = client.get("/profiles/id-1", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "id-1"
    assert body["research_status"] == "completed"
    assert body["system_confidence_score"] == 8


def test_profile_raw_200():
    rows = [("id-1", {"about": "stuff"})]
    app.dependency_overrides[get_db_conn] = override_db(rows)
    r = client.get("/profiles/id-1/raw", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert r.json()["raw_data"] == {"about": "stuff"}


def test_ingest_requires_auth():
    r = client.post("/ingest", json={"overwrite": False})
    assert r.status_code == 401


def test_ingest_calls_ingest_data(monkeypatch):
    called = {}

    def fake_ingest_data(overwrite=False):
        called["overwrite"] = overwrite
        return {"fetched": 3, "inserted": 2, "skipped": 1, "errors": 0}

    import ingest as ingest_mod
    monkeypatch.setattr(ingest_mod, "ingest_data", fake_ingest_data)

    r = client.post(
        "/ingest",
        json={"overwrite": True},
        headers={"X-API-Key": API_KEY},
    )
    assert r.status_code == 200
    assert called["overwrite"] is True
    assert r.json()["inserted"] == 2


def test_research_calls_run_research_batch(monkeypatch):
    def fake_run(limit=5):
        return {"processed": limit, "succeeded": limit, "failed": 0}

    import research_agent as ra
    monkeypatch.setattr(ra, "run_research_batch", fake_run)

    r = client.post(
        "/research",
        json={"limit": 4},
        headers={"X-API-Key": API_KEY},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["processed"] == 4
    assert body["succeeded"] == 4


def test_grade_calls_save_grade(monkeypatch):
    def fake_save(profile_id, grade, feedback):
        return {"profile_id": profile_id, "grade": grade, "saved": True}

    import research_agent as ra
    monkeypatch.setattr(ra, "save_grade", fake_save)

    r = client.post(
        "/profiles/id-1/grade",
        json={"grade": 4, "feedback": "ok"},
        headers={"X-API-Key": API_KEY},
    )
    assert r.status_code == 200
    assert r.json()["grade"] == 4


def test_grade_validation_error():
    r = client.post(
        "/profiles/id-1/grade",
        json={"grade": 99},
        headers={"X-API-Key": API_KEY},
    )
    assert r.status_code == 422


def test_search_requires_auth():
    r = client.post("/search", json={"query": "x"})
    assert r.status_code == 401
