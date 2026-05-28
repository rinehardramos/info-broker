"""TDD tests for /v3/admin/llm-pricing CRUD endpoints.

All tests use FastAPI TestClient with require_admin overridden to bypass auth.
Postgres on :5433 (POSTGRES_PORT env var).
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock, patch

import psycopg2
import psycopg2.extras
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

_PG_DSN = (
    f"dbname={os.getenv('POSTGRES_DB', 'info_broker')} "
    f"user={os.getenv('POSTGRES_USER', 'user')} "
    f"password={os.getenv('POSTGRES_PASSWORD', 'password')} "
    f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
    f"port={os.getenv('POSTGRES_PORT', '5433')}"
)


def _pg_conn():
    database_url = os.getenv("DATABASE_URL")
    conn = psycopg2.connect(database_url) if database_url else psycopg2.connect(_PG_DSN)
    conn.autocommit = True
    return conn


def _insert_pricing_row(
    conn,
    model_id: str,
    *,
    provider: str = "anthropic",
    input_usd: float = 3.0,
    output_usd: float = 15.0,
    pricing_id: str | None = None,
    effective_from: str | None = None,
) -> str:
    pid = pricing_id or str(uuid.uuid4())
    cur = conn.cursor()
    if effective_from:
        cur.execute(
            "INSERT INTO llm_pricing "
            "(id, model_id, provider, input_usd_per_1m, output_usd_per_1m, effective_from) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (pid, model_id, provider, input_usd, output_usd, effective_from),
        )
    else:
        cur.execute(
            "INSERT INTO llm_pricing "
            "(id, model_id, provider, input_usd_per_1m, output_usd_per_1m) "
            "VALUES (%s, %s, %s, %s, %s)",
            (pid, model_id, provider, input_usd, output_usd),
        )
    cur.close()
    return pid


def _delete_pricing_rows(conn, model_id: str) -> None:
    cur = conn.cursor()
    cur.execute("DELETE FROM llm_pricing WHERE model_id = %s", (model_id,))
    cur.close()


# ---------------------------------------------------------------------------
# App + auth override fixtures
# ---------------------------------------------------------------------------

_FAKE_ADMIN = {"id": "admin-test-1", "username": "admin", "is_admin": True, "is_active": True}


def _admin_override():
    return _FAKE_ADMIN


@pytest.fixture()
def client():
    """TestClient with require_admin bypassed."""
    from app.main import app
    from app.routers.v3.auth import require_admin

    app.dependency_overrides[require_admin] = _admin_override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(require_admin, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_pricing_empty(client):
    """GET /v3/admin/llm-pricing returns 200 with a list (may be empty)."""
    resp = client.get("/v3/admin/llm-pricing")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list)


def test_create_and_list_pricing(client):
    """POST a row then GET / returns that model in the list."""
    model_id = f"test-model-{uuid.uuid4().hex[:8]}"
    payload = {
        "model_id": model_id,
        "provider": "anthropic",
        "input_usd_per_1m": 3.0,
        "output_usd_per_1m": 15.0,
    }

    conn = _pg_conn()
    try:
        create_resp = client.post("/v3/admin/llm-pricing", json=payload)
        assert create_resp.status_code == 201, create_resp.text
        created = create_resp.json()
        assert created["model_id"] == model_id
        assert "id" in created

        list_resp = client.get("/v3/admin/llm-pricing")
        assert list_resp.status_code == 200
        model_ids = [r["model_id"] for r in list_resp.json()]
        assert model_id in model_ids
    finally:
        _delete_pricing_rows(conn, model_id)
        conn.close()


def test_get_pricing_history(client):
    """GET /v3/admin/llm-pricing/history?model_id=X returns all rows for model, newest first."""
    model_id = f"test-history-{uuid.uuid4().hex[:8]}"
    conn = _pg_conn()
    try:
        pid1 = _insert_pricing_row(
            conn, model_id, input_usd=1.0, effective_from="2024-01-01T00:00:00Z"
        )
        pid2 = _insert_pricing_row(
            conn, model_id, input_usd=2.0, effective_from="2025-01-01T00:00:00Z"
        )

        resp = client.get(f"/v3/admin/llm-pricing/history?model_id={model_id}")
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert len(rows) == 2
        returned_ids = [r["id"] for r in rows]
        assert pid1 in returned_ids
        assert pid2 in returned_ids
        # newest first: pid2 has effective_from 2025, pid1 has 2024
        assert rows[0]["id"] == pid2
    finally:
        _delete_pricing_rows(conn, model_id)
        conn.close()


def test_delete_pricing_row(client):
    """DELETE /{id} → 200, row gone from DB."""
    model_id = f"test-delete-{uuid.uuid4().hex[:8]}"
    conn = _pg_conn()
    try:
        pid = _insert_pricing_row(conn, model_id)

        del_resp = client.delete(f"/v3/admin/llm-pricing/{pid}")
        assert del_resp.status_code == 200, del_resp.text

        # Verify row is gone
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id FROM llm_pricing WHERE id = %s", (pid,))
        row = cur.fetchone()
        cur.close()
        assert row is None
    finally:
        _delete_pricing_rows(conn, model_id)
        conn.close()


def test_create_pricing_invalidates_cache(client):
    """POST /v3/admin/llm-pricing should call resolver.invalidate(model_id)."""
    import app.observability.pricing_ref as _pricing_ref

    model_id = f"test-invalidate-{uuid.uuid4().hex[:8]}"
    payload = {
        "model_id": model_id,
        "provider": "anthropic",
        "input_usd_per_1m": 5.0,
        "output_usd_per_1m": 25.0,
    }

    mock_resolver = MagicMock()
    original_resolver = _pricing_ref._resolver
    _pricing_ref._resolver = mock_resolver

    conn = _pg_conn()
    try:
        resp = client.post("/v3/admin/llm-pricing", json=payload)
        assert resp.status_code == 201, resp.text

        mock_resolver.invalidate.assert_called_once_with(model_id)
    finally:
        _pricing_ref._resolver = original_resolver
        _delete_pricing_rows(conn, model_id)
        conn.close()
