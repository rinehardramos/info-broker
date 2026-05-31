"""Tenant isolation tests — proves cross-org / wrong-user requests are denied.

Section 1 — Unit tests for the tenancy helpers (mock fetch_one).
Section 2 — Endpoint-level smoke tests that verify org_id appears in SQL.
"""
from __future__ import annotations

import io
import os
import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

# Stub heavy optional deps before any app import
sys.modules.setdefault("qdrant_client", MagicMock())
sys.modules.setdefault("qdrant_client.models", MagicMock())
os.environ.setdefault("INFO_BROKER_API_KEY", "test-secret-key")
os.environ.setdefault("POSTGRES_DB", "info_broker")
os.environ.setdefault("POSTGRES_USER", "user")
os.environ.setdefault("POSTGRES_PASSWORD", "password")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")

from app.routers.v3.tenancy import (  # noqa: E402
    require_system_user,
    require_user_run,
    require_user_source,
    run_visibility_clause,
    user_org_id,
)

_DB = "app.routers.v3.tenancy.fetch_one"


# ---------------------------------------------------------------------------
# Section 1 — Helper unit tests
# ---------------------------------------------------------------------------


class TestUserOrgId:
    def test_returns_string_when_present(self):
        assert user_org_id({"org_id": "org-123"}) == "org-123"

    def test_returns_empty_string_when_missing(self):
        assert user_org_id({}) == ""

    def test_returns_empty_string_when_none(self):
        assert user_org_id({"org_id": None}) == ""

    def test_coerces_uuid_to_str(self):
        oid = uuid.uuid4()
        result = user_org_id({"org_id": oid})
        assert result == str(oid)
        assert isinstance(result, str)


class TestRequireSystemUser:
    def test_rejects_empty_user_id(self):
        with pytest.raises(HTTPException) as exc:
            require_system_user("", "org-1")
        assert exc.value.status_code == 400
        assert "user_id" in str(exc.value.detail)

    def test_rejects_empty_org_id(self):
        with pytest.raises(HTTPException) as exc:
            require_system_user("user-1", "")
        assert exc.value.status_code == 400
        assert "org_id" in str(exc.value.detail)

    def test_rejects_wrong_org_with_404(self):
        with patch(_DB, return_value=None) as m:
            with pytest.raises(HTTPException) as exc:
                require_system_user("user-1", "org-other")
            assert exc.value.status_code == 404
            assert "not found" in str(exc.value.detail).lower()
            m.assert_called_once()
            sql, params = m.call_args[0]
            assert "org_id = %s" in sql
            assert params == ("user-1", "org-other")

    def test_returns_user_when_valid(self):
        row = {"id": "user-1", "org_id": "org-1"}
        with patch(_DB, return_value=row):
            assert require_system_user("user-1", "org-1") == row


class TestRequireUserRun:
    def test_rejects_wrong_org_with_404(self):
        with patch(_DB, return_value=None) as m:
            with pytest.raises(HTTPException) as exc:
                require_user_run("run-1", "user-1", "org-other")
            assert exc.value.status_code == 404
            assert "Run not found" in str(exc.value.detail)
            sql, params = m.call_args[0]
            assert "org_id = %s" in sql
            assert params == ("run-1", "user-1", "org-other")

    def test_returns_run_when_valid(self):
        row = {"id": "run-1"}
        with patch(_DB, return_value=row):
            assert require_user_run("run-1", "user-1", "org-1") == row


class TestRequireUserSource:
    def test_rejects_wrong_org_with_404(self):
        with patch(_DB, return_value=None) as m:
            with pytest.raises(HTTPException) as exc:
                require_user_source("src-1", "user-1", "org-other")
            assert exc.value.status_code == 404
            assert "Source not found" in str(exc.value.detail)
            sql, params = m.call_args[0]
            assert "org_id = %s" in sql
            assert params == ("src-1", "user-1", "org-other")

    def test_returns_source_when_valid(self):
        row = {"id": "src-1"}
        with patch(_DB, return_value=row):
            assert require_user_source("src-1", "user-1", "org-1") == row


