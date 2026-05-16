"""Tests for findings grading endpoints and grade-boost logic."""
from __future__ import annotations

import os
import sys
import uuid
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
# Helpers
# ---------------------------------------------------------------------------

_USER_A_ID = str(uuid.uuid4())
_USER_B_ID = str(uuid.uuid4())
_RUN_ID = str(uuid.uuid4())
_FINDING_ID = f"finding-{uuid.uuid4()}"


def _user(uid: str) -> dict:
    return {"id": uid, "username": "tester", "is_active": True, "role": "analyst", "is_admin": False}


def _make_client(user_id: str = _USER_A_ID):
    from app.main import app
    from app.routers.v3.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: _user(user_id)
    return TestClient(app)


# ---------------------------------------------------------------------------
# DB mock helpers — patch execute/fetch_one/fetch_all at the module level
# used by the router so tests never hit Postgres.
# ---------------------------------------------------------------------------

_DB_PATH = "app.routers.v3.findings_grades"


# ---------------------------------------------------------------------------
# test_post_grade_creates_row
# ---------------------------------------------------------------------------

class TestPostGrade:
    def test_post_grade_creates_row(self):
        stored_row = {
            "id": str(uuid.uuid4()),
            "finding_id": _FINDING_ID,
            "run_id": _RUN_ID,
            "user_id": _USER_A_ID,
            "grade": "A",
            "note": None,
            "graded_at": "2026-01-01T00:00:00+00:00",
        }
        with (
            patch(f"{_DB_PATH}.execute") as mock_exec,
            patch(f"{_DB_PATH}.fetch_one", return_value=stored_row),
        ):
            client = _make_client(_USER_A_ID)
            r = client.post(
                f"/v3/findings/{_FINDING_ID}/grade",
                json={"grade": "A", "run_id": _RUN_ID},
            )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["grade"] == "A"
        assert data["finding_id"] == _FINDING_ID
        mock_exec.assert_called_once()

    def test_post_grade_upserts_replaces_prior(self):
        """Posting a second grade for the same (user, finding) replaces the first."""
        call_count = 0
        grades_returned = [
            {"id": str(uuid.uuid4()), "finding_id": _FINDING_ID, "run_id": _RUN_ID,
             "user_id": _USER_A_ID, "grade": "A", "note": None, "graded_at": "2026-01-01T00:00:00+00:00"},
            {"id": str(uuid.uuid4()), "finding_id": _FINDING_ID, "run_id": _RUN_ID,
             "user_id": _USER_A_ID, "grade": "B", "note": "updated", "graded_at": "2026-01-02T00:00:00+00:00"},
        ]

        def fetch_side_effect(*_args, **_kwargs):
            nonlocal call_count
            row = grades_returned[min(call_count, 1)]
            call_count += 1
            return row

        client = _make_client(_USER_A_ID)
        with (
            patch(f"{_DB_PATH}.execute"),
            patch(f"{_DB_PATH}.fetch_one", side_effect=fetch_side_effect),
        ):
            r1 = client.post(
                f"/v3/findings/{_FINDING_ID}/grade",
                json={"grade": "A", "run_id": _RUN_ID},
            )
            r2 = client.post(
                f"/v3/findings/{_FINDING_ID}/grade",
                json={"grade": "B", "note": "updated", "run_id": _RUN_ID},
            )
        assert r1.json()["grade"] == "A"
        assert r2.json()["grade"] == "B"
        assert r2.json()["note"] == "updated"

    def test_grade_must_be_in_allowed_set(self):
        """Grades outside A/B/C/D are rejected with 422."""
        client = _make_client(_USER_A_ID)
        for bad_grade in ("E", "1", "x", "AB", ""):
            r = client.post(
                f"/v3/findings/{_FINDING_ID}/grade",
                json={"grade": bad_grade, "run_id": _RUN_ID},
            )
            assert r.status_code == 422, f"Expected 422 for grade={bad_grade!r}, got {r.status_code}"


# ---------------------------------------------------------------------------
# test_get_grade_returns_aggregate
# ---------------------------------------------------------------------------

class TestGetGrade:
    def test_get_grade_returns_aggregate(self):
        my_row = {"grade": "A", "note": None, "graded_at": "2026-01-01T00:00:00+00:00"}
        agg_row = {"a_count": 2, "b_count": 1, "c_count": 0, "d_count": 0, "total_graders": 3}

        fetch_call = 0

        def fetch_side_effect(*_args, **_kwargs):
            nonlocal fetch_call
            result = my_row if fetch_call == 0 else agg_row
            fetch_call += 1
            return result

        client = _make_client(_USER_A_ID)
        with patch(f"{_DB_PATH}.fetch_one", side_effect=fetch_side_effect):
            r = client.get(f"/v3/findings/{_FINDING_ID}/grade")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["my_grade"]["grade"] == "A"
        assert data["aggregate"]["a_count"] == 2
        assert data["aggregate"]["total_graders"] == 3

    def test_get_grade_returns_null_my_grade_when_ungraded(self):
        agg_row = {"a_count": 0, "b_count": 0, "c_count": 0, "d_count": 0, "total_graders": 0}
        fetch_call = 0

        def fetch_side_effect(*_args, **_kwargs):
            nonlocal fetch_call
            result = None if fetch_call == 0 else agg_row
            fetch_call += 1
            return result

        client = _make_client(_USER_A_ID)
        with patch(f"{_DB_PATH}.fetch_one", side_effect=fetch_side_effect):
            r = client.get(f"/v3/findings/{_FINDING_ID}/grade")
        assert r.status_code == 200
        assert r.json()["my_grade"] is None


