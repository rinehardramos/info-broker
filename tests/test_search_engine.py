from __future__ import annotations

import os
import sys
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from pydantic import ValidationError

# Ensure JWT_SECRET is set before any app imports that might read it
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-32chars-long!!")
# Ensure other env vars for app startup
os.environ.setdefault("INFO_BROKER_API_KEY", "test-secret-key")
os.environ.setdefault("POSTGRES_DB", "info_broker")
os.environ.setdefault("POSTGRES_USER", "user")
os.environ.setdefault("POSTGRES_PASSWORD", "password")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6333")

# Stub heavy external imports before importing the app
sys.modules.setdefault("qdrant_client", MagicMock())
sys.modules.setdefault("qdrant_client.models", MagicMock())

from app.search_engine.schemas import (
    SearchFeedbackRequest,
    SearchJobStatus,
    SearchRequest,
    SearchResultItem,
    TokenRequest,
)


class TestSchemas:
    def test_search_request_defaults(self):
        req = SearchRequest(query="test")
        assert req.query == "test"
        assert req.deep_search is False
        assert req.max_parallel is None
        assert req.max_budget == 5
        assert req.plugins is None
        assert req.callback_url is None

    def test_search_request_empty_query_rejected(self):
        with pytest.raises(ValidationError):
            SearchRequest(query="")

    def test_search_request_budget_clamped_to_max(self):
        req = SearchRequest(query="test", max_budget=100)
        assert req.max_budget == 20

    def test_search_feedback_valid_range(self):
        fb = SearchFeedbackRequest(interest=1, relevance=5, usefulness=3)
        assert fb.interest == 1
        assert fb.relevance == 5
        assert fb.usefulness == 3

    def test_search_feedback_interest_too_high(self):
        with pytest.raises(ValidationError):
            SearchFeedbackRequest(interest=6, relevance=3, usefulness=3)

    def test_search_feedback_interest_too_low(self):
        with pytest.raises(ValidationError):
            SearchFeedbackRequest(interest=0, relevance=3, usefulness=3)

    def test_search_feedback_relevance_too_high(self):
        with pytest.raises(ValidationError):
            SearchFeedbackRequest(interest=3, relevance=6, usefulness=3)

    def test_search_feedback_relevance_too_low(self):
        with pytest.raises(ValidationError):
            SearchFeedbackRequest(interest=3, relevance=0, usefulness=3)

    def test_search_feedback_usefulness_too_high(self):
        with pytest.raises(ValidationError):
            SearchFeedbackRequest(interest=3, relevance=3, usefulness=6)

    def test_search_feedback_usefulness_too_low(self):
        with pytest.raises(ValidationError):
            SearchFeedbackRequest(interest=3, relevance=3, usefulness=0)

    def test_token_request_basic_creation(self):
        req = TokenRequest(username="alice")
        assert req.username == "alice"

    def test_search_result_item_shape(self):
        item = SearchResultItem(
            id=uuid.uuid4(),
            plugin="google",
            title="Test Result",
            snippet="A short snippet.",
            scores={"confidence": 0.9},
        )
        assert item.plugin == "google"
        assert item.title == "Test Result"
        assert item.url is None
        assert item.published_at is None
        assert item.is_deep_child is False
        assert item.feedback is None
        assert isinstance(item.scores, dict)

    def test_search_job_status_enum_values(self):
        assert SearchJobStatus.PENDING == "pending"
        assert SearchJobStatus.COMPLETED == "completed"


from app.search_engine.auth import DUMMY_USER_ID, create_token, decode_token  # noqa: E402
from app.search_engine.db import build_dsn, SEARCH_TABLES_DDL  # noqa: E402


class TestDb:
    def test_build_dsn_defaults(self, monkeypatch):
        monkeypatch.setenv("POSTGRES_DB", "info_broker")
        monkeypatch.setenv("POSTGRES_USER", "user")
        monkeypatch.setenv("POSTGRES_PASSWORD", "pass")
        monkeypatch.setenv("POSTGRES_HOST", "localhost")
        monkeypatch.setenv("POSTGRES_PORT", "5433")
        result = build_dsn()
        assert "info_broker" in result
        assert "5433" in result

    def test_ddl_contains_all_tables(self):
        expected_tables = [
            "search_users",
            "search_jobs",
            "search_results",
            "search_reports",
            "search_feedback",
            "search_plugins_config",
            "search_domain_scores",
        ]
        for table in expected_tables:
            assert table in SEARCH_TABLES_DDL, f"Expected table '{table}' not found in SEARCH_TABLES_DDL"


