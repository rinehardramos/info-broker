"""Startup-time strategy gate audit.

Every CheckSpec.kind declared in any registered Strategy MUST exist in
the runtime's _GATE_CHECKS dict. Otherwise the strategist fail-opens at
strategist.py:303-306 ("Unknown gate check kind ... treating as pass") —
which means the strategy's gate is documentation, not enforcement, and
runs report success without doing any work (see issue: skeleton strategies
"succeeding" in 0.1s with 0 tool calls).

This module exposes `audit_strategy_gates(strategies, registered_kinds)`
that returns a list of (strategy_id, phase_id, unknown_kind) violations.
The app startup path calls it, logs at ERROR for every violation, and
optionally raises in strict mode.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.pipeline.catalogs.loader import load_catalog
from app.pipeline.catalogs.schemas import Strategy
from app.pipeline.strategist import _GATE_CHECKS, audit_strategy_gates


STRATEGIES_DIR = (
    Path(__file__).parent.parent / "catalogs" / "registries" / "strategies"
)


@pytest.fixture(scope="module")
def catalog() -> dict[str, Strategy]:
    return load_catalog("strategy", STRATEGIES_DIR)


# ---------------------------------------------------------------------------
# audit_strategy_gates contract
# ---------------------------------------------------------------------------


class TestAuditContract:
    def test_clean_strategy_returns_no_violations(self):
        """A strategy whose gates only reference registered kinds is clean."""
        strategies = {
            "x": _make_strategy_dict("x", [
                {"kind": "min_primary_signals", "params": {}},
            ]),
        }
        registered = {"min_primary_signals"}
        violations = audit_strategy_gates(strategies, registered)
        assert violations == []

    def test_unknown_kind_surfaces_as_violation(self):
        strategies = {
            "real_estate": _make_strategy_dict("real_estate", [
                {"kind": "min_listings_returned", "params": {"min": 1}},
            ]),
        }
        registered = {"min_primary_signals"}  # min_listings_returned NOT registered
        violations = audit_strategy_gates(strategies, registered)
        assert len(violations) == 1
        v = violations[0]
        assert v.strategy_id == "real_estate"
        assert v.unknown_kind == "min_listings_returned"

    def test_multiple_strategies_multiple_violations(self):
        strategies = {
            "a": _make_strategy_dict("a", [{"kind": "missing_a"}]),
            "b": _make_strategy_dict("b", [{"kind": "missing_b"}, {"kind": "min_primary_signals"}]),
        }
        registered = {"min_primary_signals"}
        violations = audit_strategy_gates(strategies, registered)
        kinds = sorted(v.unknown_kind for v in violations)
        assert kinds == ["missing_a", "missing_b"]

    def test_empty_gate_checks_is_not_a_violation(self):
        """A phase with empty gate.checks (always-passes) is a design choice,
        not an audit failure. The audit only flags UNKNOWN kinds, not absent."""
        strategies = {"x": _make_strategy_dict("x", [])}
        violations = audit_strategy_gates(strategies, {"min_primary_signals"})
        assert violations == []


# ---------------------------------------------------------------------------
# Real catalog — this is the regression bar
# ---------------------------------------------------------------------------


class TestAcceptsBothDictsAndPydanticObjects:
    """Regression: the lifespan audit path passes Strategy objects from
    load_catalog (Pydantic models), not raw dicts. An earlier helper
    impl assumed dicts and crashed on `gate.get(...)`.
    """
    def test_accepts_pydantic_strategy_objects(self):
        from app.pipeline.catalogs.schemas import Strategy
        strat = Strategy.model_validate(_make_strategy_dict("x", [
            {"kind": "missing_kind"},
        ]))
        violations = audit_strategy_gates({"x": strat}, registered_kinds={"min_primary_signals"})
        assert [v.unknown_kind for v in violations] == ["missing_kind"]

    def test_accepts_loaded_catalog(self, catalog):
        """The real catalog comes back as a dict[str, Strategy]. Audit
        must traverse it without AttributeError."""
        # Should not raise on real Pydantic Strategy objects.
        violations = audit_strategy_gates(catalog)
        # Whatever the result is, the call itself must succeed.
        assert isinstance(violations, list)


class TestRealCatalog:
    def test_all_registered_strategies_have_known_gate_kinds(self, catalog):
        """The crown jewel: every gate check kind declared in the real
        registries/strategies/*.py files must be implemented in _GATE_CHECKS.

        If this test fails, the strategy that mentions the unknown kind is
        broken-as-shipped — its gate auto-passes, runs report success with
        zero work done, and admins can't tell from the UI."""
        # The audit function expects raw dicts (matches load_catalog → Strategy
        # round-trip). The pydantic models expose .gate.checks[].kind directly.
        violations = []
        for sid, s in catalog.items():
            for phase in s.phases:
                for check in phase.gate.checks:
                    if check.kind not in _GATE_CHECKS:
                        violations.append((sid, phase.id, check.kind))
        # Pretty failure message — admin reading the CI output needs to know
        # WHICH strategy is broken and WHICH kind is missing.
        if violations:
            lines = ["Unknown gate check kinds (fail-open runtime risk):"]
            for sid, pid, kind in violations:
                lines.append(f"  - {sid}.{pid}: kind={kind!r}")
            lines.append(f"\nRegistered kinds: {sorted(_GATE_CHECKS)}")
            pytest.fail("\n".join(lines))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strategy_dict(id: str, broaden_checks: list) -> dict:
    """Minimal valid Strategy dict for the audit (Pydantic-validated)."""
    return {
        "id": id,
        "ach_signals": [{"id": "s", "label": "s", "weight": 1.0, "penalty_on_mismatch": 0.1}],
        "applies_to": {},
        "default_mode": "quick_lookup",
        "budget_minimums": {"hypothesis_count": "single"},
        "phases": [
            {
                "id": "broaden",
                "depends_on": [],
                "unit_of_work_contract": {"inputs": [], "briefing": "test"},
                "hypothesis_count_policy": "fixed:1",
                "gate": {"checks": broaden_checks, "on_fail": "ask_user"},
            },
        ],
    }
