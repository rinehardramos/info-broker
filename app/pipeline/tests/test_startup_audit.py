"""Tests for app.pipeline.catalogs.audit.

Per spec §"Implementation ordering constraints", the audit module exists
but the invocation in app/main.py is wired separately (Task 13). These
tests exercise the audit function directly with constructed catalogs.
"""
import pytest
from app.pipeline.catalogs.audit import (
    audit_strategy_tactic_alignment,
    StrategyTacticAuditError,
)


def _stub_tactic(tid: str, phase_compat: list[str]):
    """Build a minimal stub object that has `.id` and `.phase_compatibility`."""
    class _T:
        id = tid
        phase_compatibility = phase_compat
    return _T()


def _stub_strategy(sid: str, phases: list[dict]):
    """Build a minimal stub strategy with `.id` and `.phases` (list of stubs)."""
    class _P:
        def __init__(self, d):
            self.id = d["id"]
            self.preferred_tactic_id = d.get("preferred_tactic_id")
    class _S:
        id = sid
        def __init__(self):
            self.phases = [_P(p) for p in phases]
    return _S()


def test_audit_passes_on_clean_catalog():
    """Empty-error list when every strategy phase has a compatible tactic."""
    strategies = {
        "s1": _stub_strategy("s1", [{"id": "extract"}, {"id": "gather"}]),
    }
    tactics = {
        "extract_default": _stub_tactic("extract_default", ["extract"]),
        "gather_default": _stub_tactic("gather_default", ["gather"]),
    }
    errors = audit_strategy_tactic_alignment(strategies, tactics)
    assert errors == []


def test_audit_fails_when_strategy_phase_has_no_compatible_tactic():
    strategies = {
        "s1": _stub_strategy("s1", [{"id": "extract"}, {"id": "gather"}]),
    }
    tactics = {
        "extract_default": _stub_tactic("extract_default", ["extract"]),
        # No gather-compatible tactic
    }
    errors = audit_strategy_tactic_alignment(strategies, tactics)
    assert len(errors) == 1
    assert "s1" in errors[0]
    assert "gather" in errors[0]
    assert "zero compatible tactics" in errors[0]


def test_audit_fails_when_preferred_tactic_id_is_not_compatible():
    strategies = {
        "s1": _stub_strategy("s1", [
            {"id": "gather", "preferred_tactic_id": "listings_gather"},
        ]),
    }
    tactics = {
        "gather_default": _stub_tactic("gather_default", ["gather"]),
        # listings_gather is registered but for a different phase
        "listings_gather": _stub_tactic("listings_gather", ["extract"]),
    }
    errors = audit_strategy_tactic_alignment(strategies, tactics)
    assert len(errors) == 1
    assert "listings_gather" in errors[0]
    assert "not in the compatible set" in errors[0]


def test_audit_fails_when_tactic_declares_legacy_phase_id():
    strategies = {}
    tactics = {
        "legacy_tactic": _stub_tactic("legacy_tactic", ["broaden"]),
    }
    errors = audit_strategy_tactic_alignment(strategies, tactics)
    assert len(errors) == 1
    assert "broaden" in errors[0]
    assert "illegal" in errors[0].lower() or "legal:" in errors[0].lower()


def test_audit_error_includes_strategy_id_phase_id_and_compatible_set():
    """Error messages must be operator-actionable."""
    strategies = {
        "real_estate": _stub_strategy("real_estate", [
            {"id": "gather", "preferred_tactic_id": "listings_gather"},
        ]),
    }
    tactics = {
        "gather_default": _stub_tactic("gather_default", ["gather"]),
        "listings_gather": _stub_tactic("listings_gather", ["extract"]),
    }
    errors = audit_strategy_tactic_alignment(strategies, tactics)
    assert any("real_estate" in e for e in errors)
    assert any("gather" in e for e in errors)
    # Compatible set should be listed for operator hint
    assert any("gather_default" in e for e in errors)


def test_audit_error_class_extends_runtime_error():
    """StrategyTacticAuditError must be a RuntimeError so existing handlers see it."""
    assert issubclass(StrategyTacticAuditError, RuntimeError)
