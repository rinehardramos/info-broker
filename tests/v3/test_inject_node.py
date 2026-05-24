"""Tests for POST /v3/runs/{run_id}/inject (inject_node endpoint).

Covers:
- 403 when run belongs to a different user
- 404 when run does not exist
- Successful injection enqueues the instruction
- Appends to conversation_thread when session_id is present
- Works when session_id is NULL (no DB error)
"""
from __future__ import annotations

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.v3.test_auth import _register_user

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_HOST"),
    reason="Requires Postgres",
)

client = TestClient(app)

SYSTEM_PIPELINE_ID = "00000000-0000-4000-8000-000000000001"


def _auth_headers(username: str) -> dict:
    _register_user(username, "pass")
    r = client.post("/v3/auth/login", json={"username": username, "password": "pass"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _get_user_id(username: str) -> str:
    from app.routers.v3.db import fetch_one
    row = fetch_one("SELECT id FROM ui_users WHERE username = %s", (username,))
    assert row is not None
    return str(row["id"])


def _seed_run(user_id: str, session_id: str | None = None) -> str:
    """Insert a pipeline_run row and return its id."""
    from app.routers.v3.db import execute
    run_id = str(uuid.uuid4())
    execute(
        """
        INSERT INTO pipeline_runs
            (id, pipeline_id, user_id, status, trigger_type, query)
        VALUES (%s, %s, %s, 'running', 'agent_is', 'test query')
        """,
        (run_id, SYSTEM_PIPELINE_ID, user_id),
    )
    if session_id is not None:
        from app.routers.v3.db import execute as _exec
        _exec(
            "UPDATE pipeline_runs SET session_id = %s WHERE id = %s",
            (session_id, run_id),
        )
    return run_id


def _seed_session(user_id: str) -> str:
    """Insert an agent_sessions row and return its id."""
    from app.routers.v3.db import fetch_one
    session_id = str(uuid.uuid4())
    fetch_one(
        """
        INSERT INTO agent_sessions (id, user_id, genesis_query, status)
        VALUES (%s, %s, 'test', 'active')
        RETURNING id
        """,
        (session_id, user_id),
    )
    return session_id


def _get_session_thread(session_id: str) -> list:
    from app.routers.v3.db import fetch_one
    row = fetch_one("SELECT conversation_thread FROM agent_sessions WHERE id = %s", (session_id,))
    if row is None:
        return []
    thread = row["conversation_thread"]
    if isinstance(thread, str):
        return json.loads(thread)
    return list(thread or [])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestInjectNode404:
    def test_nonexistent_run_returns_404(self):
        uname = f"inject_404_{uuid.uuid4().hex[:8]}"
        h = _auth_headers(uname)
        fake_run_id = str(uuid.uuid4())
        r = client.post(f"/v3/runs/{fake_run_id}/inject", json={"instruction": "hello"}, headers=h)
        assert r.status_code == 404


class TestInjectNode403:
    def test_run_owned_by_other_user_returns_403(self):
        owner_name = f"inject_owner_{uuid.uuid4().hex[:8]}"
        intruder_name = f"inject_intruder_{uuid.uuid4().hex[:8]}"

        h_owner = _auth_headers(owner_name)
        h_intruder = _auth_headers(intruder_name)

        owner_id = _get_user_id(owner_name)
        run_id = _seed_run(owner_id)

        r = client.post(f"/v3/runs/{run_id}/inject", json={"instruction": "hack"}, headers=h_intruder)
        assert r.status_code == 403


class TestInjectNodeEnqueues:
    def test_successful_inject_enqueues_instruction(self):
        from app.pipeline.runners import injection_queue

        uname = f"inject_ok_{uuid.uuid4().hex[:8]}"
        h = _auth_headers(uname)
        user_id = _get_user_id(uname)
        run_id = _seed_run(user_id)

        # Drain any prior state
        injection_queue.drain(run_id)

        r = client.post(f"/v3/runs/{run_id}/inject", json={"instruction": "focus on executives"}, headers=h)
        assert r.status_code == 200
        data = r.json()
        assert "node_id" in data
        assert data["status"] == "queued"

        # Verify instruction was enqueued
        pending = injection_queue.drain(run_id)
        assert pending == ["focus on executives"]

    def test_successful_inject_returns_uuid_node_id(self):
        uname = f"inject_uuid_{uuid.uuid4().hex[:8]}"
        h = _auth_headers(uname)
        user_id = _get_user_id(uname)
        run_id = _seed_run(user_id)

        r = client.post(f"/v3/runs/{run_id}/inject", json={"instruction": "test"}, headers=h)
        assert r.status_code == 200
        node_id = r.json()["node_id"]
        # Should be a valid UUID
        uuid.UUID(node_id)


class TestInjectNodePersistsToSession:
    def test_instruction_appended_to_conversation_thread(self):
        uname = f"inject_persist_{uuid.uuid4().hex[:8]}"
        h = _auth_headers(uname)
        user_id = _get_user_id(uname)

        session_id = _seed_session(user_id)
        run_id = _seed_run(user_id, session_id=session_id)

        r = client.post(
            f"/v3/runs/{run_id}/inject",
            json={"instruction": "also check Twitter"},
            headers=h,
        )
        assert r.status_code == 200

        thread = _get_session_thread(session_id)
        assert len(thread) == 1
        msg = thread[0]
        assert msg["role"] == "user"
        assert msg["content"] == "also check Twitter"
        assert msg["type"] == "injection"
        assert "ts" in msg

    def test_multiple_injections_all_persisted(self):
        uname = f"inject_multi_{uuid.uuid4().hex[:8]}"
        h = _auth_headers(uname)
        user_id = _get_user_id(uname)

        session_id = _seed_session(user_id)
        run_id = _seed_run(user_id, session_id=session_id)

        client.post(f"/v3/runs/{run_id}/inject", json={"instruction": "first"}, headers=h)
        client.post(f"/v3/runs/{run_id}/inject", json={"instruction": "second"}, headers=h)

        thread = _get_session_thread(session_id)
        assert len(thread) == 2
        contents = [m["content"] for m in thread]
        assert "first" in contents
        assert "second" in contents


class TestInjectNodeNullSession:
    def test_inject_without_session_id_does_not_error(self):
        """When run has no session_id, persist is skipped but enqueue still works."""
        from app.pipeline.runners import injection_queue

        uname = f"inject_nosess_{uuid.uuid4().hex[:8]}"
        h = _auth_headers(uname)
        user_id = _get_user_id(uname)
        run_id = _seed_run(user_id, session_id=None)

        injection_queue.drain(run_id)

        r = client.post(f"/v3/runs/{run_id}/inject", json={"instruction": "no session"}, headers=h)
        assert r.status_code == 200

        pending = injection_queue.drain(run_id)
        assert pending == ["no session"]
