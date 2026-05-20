"""Tests for share-link augmentation + hypothesis comments."""
from __future__ import annotations

import os, uuid
from unittest.mock import patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")


def test_hypothesis_comment_pydantic_validation():
    from app.routers.v3.working_memory import HypothesisCommentIn
    # Body length enforced (1..4000)
    HypothesisCommentIn(body="ok")  # min ok
    try:
        HypothesisCommentIn(body="")
        raise AssertionError("empty body should fail validation")
    except Exception:
        pass
    try:
        HypothesisCommentIn(body="x" * 4001)
        raise AssertionError("4001-char body should fail validation")
    except Exception:
        pass


def test_share_endpoint_includes_loop_view_when_snapshots_exist():
    """The public share endpoint must surface the loop's analytical
    artifacts (synthesis, hypotheses, findings) — read-only and safe for
    public links."""
    from fastapi.testclient import TestClient
    from app.routers.v3.share import router as share_router
    from fastapi import FastAPI
    test_app = FastAPI()
    test_app.include_router(share_router)
    client = TestClient(test_app)

    # Mock fetch_one + fetch_all calls in the share module.
    fake_run_id = str(uuid.uuid4())
    fake_token = "test-token-abc"
    from datetime import datetime, timezone, timedelta
    expires = datetime.now(timezone.utc) + timedelta(hours=1)

    def fake_fetch_one(query, params):
        if "run_share_links" in query:
            return {
                "token": fake_token, "run_id": fake_run_id,
                "expires_at": expires, "revoked_at": None,
                "created_at": datetime.now(timezone.utc),
            }
        if "FROM pipeline_runs" in query:
            return {"id": fake_run_id, "query": "test query",
                    "status": "succeeded",
                    "started_at": datetime.now(timezone.utc),
                    "finished_at": datetime.now(timezone.utc)}
        if "FROM research_trails" in query:
            return None
        return None

    def fake_fetch_all(query, params):
        if "working_memory_snapshots" in query:
            return [{
                "turn": 3, "phase": "synthesize",
                "working_memory": {
                    "synthesis_summary": "Test synthesis answer.",
                    "hypotheses": [{"id": "abc12345-...", "statement": "H1",
                                    "status": "supported", "confidence": 0.9,
                                    "falsification_condition": "X would refute"}],
                    "findings": [{"title": "F1", "source_url": "https://x",
                                  "source_class": "primary_official",
                                  "confidence": 0.85}],
                    "evidence_matrix": [
                        {"finding_id": "abc", "hypothesis_id": "abc",
                         "consistency": "consistent"},
                        {"finding_id": "def", "hypothesis_id": "abc",
                         "consistency": "inconsistent"},
                    ],
                },
            }]
        return []

    with patch("app.routers.v3.share.fetch_one", side_effect=fake_fetch_one), \
         patch("app.routers.v3.db.fetch_all", side_effect=fake_fetch_all):
        r = client.get(f"/share/{fake_token}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["loop"] is not None
        loop = body["loop"]
        assert loop["kind"] == "loop"
        assert loop["synthesis_summary"] == "Test synthesis answer."
        assert len(loop["hypotheses"]) == 1
        assert loop["hypotheses"][0]["status"] == "supported"
        assert loop["findings_count"] == 1
        assert loop["ach_summary"]["consistent"] == 1
        assert loop["ach_summary"]["inconsistent"] == 1
