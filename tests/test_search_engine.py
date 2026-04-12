from __future__ import annotations

import uuid

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