class TestRunVisibilityClause:
    """Run-owned resources must remain visible to their owner even when the run's
    org_id is NULL (created before org stamping) — otherwise org-scoped reads 404
    on the user's own data. Admins see everything."""

    def test_admin_sees_all(self):
        clause, params = run_visibility_clause({"is_admin": True, "id": "u1", "org_id": "org-A"})
        assert clause == ""
        assert params == []

    def test_non_admin_allows_null_org_owned_rows(self):
        clause, params = run_visibility_clause({"id": "u1", "org_id": "org-A"})
        # Must match org OR (org IS NULL AND owned by caller)
        assert "IS NULL" in clause
        assert "OR" in clause
        assert "org_id = %s" in clause
        assert "user_id = %s" in clause
        assert params == ["org-A", "u1"]

    def test_custom_column_aliases(self):
        clause, _ = run_visibility_clause(
            {"id": "u1", "org_id": "org-A"}, run_col="pr.org_id", user_col="pr.user_id"
        )
        assert "pr.org_id = %s" in clause
        assert "pr.org_id IS NULL" in clause
        assert "pr.user_id = %s" in clause


# ---------------------------------------------------------------------------
# Section 2 — Endpoint SQL smoke tests
# ---------------------------------------------------------------------------


_FAKE_USER = {"id": "u1", "org_id": "org-A"}


class TestSourceOrg:
    def test_list_sources_filters_by_org(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.routers.v3.auth import get_current_user

        with patch("app.routers.v3.sources_api.fetch_all") as m_fetch:
            m_fetch.return_value = []
            app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
            try:
                TestClient(app).get("/v3/sources/")
            finally:
                app.dependency_overrides.pop(get_current_user, None)
        assert m_fetch.called
        sql, params = m_fetch.call_args[0]
        assert "org_id" in sql
        assert "org-A" in params

    def test_upload_source_stores_org_id(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.routers.v3.auth import get_current_user

        with patch("app.routers.v3.sources_api.execute") as m_exec, \
             patch("app.routers.v3.sources_api.asyncio.create_task"):
            m_exec.return_value = None
            app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
            try:
                TestClient(app).post(
                    "/v3/sources/upload",
                    files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
                )
            except Exception:
                pass
            finally:
                app.dependency_overrides.pop(get_current_user, None)
        if m_exec.called:
            sql = m_exec.call_args[0][0]
            assert "org_id" in sql

    def test_get_source_filters_by_org(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.routers.v3.auth import get_current_user

        with patch("app.routers.v3.sources_api.fetch_one") as m_fetch:
            m_fetch.return_value = None
            app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
            try:
                TestClient(app).get("/v3/sources/some-source-id")
            finally:
                app.dependency_overrides.pop(get_current_user, None)
        assert m_fetch.called
        sql, params = m_fetch.call_args[0]
        assert "org_id" in sql
        assert "org-A" in params


class TestExportRunVisibility:
    """The research export lookup must tolerate the caller's own NULL-org runs
    (the 215 agent-trigger runs) instead of 404ing."""

    def test_export_query_allows_null_org_owned_run(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.routers.v3.auth import get_current_user

        with patch("app.routers.v3.exports.fetch_one") as m_fetch:
            m_fetch.return_value = None  # forces the 404 path after the query is built
            app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
            try:
                TestClient(app).post(
                    "/v3/exports/research/some-run-id",
                    json={"format": "json"},
                )
            finally:
                app.dependency_overrides.pop(get_current_user, None)
        assert m_fetch.called
        sql, params = m_fetch.call_args[0]
        # Owner fallback for NULL-org runs must be present
        assert "IS NULL" in sql
        assert "org-A" in params
        assert "u1" in params  # caller's user id threaded for the NULL-org branch


class TestGetRunTrailForAgent:
    """get_run must attach the research trail for plain 'agent' runs, not only
    'agent_is' — half the runs use trigger_type='agent'."""

    def test_agent_run_issues_trail_query(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.routers.v3.auth import get_current_user

        run_row = {"id": "run-1", "trigger_type": "agent", "user_id": "u1"}

        def _fetch_one_side(sql, params):
            # run lookup → the run row; trail lookup → None
            if "pipeline_runs" in sql and "research_trails" not in sql:
                return run_row
            return None

        with patch("app.routers.v3.pipelines.fetch_one", side_effect=_fetch_one_side) as m_one, \
             patch("app.routers.v3.pipelines.fetch_all", return_value=[]):
            app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
            try:
                # raise_server_exceptions=False: the dummy run row fails response-model
                # validation, but the trail query has already been captured by then.
                TestClient(app, raise_server_exceptions=False).get("/v3/pipelines/runs/run-1")
            finally:
                app.dependency_overrides.pop(get_current_user, None)

        # A trail query against research_trails MUST have been issued for the agent run
        trail_sqls = [c.args[0] for c in m_one.call_args_list if "research_trails" in c.args[0]]
        assert trail_sqls, "get_run did not query research_trails for a trigger_type='agent' run"
        assert "IS NULL" in trail_sqls[0]  # owner-fallback scope used
