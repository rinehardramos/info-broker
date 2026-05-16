"""Tests for Story 3.9 — public read-only run share links via signed tokens."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Minimal environment stubs so app.main imports cleanly without live services
# ---------------------------------------------------------------------------
os.environ.setdefault("INFO_BROKER_API_KEY", "test-secret-key")
os.environ.setdefault("POSTGRES_DB", "info_broker")
os.environ.setdefault("POSTGRES_USER", "user")
os.environ.setdefault("POSTGRES_PASSWORD", "password")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6333")

sys.modules.setdefault("qdrant_client", MagicMock())
sys.modules.setdefault("qdrant_client.models", MagicMock())

from fastapi.testclient import TestClient  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_USER_A = str(uuid.uuid4())
_USER_B = str(uuid.uuid4())
_RUN_ID = str(uuid.uuid4())
_TOKEN = "abc123urlsafetoken_xyz"

_NOW = datetime.now(timezone.utc)
_FUTURE = _NOW + timedelta(days=7)
_PAST = _NOW - timedelta(days=1)


def _user(uid: str) -> dict:
    return {"id": uid, "username": "tester", "is_active": True, "role": "analyst", "is_admin": False}


def _make_client(user_id: str = _USER_A):
    from app.main import app
    from app.routers.v3.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _user(user_id)
    return TestClient(app)


_DB = "app.routers.v3.share"

_GOOD_RUN = {"id": _RUN_ID, "user_id": _USER_A, "query": "test query",
             "status": "completed", "started_at": _NOW, "finished_at": _NOW}
_GOOD_LINK = {
    "token": _TOKEN,
    "run_id": uuid.UUID(_RUN_ID),
    "created_by": uuid.UUID(_USER_A),
    "expires_at": _FUTURE,
    "revoked_at": None,
    "created_at": _NOW,
}
_TRAIL = {
    "trail": {
        "branches": [
            {"phase_id": "p1", "slot_idx": 0, "candidate_name": "Alice",
             "source_class": "live_search", "confidence": 0.9, "evidence_summary": "found"}
        ],
        "phases": ["p1"],
        "status": "completed",
        "ranked_candidates": [
            {"name": "Alice", "confidence": 0.9, "signal_scores": {}, "evidence": [], "slot_idx": 0}
        ],
    },
    "findings": [],
}


# ===========================================================================
# test_share_create_returns_token_and_url
# ===========================================================================
class TestCreateShare:
    def test_share_create_returns_token_and_url(self):
        with (
            patch(f"{_DB}.fetch_one", return_value=_GOOD_RUN),
            patch(f"{_DB}.execute"),
        ):
            client = _make_client(_USER_A)
            r = client.post(f"/v3/runs/{_RUN_ID}/share", json={"ttl_days": 7})
        assert r.status_code == 201
        data = r.json()
        assert "token" in data
        assert "share_url" in data
        assert "/share/" in data["share_url"]
        assert "expires_at" in data

    # ===========================================================================
    # test_share_create_requires_run_ownership
    # ===========================================================================
    def test_share_create_requires_run_ownership(self):
        # Run is owned by USER_A, but USER_B is making the request
        with patch(f"{_DB}.fetch_one", return_value=_GOOD_RUN):
            client = _make_client(_USER_B)
            r = client.post(f"/v3/runs/{_RUN_ID}/share", json={})
        assert r.status_code == 403

    # ===========================================================================
    # test_share_create_ttl_default_7_days
    # ===========================================================================
    def test_share_create_ttl_default_7_days(self):
        captured: list[tuple] = []

        def mock_execute(query: str, params: tuple):
            captured.append(params)

        with (
            patch(f"{_DB}.fetch_one", return_value=_GOOD_RUN),
            patch(f"{_DB}.execute", side_effect=mock_execute),
        ):
            client = _make_client(_USER_A)
            r = client.post(f"/v3/runs/{_RUN_ID}/share", json={})
        assert r.status_code == 201
        # params[3] = expires_at (INSERT: token, run_id, created_by, expires_at)
        assert len(captured) == 1
        expires_at = captured[0][3]
        if isinstance(expires_at, str):
            from datetime import datetime as _dt
            expires_at = _dt.fromisoformat(expires_at)
        delta = expires_at - datetime.now(timezone.utc)
        assert 6.9 <= delta.total_seconds() / 86400 <= 7.1

    # ===========================================================================
    # test_share_create_ttl_max_30_days
    # ===========================================================================
    def test_share_create_ttl_max_30_days(self):
        with patch(f"{_DB}.fetch_one", return_value=_GOOD_RUN):
            client = _make_client(_USER_A)
            r = client.post(f"/v3/runs/{_RUN_ID}/share", json={"ttl_days": 31})
        assert r.status_code == 422

    def test_share_create_ttl_zero_rejected(self):
        with patch(f"{_DB}.fetch_one", return_value=_GOOD_RUN):
            client = _make_client(_USER_A)
            r = client.post(f"/v3/runs/{_RUN_ID}/share", json={"ttl_days": 0})
        assert r.status_code == 422


# ===========================================================================
# test_get_share_returns_public_shape_no_pii
# ===========================================================================
class TestGetShare:
    def _fetch_side_effect(self, query: str, params: tuple):
        """Route fetch_one calls by query content."""
        if "run_share_links" in query:
            return _GOOD_LINK
        if "pipeline_runs" in query:
            return _GOOD_RUN
        if "research_trails" in query:
            return _TRAIL
        return None

    def test_get_share_returns_public_shape_no_pii(self):
        with patch(f"{_DB}.fetch_one", side_effect=self._fetch_side_effect):
            client = _make_client()
            r = client.get(f"/share/{_TOKEN}")
        assert r.status_code == 200
        data = r.json()
        # Required public fields present
        assert "run_id" in data
        assert "query" in data
        assert "ranked_candidates" in data
        assert "phases" in data
        assert "expires_at" in data
        assert "expires_in_hours" in data
        # PII must NOT appear
        for forbidden in ("user_id", "created_by", "email", "password", "wallet",
                          "balance_ru", "ru_consumed", "idempotency_key"):
            assert forbidden not in data, f"PII field '{forbidden}' leaked in share response"
        # No grading fields
        assert "grade" not in data
        assert "grades" not in data

    # ===========================================================================
    # test_get_share_404_after_expiry
    # ===========================================================================
    def test_get_share_404_after_expiry(self):
        expired_link = {**_GOOD_LINK, "expires_at": _PAST}
        with patch(f"{_DB}.fetch_one", return_value=expired_link):
            client = _make_client()
            r = client.get(f"/share/{_TOKEN}")
        assert r.status_code == 404

    # ===========================================================================
    # test_get_share_404_after_revoke
    # ===========================================================================
    def test_get_share_404_after_revoke(self):
        revoked_link = {**_GOOD_LINK, "revoked_at": _PAST}
        with patch(f"{_DB}.fetch_one", return_value=revoked_link):
            client = _make_client()
            r = client.get(f"/share/{_TOKEN}")
        assert r.status_code == 404

    # ===========================================================================
    # test_get_share_404_for_nonexistent_token (same response as expired — info-leak prevention)
    # ===========================================================================
    def test_get_share_404_for_nonexistent_token(self):
        with patch(f"{_DB}.fetch_one", return_value=None):
            client = _make_client()
            r = client.get("/share/does-not-exist")
        assert r.status_code == 404
        # Must NOT distinguish between "invalid", "expired", or "revoked"
        assert r.json().get("detail") == "Not found"


# ===========================================================================
# test_share_revoke_sets_revoked_at_idempotent
# ===========================================================================
class TestRevokeShare:
    def test_share_revoke_sets_revoked_at_idempotent(self):
        """Revoking a token (even twice) returns 204 and does not error."""
        link_owned = {
            "token": _TOKEN,
            "run_id": uuid.UUID(_RUN_ID),
            "created_by": uuid.UUID(_USER_A),
        }
        with (
            patch(f"{_DB}.fetch_one", return_value=link_owned),
            patch(f"{_DB}.execute") as mock_exec,
        ):
            client = _make_client(_USER_A)
            r = client.delete(f"/v3/runs/{_RUN_ID}/share/{_TOKEN}")
        assert r.status_code == 204
        # execute called with UPDATE ... SET revoked_at
        call_sql = mock_exec.call_args[0][0]
        assert "revoked_at" in call_sql.lower()
        assert "revoked_at IS NULL" in call_sql  # idempotent guard

    def test_share_revoke_403_for_non_owner(self):
        link_owned_by_a = {
            "token": _TOKEN,
            "run_id": uuid.UUID(_RUN_ID),
            "created_by": uuid.UUID(_USER_A),
        }
        with patch(f"{_DB}.fetch_one", return_value=link_owned_by_a):
            client = _make_client(_USER_B)
            r = client.delete(f"/v3/runs/{_RUN_ID}/share/{_TOKEN}")
        assert r.status_code == 403

    def test_share_revoke_404_for_missing_token(self):
        with patch(f"{_DB}.fetch_one", return_value=None):
            client = _make_client(_USER_A)
            r = client.delete(f"/v3/runs/{_RUN_ID}/share/bogus")
        assert r.status_code == 404
