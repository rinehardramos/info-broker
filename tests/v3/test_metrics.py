"""Tests for GET /v3/metrics/summary and /v3/metrics/runs.

These tests use dependency_overrides + fetch patches so they run without Postgres.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Stub heavy optional deps before any app import
sys.modules.setdefault("qdrant_client", MagicMock())
sys.modules.setdefault("qdrant_client.models", MagicMock())
os.environ.setdefault("INFO_BROKER_API_KEY", "test-secret-key")
os.environ.setdefault("POSTGRES_DB", "info_broker")
os.environ.setdefault("POSTGRES_USER", "user")
os.environ.setdefault("POSTGRES_PASSWORD", "password")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.routers.v3.auth import get_current_user  # noqa: E402

_USER = {"id": "u1", "org_id": "org-1"}

_RUN_STATS = {
    "total_runs": 10,
    "succeeded": 8,
    "failed": 2,
    "budget_exhausted": 0,
    "avg_latency_seconds": 45.2,
    "p50_latency_seconds": 38.0,
    "p95_latency_seconds": 120.5,
}


def _override_user():
    return _USER


# ---------------------------------------------------------------------------
# Summary endpoint
# ---------------------------------------------------------------------------


def test_summary_returns_correct_shape():
    app.dependency_overrides[get_current_user] = _override_user
    try:
        with patch("app.routers.v3.metrics.fetch_one", return_value=_RUN_STATS), \
             patch("app.routers.v3.metrics.fetch_all", return_value=[]):
            client = TestClient(app)
            resp = client.get("/v3/metrics/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "runs" in data
        assert "latency" in data
        assert "steps" in data
        assert "strategies" in data
        assert data["runs"]["total"] == 10
        assert data["runs"]["succeeded"] == 8
        assert data["runs"]["failed"] == 2
        assert data["runs"]["success_rate"] == 80.0
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_summary_latency_shape():
    app.dependency_overrides[get_current_user] = _override_user
    try:
        with patch("app.routers.v3.metrics.fetch_one", return_value=_RUN_STATS), \
             patch("app.routers.v3.metrics.fetch_all", return_value=[]):
            client = TestClient(app)
            resp = client.get("/v3/metrics/summary")
        assert resp.status_code == 200
        latency = resp.json()["latency"]
        assert latency["avg_seconds"] == 45.2
        assert latency["p50_seconds"] == 38.0
        assert latency["p95_seconds"] == 120.5
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_summary_handles_no_data():
    """When there are no runs, all numeric fields default to 0 and success_rate is 0."""
    app.dependency_overrides[get_current_user] = _override_user
    try:
        with patch("app.routers.v3.metrics.fetch_one", return_value=None), \
             patch("app.routers.v3.metrics.fetch_all", return_value=[]):
            client = TestClient(app)
            resp = client.get("/v3/metrics/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["runs"]["total"] == 0
        assert data["runs"]["success_rate"] == 0.0
        assert data["latency"]["avg_seconds"] == 0.0
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_summary_custom_days_param():
    partial_stats = dict(_RUN_STATS)
    app.dependency_overrides[get_current_user] = _override_user
    try:
        with patch("app.routers.v3.metrics.fetch_one", return_value=partial_stats), \
             patch("app.routers.v3.metrics.fetch_all", return_value=[]):
            client = TestClient(app)
            resp = client.get("/v3/metrics/summary?days=7")
        assert resp.status_code == 200
        assert resp.json()["period_days"] == 7
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_summary_budget_exhausted_field():
    stats = dict(_RUN_STATS, budget_exhausted=3)
    app.dependency_overrides[get_current_user] = _override_user
    try:
        with patch("app.routers.v3.metrics.fetch_one", return_value=stats), \
             patch("app.routers.v3.metrics.fetch_all", return_value=[]):
            client = TestClient(app)
            resp = client.get("/v3/metrics/summary")
        assert resp.status_code == 200
        assert resp.json()["runs"]["budget_exhausted"] == 3
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Run history endpoint
# ---------------------------------------------------------------------------


def test_run_history_returns_empty_list():
    app.dependency_overrides[get_current_user] = _override_user
    try:
        with patch("app.routers.v3.metrics.fetch_all", return_value=[]):
            client = TestClient(app)
            resp = client.get("/v3/metrics/runs")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_run_history_returns_rows():
    _rows = [
        {
            "id": "run-1",
            "status": "succeeded",
            "trigger_type": "agent_is",
            "query": "test query",
            "started_at": "2026-05-01T10:00:00",
            "finished_at": "2026-05-01T10:01:00",
            "duration_seconds": 60.0,
            "error_message": None,
        }
    ]
    app.dependency_overrides[get_current_user] = _override_user
    try:
        with patch("app.routers.v3.metrics.fetch_all", return_value=_rows):
            client = TestClient(app)
            resp = client.get("/v3/metrics/runs")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["status"] == "succeeded"
        assert rows[0]["duration_seconds"] == 60.0
    finally:
        app.dependency_overrides.pop(get_current_user, None)
