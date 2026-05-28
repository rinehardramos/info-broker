"""Real-PG integration tests for paginated GET /v3/auth/users.

Requires a live Postgres instance (POSTGRES_PORT=5433 by default).
Inserts 60 test users in an isolated prefix, verifies page-1/page-2
behaviour, then cleans up.
"""
from __future__ import annotations

import os
import uuid
import sys
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Point at the local dev DB (port 5433); keep other env stubs consistent.
# ---------------------------------------------------------------------------
os.environ.setdefault("INFO_BROKER_API_KEY", "test-secret-key")
os.environ.setdefault("POSTGRES_DB", "info_broker")
os.environ.setdefault("POSTGRES_USER", "user")
os.environ.setdefault("POSTGRES_PASSWORD", "password")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")

# Stub out qdrant (not needed for these tests)
sys.modules.setdefault("qdrant_client", MagicMock())
sys.modules.setdefault("qdrant_client.models", MagicMock())

from fastapi.testclient import TestClient  # noqa: E402
from app.routers.v3.db import execute, fetch_all  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.v3.auth import get_current_user  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ADMIN_USER = {
    "id": str(uuid.uuid4()),
    "username": "testadmin",
    "is_active": True,
    "role": "admin",
    "is_admin": True,
}

# Unique prefix so test rows don't collide with real users
_PREFIX = f"pgtest_{uuid.uuid4().hex[:8]}_"
_N = 60


@pytest.fixture(scope="module")
def db_users():
    """Insert 60 uniquely-prefixed test users; yield; delete them."""
    inserted_ids: list[str] = []
    for i in range(_N):
        uname = f"{_PREFIX}{i:03d}"
        email = f"{uname}@test.invalid"
        row = execute(
            """INSERT INTO ui_users (username, email, password_hash, is_active)
               VALUES (%s, %s, 'x', true)
               RETURNING id""",
            (uname, email),
        )
        # execute() may or may not return RETURNING rows; use fetch_all for safety
    # Fetch the inserted IDs
    rows = fetch_all(
        "SELECT id FROM ui_users WHERE username LIKE %s ORDER BY created_at",
        (f"{_PREFIX}%",),
    )
    inserted_ids = [str(r["id"]) for r in rows]
    yield inserted_ids
    # Cleanup
    execute(
        "DELETE FROM ui_users WHERE username LIKE %s",
        (f"{_PREFIX}%",),
    )


@pytest.fixture(scope="module")
def client():
    app.dependency_overrides[get_current_user] = lambda: ADMIN_USER
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestUsersPagination:
    def test_default_page_200(self, client, db_users):
        """GET /v3/auth/users returns 200 with paginated envelope."""
        r = client.get("/v3/auth/users")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data

    def test_page1_returns_50_items(self, client, db_users):
        """First page with page_size=50 should return exactly 50 items (we have >=60)."""
        r = client.get("/v3/auth/users?page=1&page_size=50")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert len(data["items"]) == 50
        # Total should include all test users plus any pre-existing users
        assert data["total"] >= _N

    def test_page2_contains_remaining_test_users(self, client, db_users):
        """When filtered by prefix, page 2 of page_size=50 should return exactly 10 items."""
        # Use search to isolate just our test users
        r1 = client.get(f"/v3/auth/users?page=1&page_size=50&search={_PREFIX}")
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["total"] == _N, f"Expected {_N} test users, got {d1['total']}"
        assert len(d1["items"]) == 50
        assert d1["total_pages"] == 2

        r2 = client.get(f"/v3/auth/users?page=2&page_size=50&search={_PREFIX}")
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert len(d2["items"]) == 10
        assert d2["total"] == _N

    def test_total_consistent_across_pages(self, client, db_users):
        """total field must be the same on both pages."""
        r1 = client.get("/v3/auth/users?page=1&page_size=50")
        r2 = client.get("/v3/auth/users?page=2&page_size=50")
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["total"] == r2.json()["total"]

    def test_search_filters_by_username(self, client, db_users):
        """search param should reduce results to matching users only."""
        r = client.get(f"/v3/auth/users?search={_PREFIX}&page=1&page_size=100")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == _N
        for item in data["items"]:
            assert _PREFIX in item["username"] or (item["email"] and _PREFIX in item["email"])

    def test_search_no_match_returns_empty(self, client, db_users):
        """search that matches nothing returns empty items and total=0."""
        r = client.get("/v3/auth/users?search=ZZZZ_IMPOSSIBLE_MATCH_9999")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["total_pages"] == 1

    def test_page_size_max_200(self, client, db_users):
        """page_size=200 should be accepted."""
        r = client.get("/v3/auth/users?page=1&page_size=200")
        assert r.status_code == 200

    def test_page_size_over_limit_rejected(self, client, db_users):
        """page_size=201 should be rejected with 422."""
        r = client.get("/v3/auth/users?page=1&page_size=201")
        assert r.status_code == 422

    def test_page_zero_rejected(self, client, db_users):
        """page=0 should be rejected with 422."""
        r = client.get("/v3/auth/users?page=0")
        assert r.status_code == 422

    def test_items_schema(self, client, db_users):
        """Each item in the response should have the expected fields."""
        r = client.get("/v3/auth/users?page=1&page_size=1")
        assert r.status_code == 200
        item = r.json()["items"][0]
        for field in ("id", "username", "is_admin", "role", "is_active", "created_at"):
            assert field in item, f"Missing field: {field}"
