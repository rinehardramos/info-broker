"""TDD tests for app.pipeline.reconcile — orphaned and stale run reconciliation."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.pipeline.reconcile import reconcile_orphaned_runs, sweep_stale_runs


class TestReconcileOrphanedRuns:
    """reconcile_orphaned_runs() marks running/queued manual runs as failed at startup."""

    def test_marks_running_manual_runs_as_failed(self):
        orphans = [{"id": "run-1"}, {"id": "run-2"}]
        with (
            patch("app.pipeline.reconcile.fetch_all", return_value=orphans) as mock_fetch,
            patch("app.pipeline.reconcile.execute") as mock_exec,
        ):
            count = reconcile_orphaned_runs()

        assert count == 2
        mock_fetch.assert_called_once()
        fetch_sql = mock_fetch.call_args[0][0]
        assert "running" in fetch_sql
        assert "queued" in fetch_sql
        assert "manual" in fetch_sql

        mock_exec.assert_called_once()
        update_sql = mock_exec.call_args[0][0]
        assert "failed" in update_sql
        assert "finished_at" in update_sql

    def test_returns_zero_when_no_orphans(self):
        with (
            patch("app.pipeline.reconcile.fetch_all", return_value=[]),
            patch("app.pipeline.reconcile.execute") as mock_exec,
        ):
            count = reconcile_orphaned_runs()

        assert count == 0
        mock_exec.assert_not_called()

    def test_marks_queued_manual_runs_as_failed(self):
        orphans = [{"id": "run-queued"}]
        with (
            patch("app.pipeline.reconcile.fetch_all", return_value=orphans),
            patch("app.pipeline.reconcile.execute") as mock_exec,
        ):
            count = reconcile_orphaned_runs()

        assert count == 1
        update_sql = mock_exec.call_args[0][0]
        assert "failed" in update_sql

    def test_does_not_touch_agent_is_runs(self):
        """agent_is runs have their own reconciliation path; manual should not overlap."""
        with (
            patch("app.pipeline.reconcile.fetch_all", return_value=[]) as mock_fetch,
            patch("app.pipeline.reconcile.execute"),
        ):
            reconcile_orphaned_runs()

        fetch_sql = mock_fetch.call_args[0][0]
        assert "agent_is" not in fetch_sql


class TestSweepStaleRuns:
    """sweep_stale_runs() marks manual runs running longer than max_age_minutes as failed."""

    def test_marks_runs_older_than_threshold_as_failed(self):
        with patch("app.pipeline.reconcile.execute") as mock_exec:
            sweep_stale_runs(max_age_minutes=60)

        mock_exec.assert_called_once()
        sql, params = mock_exec.call_args[0]
        assert "failed" in sql
        assert "finished_at" in sql
        assert "manual" in sql
        assert 60 in params

    def test_default_threshold_is_60_minutes(self):
        with patch("app.pipeline.reconcile.execute") as mock_exec:
            sweep_stale_runs()

        _, params = mock_exec.call_args[0]
        assert 60 in params

    def test_does_not_touch_agent_is_runs(self):
        with patch("app.pipeline.reconcile.execute") as mock_exec:
            sweep_stale_runs()

        sql, _ = mock_exec.call_args[0]
        assert "agent_is" not in sql

    def test_custom_threshold_is_applied(self):
        with patch("app.pipeline.reconcile.execute") as mock_exec:
            sweep_stale_runs(max_age_minutes=30)

        _, params = mock_exec.call_args[0]
        assert 30 in params
