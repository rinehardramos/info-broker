from __future__ import annotations

import time
import uuid

import jwt
import pytest
from pydantic import ValidationError

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