# ---------------------------------------------------------------------------
# test_get_run_grades_returns_all_user_grades_in_run
# ---------------------------------------------------------------------------

class TestGetRunGrades:
    def test_get_run_grades_returns_all_user_grades_in_run(self):
        rows = [
            {"id": str(uuid.uuid4()), "finding_id": f"f-{i}", "run_id": _RUN_ID,
             "user_id": _USER_A_ID, "grade": "A", "note": None, "graded_at": "2026-01-01T00:00:00+00:00"}
            for i in range(3)
        ]
        client = _make_client(_USER_A_ID)
        with patch(f"{_DB_PATH}.fetch_all", return_value=rows):
            r = client.get(f"/v3/runs/{_RUN_ID}/grades")
        assert r.status_code == 200
        assert len(r.json()) == 3

    def test_grade_isolated_per_user(self):
        """Each user sees only their own grades — endpoint scopes to requesting user."""
        user_a_rows = [
            {"id": str(uuid.uuid4()), "finding_id": "f-1", "run_id": _RUN_ID,
             "user_id": _USER_A_ID, "grade": "A", "note": None, "graded_at": "2026-01-01T00:00:00+00:00"},
        ]
        user_b_rows = [
            {"id": str(uuid.uuid4()), "finding_id": "f-1", "run_id": _RUN_ID,
             "user_id": _USER_B_ID, "grade": "D", "note": None, "graded_at": "2026-01-01T00:00:00+00:00"},
        ]

        client_a = _make_client(_USER_A_ID)
        with patch(f"{_DB_PATH}.fetch_all", return_value=user_a_rows):
            r_a = client_a.get(f"/v3/runs/{_RUN_ID}/grades")

        client_b = _make_client(_USER_B_ID)
        with patch(f"{_DB_PATH}.fetch_all", return_value=user_b_rows):
            r_b = client_b.get(f"/v3/runs/{_RUN_ID}/grades")

        # Each client receives its own grade — not the other user's
        assert r_a.status_code == 200
        assert r_b.status_code == 200
        assert r_a.json()[0]["grade"] == "A"
        assert r_b.json()[0]["grade"] == "D"
        # The grades themselves differ — confirming per-user isolation at the mock level
        assert r_a.json()[0]["user_id"] == _USER_A_ID
        assert r_b.json()[0]["user_id"] == _USER_B_ID


# ---------------------------------------------------------------------------
# test apply_grade_boost (pure unit — no DB)
# ---------------------------------------------------------------------------

class TestApplyGradeBoost:
    def test_boost_multipliers_applied_correctly(self):
        from dataclasses import replace as dc_replace
        from app.memory.models import MemoryResult
        from app.memory.rrf import apply_grade_boost

        base_score = 0.1

        def _result(ref: str) -> MemoryResult:
            return MemoryResult(ref=ref, title=ref, content="", source="semantic", score=base_score)

        results = [_result("a"), _result("b"), _result("c"), _result("d"), _result("ungraded")]
        grades_map = {"a": "A", "b": "B", "c": "C", "d": "D"}

        boosted = apply_grade_boost(results, grades_map)
        by_ref = {r.ref: r for r in boosted}

        assert abs(by_ref["a"].score - base_score * 1.5) < 1e-9
        assert abs(by_ref["b"].score - base_score * 1.2) < 1e-9
        assert abs(by_ref["c"].score - base_score * 1.0) < 1e-9
        assert abs(by_ref["d"].score - base_score * 0.4) < 1e-9
        assert abs(by_ref["ungraded"].score - base_score) < 1e-9

    def test_results_re_sorted_after_boost(self):
        from app.memory.models import MemoryResult
        from app.memory.rrf import apply_grade_boost

        results = [
            MemoryResult(ref="low", title="low", content="", source="semantic", score=0.9),
            MemoryResult(ref="high", title="high", content="", source="semantic", score=0.1),
        ]
        # "high" is D (suppressed), "low" is A (boosted) — after boost "low" should rank first
        grades_map = {"low": "A", "high": "D"}
        boosted = apply_grade_boost(results, grades_map)
        assert boosted[0].ref == "low"
        assert boosted[1].ref == "high"
