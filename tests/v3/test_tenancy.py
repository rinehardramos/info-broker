"""Tenant isolation tests — proves cross-org / wrong-user requests are denied.

Section 1 — Unit tests for the tenancy helpers (mock fetch_one).
Section 2 — Endpoint-level integration tests that drive the FastAPI handlers
            with the helpers monkey-patched to raise (so we don't need a DB).
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

# Ensure heavy/optional deps don't blow up at import time and the API-key env
# var is set so anything that imports app.main works headlessly.
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
    user_org_id,
)

DB = "app.routers.v3.tenancy.fetch_one"


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

    def test_rejects_mismatched_user_and_org_with_404(self):
        with patch(DB, return_value=None) as m:
            with pytest.raises(HTTPException) as exc:
                require_system_user("user-1", "org-other")
            assert exc.value.status_code == 404
            assert "not found" in str(exc.value.detail).lower()
            m.assert_called_once()
            # Make sure the query is scoped by BOTH user_id and org_id
            sql, params = m.call_args[0]
            assert "org_id = %s" in sql
            assert params == ("user-1", "org-other")

    def test_returns_user_when_valid(self):
        row = {"id": "user-1", "org_id": "org-1"}
        with patch(DB, return_value=row):
            assert require_system_user("user-1", "org-1") == row


class TestRequireUserRun:
    def test_rejects_wrong_org_with_404(self):
        with patch(DB, return_value=None) as m:
            with pytest.raises(HTTPException) as exc:
                require_user_run("run-1", "user-1", "org-other")
            assert exc.value.status_code == 404
            assert "Run not found" in str(exc.value.detail)
            sql, params = m.call_args[0]
            assert "org_id = %s" in sql
            assert params == ("run-1", "user-1", "org-other")

    def test_rejects_wrong_user_with_404(self):
        with patch(DB, return_value=None):
            with pytest.raises(HTTPException) as exc:
                require_user_run("run-1", "stranger", "org-1")
            assert exc.value.status_code == 404

    def test_returns_run_when_valid(self):
        row = {"id": "run-1", "user_id": "user-1", "org_id": "org-1"}
        with patch(DB, return_value=row):
            assert require_user_run("run-1", "user-1", "org-1") == row


class TestRequireUserSource:
    def test_rejects_another_orgs_source_with_404(self):
        with patch(DB, return_value=None) as m:
            with pytest.raises(HTTPException) as exc:
                require_user_source("src-1", "user-1", "org-other")
            assert exc.value.status_code == 404
            assert "Source not found" in str(exc.value.detail)
            sql, params = m.call_args[0]
            assert "org_id = %s" in sql
            assert params == ("src-1", "user-1", "org-other")

    def test_rejects_wrong_user_with_404(self):
        with patch(DB, return_value=None):
            with pytest.raises(HTTPException) as exc:
                require_user_source("src-1", "stranger", "org-1")
            assert exc.value.status_code == 404

    def test_returns_source_when_valid(self):
        row = {"id": "src-1", "user_id": "user-1", "org_id": "org-1"}
        with patch(DB, return_value=row):
            assert require_user_source("src-1", "user-1", "org-1") == row


# ---------------------------------------------------------------------------
# Section 2 — Endpoint integration tests (handlers invoked directly with
# tenancy helpers monkey-patched to raise — no DB required).
# ---------------------------------------------------------------------------


class TestSourceUploadSystemTenancy:
    """`/v3/sources/upload/system` must enforce user+org via require_system_user."""

    def test_missing_org_id_rejected_400(self):
        from app.routers.v3 import sources_api

        with patch.object(sources_api, "require_system_user") as m:
            m.side_effect = HTTPException(status_code=400, detail="org_id is required")
            with pytest.raises(HTTPException) as exc:
                asyncio.run(sources_api.upload_source_system(
                    file=MagicMock(filename="x.csv"),
                    user_id="user-1",
                    org_id="",
                    run_id=None,
                    _key="test",
                ))
            assert exc.value.status_code == 400
            assert "org_id" in str(exc.value.detail)
            m.assert_called_once_with("user-1", "")

    def test_mismatched_user_and_org_rejected_404(self):
        from app.routers.v3 import sources_api

        with patch.object(sources_api, "require_system_user") as m:
            m.side_effect = HTTPException(
                status_code=404, detail="User not found in organization"
            )
            with pytest.raises(HTTPException) as exc:
                asyncio.run(sources_api.upload_source_system(
                    file=MagicMock(filename="x.csv"),
                    user_id="user-1",
                    org_id="org-of-someone-else",
                    run_id=None,
                    _key="test",
                ))
            assert exc.value.status_code == 404
            assert "not found" in str(exc.value.detail).lower()


class TestAsyncIsStartSystemTenancy:
    """`/v3/agent/research/async/system` must guard via require_system_user."""

    def test_missing_org_id_returns_error(self):
        from app.routers.v3 import agent

        result = asyncio.run(agent.start_research_async_system(
            {"user_id": "user-1", "query": "q"},
            _key="test",
        ))
        assert "error" in result
        assert "org_id" in result["error"]

    def test_missing_user_id_returns_error(self):
        from app.routers.v3 import agent

        result = asyncio.run(agent.start_research_async_system(
            {"org_id": "org-1", "query": "q"},
            _key="test",
        ))
        assert "error" in result
        assert "user_id" in result["error"]

    def test_missing_query_returns_error(self):
        from app.routers.v3 import agent

        result = asyncio.run(agent.start_research_async_system(
            {"user_id": "user-1", "org_id": "org-1", "query": ""},
            _key="test",
        ))
        assert "error" in result
        assert "query" in result["error"]

    def test_mismatched_user_and_org_returns_error(self, monkeypatch):
        from app.routers.v3 import agent

        def boom(uid, org):
            raise HTTPException(status_code=404, detail="User not found in organization")

        monkeypatch.setattr(agent, "require_system_user", boom)

        result = asyncio.run(agent.start_research_async_system(
            {"user_id": "user-1", "org_id": "wrong-org", "query": "q"},
            _key="test",
        ))
        assert "error" in result
        assert result["user_id"] == "user-1"
        assert result["org_id"] == "wrong-org"


class TestRunStatusSystemTenancy:
    """`/v3/agent/research/runs/{run_id}/system` must reject wrong org."""

    def test_wrong_org_returns_404(self, monkeypatch):
        from app.routers.v3 import agent

        def fake_require_system_user(uid, org):
            return {"id": uid, "org_id": org}

        def fake_require_user_run(run_id, uid, org):
            # Simulates "no row" because the run belongs to another org/user
            raise HTTPException(status_code=404, detail="Run not found")

        monkeypatch.setattr(agent, "require_system_user", fake_require_system_user)
        monkeypatch.setattr(agent, "require_user_run", fake_require_user_run)

        with pytest.raises(HTTPException) as exc:
            asyncio.run(agent.get_research_run_system(
                "run-1", user_id="user-1", org_id="wrong-org", _key="test"
            ))
        assert exc.value.status_code == 404

    def test_wrong_user_returns_404(self, monkeypatch):
        from app.routers.v3 import agent

        monkeypatch.setattr(
            agent, "require_system_user", lambda uid, org: {"id": uid, "org_id": org}
        )

        def fake_require_user_run(run_id, uid, org):
            raise HTTPException(status_code=404, detail="Run not found")

        monkeypatch.setattr(agent, "require_user_run", fake_require_user_run)

        with pytest.raises(HTTPException) as exc:
            asyncio.run(agent.get_research_run_system(
                "run-1", user_id="stranger", org_id="org-1", _key="test"
            ))
        assert exc.value.status_code == 404


class TestArtifactsSystemTenancy:
    """`/v3/agent/research/runs/{run_id}/artifacts/system` must reject wrong org."""

    def test_wrong_org_returns_404(self, monkeypatch):
        from app.routers.v3 import agent

        monkeypatch.setattr(
            agent, "require_system_user", lambda uid, org: {"id": uid, "org_id": org}
        )

        def fake_require_user_run(run_id, uid, org):
            raise HTTPException(status_code=404, detail="Run not found")

        monkeypatch.setattr(agent, "require_user_run", fake_require_user_run)

        with pytest.raises(HTTPException) as exc:
            asyncio.run(agent.get_research_run_artifacts_system(
                "run-1",
                user_id="user-1",
                org_id="wrong-org",
                limit=100,
                offset=0,
                _key="test",
            ))
        assert exc.value.status_code == 404

    def test_unknown_user_for_org_returns_404(self, monkeypatch):
        from app.routers.v3 import agent

        def fake_require_system_user(uid, org):
            raise HTTPException(
                status_code=404, detail="User not found in organization"
            )

        monkeypatch.setattr(agent, "require_system_user", fake_require_system_user)

        with pytest.raises(HTTPException) as exc:
            asyncio.run(agent.get_research_run_artifacts_system(
                "run-1",
                user_id="stranger",
                org_id="org-1",
                limit=100,
                offset=0,
                _key="test",
            ))
        assert exc.value.status_code == 404