class TestAuth:
    def test_create_and_decode_token(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "test-secret-key")
        token = create_token(username="alice")
        payload = decode_token(token)
        assert payload["sub"] == str(DUMMY_USER_ID)
        assert payload["username"] == "alice"

    def test_decode_expired_token_raises(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "test-secret-key")
        token = create_token(username="alice", expiry_hours=0.000001)
        time.sleep(0.1)
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_token(token)

    def test_decode_invalid_token_raises(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "test-secret-key")
        with pytest.raises(jwt.InvalidTokenError):
            decode_token("garbage.token.here")

    def test_missing_jwt_secret_raises(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET", raising=False)
        with pytest.raises(ValueError, match="JWT_SECRET"):
            create_token(username="alice")


import asyncio  # noqa: E402
from datetime import datetime  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

from app.search_engine.plugins.base import SearchPlugin, PluginResult  # noqa: E402
from app.search_engine.plugins.ddg import DdgPlugin  # noqa: E402
from app.search_engine.plugins import PluginRegistry  # noqa: E402


class TestPluginBase:
    def test_plugin_result_creation(self):
        result = PluginResult(
            title="Test Title",
            url="https://example.com",
            snippet="A short snippet.",
            full_text="Full text content here.",
            published_at=datetime(2024, 1, 15),
            source_name="ddg",
            metadata={"extra": "data"},
        )
        assert result.title == "Test Title"

    def test_ddg_plugin_attributes(self):
        plugin = DdgPlugin()
        assert plugin.name == "ddg"
        assert plugin.requires_api_key is False
        assert plugin.available() is True

    def test_plugin_registry_discovers_ddg(self):
        registry = PluginRegistry()
        registry.auto_discover()
        names = [p.name for p in registry.all()]
        assert "ddg" in names

    def test_plugin_registry_get(self):
        registry = PluginRegistry()
        registry.auto_discover()
        plugin = registry.get("ddg")
        assert plugin is not None
        assert plugin.name == "ddg"

    def test_plugin_registry_get_unknown(self):
        registry = PluginRegistry()
        registry.auto_discover()
        result = registry.get("nonexistent")
        assert result is None


class TestDdgPlugin:
    def test_ddg_search_returns_results(self):
        mock_hits = [
            {"title": "Result 1", "href": "https://example.com/1", "body": "Snippet 1"},
            {"title": "Result 2", "href": "https://example.com/2", "body": "Snippet 2"},
        ]
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
        mock_ddgs_instance.text = MagicMock(return_value=mock_hits)

        with patch("app.search_engine.plugins.ddg.DDGS", return_value=mock_ddgs_instance):
            plugin = DdgPlugin()
            results = asyncio.run(plugin.search("test query", max_results=2))

        assert len(results) == 2
        assert results[0].title == "Result 1"
        assert results[0].url == "https://example.com/1"
        assert results[0].snippet == "Snippet 1"
        assert results[1].title == "Result 2"

    def test_ddg_search_handles_failure(self):
        with patch("app.search_engine.plugins.ddg.DDGS", side_effect=Exception("Network error")):
            plugin = DdgPlugin()
            results = asyncio.run(plugin.search("test query"))

        assert results == []


from datetime import timezone, timedelta  # noqa: E402
from app.search_engine.grading import score_result, freshness_score, relevance_score  # noqa: E402
from app.search_engine.domain_tiers import get_domain_reliability  # noqa: E402


class TestDomainTiers:
    def test_known_tier1(self):
        assert get_domain_reliability("reuters.com") == 1.0

    def test_known_tier2(self):
        score = get_domain_reliability("bbc.com")
        assert 0.7 <= score <= 0.9

    def test_unknown(self):
        assert get_domain_reliability("randomsite12345.com") == 0.4

    def test_subdomain_matches_parent(self):
        assert get_domain_reliability("news.bbc.com") == get_domain_reliability("bbc.com")

    def test_none_returns_default(self):
        assert get_domain_reliability(None) == 0.4


class TestGrading:
    def test_freshness_today(self):
        assert freshness_score(datetime.now(timezone.utc)) == 1.0

    def test_freshness_7_days(self):
        score = freshness_score(datetime.now(timezone.utc) - timedelta(days=7))
        assert 0.4 <= score <= 0.6

    def test_freshness_none(self):
        assert freshness_score(None) == 0.3

    def test_relevance_high_match(self):
        assert relevance_score("python web framework", "Python Web Framework Comparison") > 0.7

    def test_relevance_no_match(self):
        assert relevance_score("python web framework", "Best recipes for apple pie") < 0.3

    def test_score_result_all_dimensions(self):
        result = score_result(
            query="python web framework",
            title="Python Web Framework Comparison",
            snippet="A comparison of popular Python web frameworks.",
            url="https://reuters.com/tech/python-frameworks",
            published_at=datetime.now(timezone.utc),
        )
        assert set(result.keys()) == {"relevance", "freshness", "source_reliability", "composite"}
        for key, val in result.items():
            assert 0.0 <= val <= 1.0, f"{key} out of range: {val}"


from app.search_engine.qdrant import build_embedding_text  # noqa: E402


class TestQdrant:
    def test_build_embedding_text(self):
        result = build_embedding_text(
            title="Test Title",
            snippet="A snippet here",
            full_text="Full text content",
        )
        assert "Test Title" in result
        assert "A snippet here" in result
        assert "Full text content" in result

    def test_build_embedding_text_truncates(self):
        result = build_embedding_text(
            title="Test Title",
            snippet="A snippet here",
            full_text="x" * 10000,
        )
        assert len(result) <= 4100

    def test_build_embedding_text_handles_none(self):
        result = build_embedding_text(
            title="Test Title",
            snippet="A snippet here",
            full_text=None,
        )
        assert "Test Title" in result
        assert "A snippet here" in result


from app.search_engine.executor import _deduplicate_results  # noqa: E402


class TestExecutorHelpers:
    def test_deduplicate_by_url(self):
        results = [
            PluginResult(title="A", url="https://example.com/page", snippet="s", full_text=None, published_at=None, source_name="ddg"),
            PluginResult(title="B", url="https://example.com/page", snippet="s", full_text=None, published_at=None, source_name="ddg"),
            PluginResult(title="C", url="https://other.com/page", snippet="s", full_text=None, published_at=None, source_name="ddg"),
            PluginResult(title="D", url=None, snippet="s", full_text=None, published_at=None, source_name="ddg"),
        ]
        deduped = _deduplicate_results(results)
        assert len(deduped) == 3
        titles = [r.title for r in deduped]
        assert "A" in titles
        assert "C" in titles
        assert "D" in titles
        assert "B" not in titles

    def test_deduplicate_empty(self):
        assert _deduplicate_results([]) == []


import inspect  # noqa: E402

from app.search_engine.feedback import validate_feedback_ownership, save_feedback  # noqa: E402


class TestFeedback:
    def test_validate_feedback_ownership_structure(self):
        sig = inspect.signature(validate_feedback_ownership)
        params = sig.parameters
        assert "result_id" in params, "validate_feedback_ownership must have 'result_id' param"
        assert "user_id" in params, "validate_feedback_ownership must have 'user_id' param"

    def test_save_feedback_structure(self):
        sig = inspect.signature(save_feedback)
        params = sig.parameters
        assert "result_id" in params, "save_feedback must have 'result_id' param"
        assert "user_id" in params, "save_feedback must have 'user_id' param"
        assert "interest" in params, "save_feedback must have 'interest' param"
        assert "relevance" in params, "save_feedback must have 'relevance' param"
        assert "usefulness" in params, "save_feedback must have 'usefulness' param"
        assert "comment" in params, "save_feedback must have 'comment' param"


# ---------------------------------------------------------------------------
# Router integration tests
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

from app.search_engine.auth import create_token  # noqa: E402
from app.search_engine import router as router_module  # noqa: E402


def _mock_lifespan():
    """Return a no-op lifespan so TestClient does not hit real DB/Qdrant."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _noop(app):
        yield

    return _noop


# Patch the lifespan before importing app.main so TestClient skips real migrations
with patch("app.main.lifespan", _mock_lifespan()):
    from app.main import app as _app  # noqa: E402

# Rebuild the app's lifespan to the no-op for test usage
_app.router.lifespan_context = _mock_lifespan()

_client = TestClient(_app)


class TestRouter:
    def _auth_header(self) -> dict[str, str]:
        token = create_token(username="testuser")
        return {"Authorization": f"Bearer {token}"}

    def test_auth_token_endpoint(self):
        r = _client.post("/v2/auth/token", json={"username": "testuser"})
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_submit_search_requires_auth(self):
        r = _client.post("/v2/search", json={"query": "test"})
        assert r.status_code in (401, 422)

    @patch.object(router_module, "_executor")
    @patch("app.search_engine.router.db")
    def test_submit_search(self, mock_db, mock_executor):
        job_id = uuid.uuid4()
        mock_db.ensure_user = AsyncMock(return_value=DUMMY_USER_ID)
        mock_executor.submit = AsyncMock(return_value=job_id)

        r = _client.post(
            "/v2/search",
            json={"query": "test"},
            headers=self._auth_header(),
        )
        assert r.status_code == 202
        body = r.json()
        assert body["job_id"] == str(job_id)
        assert body["status"] == "pending"
        assert "status_url" in body
        assert "results_url" in body

    @patch("app.search_engine.router.db")
    def test_get_job_status(self, mock_db):
        job_id = uuid.uuid4()
        mock_db.ensure_user = AsyncMock(return_value=DUMMY_USER_ID)
        mock_db.get_job = AsyncMock(return_value={
            "id": job_id,
            "user_id": DUMMY_USER_ID,
            "query": "test query",
            "status": "completed",
            "started_at": None,
            "completed_at": None,
            "error": None,
        })
        mock_db.get_job_result_count = AsyncMock(return_value=5)

        r = _client.get(
            f"/v2/search/{job_id}/status",
            headers=self._auth_header(),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "completed"
        assert body["total_results"] == 5
