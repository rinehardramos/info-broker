"""Verify the strategy/tactic audit runs at API lifespan startup.

These tests are deliberately sync (using asyncio.run internally) so they
don't depend on pytest-asyncio being installed — the production .venv is
built with `uv sync --no-dev` and dev-only test plugins are not available.
"""
import asyncio

import pytest


def test_lifespan_calls_run_audit_or_fail(monkeypatch):
    """Mock run_audit_or_fail and assert it's called at app startup."""
    from unittest.mock import MagicMock
    audit_mock = MagicMock()
    monkeypatch.setattr("app.pipeline.catalogs.audit.run_audit_or_fail", audit_mock)

    from app.main import app

    async def _exercise():
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(_exercise())
    # The audit must have been called at least once
    assert audit_mock.call_count >= 1


def test_lifespan_aborts_when_audit_fails(monkeypatch):
    """When the audit raises, lifespan startup must propagate (API does not start)."""
    from app.pipeline.catalogs.audit import StrategyTacticAuditError

    def _fail(*args, **kwargs):
        raise StrategyTacticAuditError("test failure")
    monkeypatch.setattr("app.pipeline.catalogs.audit.run_audit_or_fail", _fail)

    from app.main import app

    async def _exercise():
        async with app.router.lifespan_context(app):
            pass

    with pytest.raises(StrategyTacticAuditError):
        asyncio.run(_exercise())
