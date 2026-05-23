"""Unit tests for app/pipeline/catalogs (MVP-M2).

Tests cover:
- Schema happy-path validation (Strategy, PhaseSpec, GateSpec, CheckSpec,
  Tactic, TaskSpec, Technique, OptimizationMode)
- Schema rejection on missing required fields
- Dependency-cycle detection in Strategy.phases
- Loader discovery across a temp directory
- BudgetEnvelope dial validation
- default_envelope() dial defaults
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.pipeline.catalogs.budget import (
    DEPTH_LEVELS,
    HYPOTHESIS_COUNT_LEVELS,
    BudgetEnvelope,
    default_envelope,
)
from app.pipeline.catalogs.loader import CatalogValidationError, load_catalog
from app.pipeline.catalogs.schemas import (
    CheckSpec,
    GateSpec,
    OptimizationMode,
    PhaseSpec,
    Strategy,
    TaskSpec,
    Tactic,
    Technique,
)


# ---------------------------------------------------------------------------
# Fixtures — minimal valid dicts
# ---------------------------------------------------------------------------


def _gate() -> dict:
    return {
        "checks": [{"kind": "distinct_identity_count", "params": {"min": 3}}],
        "on_fail": "replan",
    }


def _phase(pid: str, depends_on: list[str] | None = None) -> dict:
    return {
        "id": pid,
        "depends_on": depends_on or [],
        "unit_of_work_contract": {"objective": "find candidates"},
        "hypothesis_count_policy": "from_dial",
        "gate": _gate(),
    }


def _valid_strategy() -> dict:
    return {
        "id": "media_identification",
        "applies_to": {"entity_type": "media", "query_type": "identification"},
        "phases": [
            _phase("gather"),
            _phase("disconfirm", depends_on=["gather"]),
            _phase("synthesize", depends_on=["disconfirm"]),
        ],
        "default_mode": "investigation",
        "budget_minimums": {"depth": "search", "hypothesis_count": "competing"},
    }


def _valid_tactic() -> dict:
    return {
        "id": "hypothesis_first_search",
        "phase_compatibility": ["gather"],
        "accepts": {"objective": "str", "scope_in": "list"},
        "produces": [
            {
                "technique_id": "web_search",
                "params_template": {"query": "{hypothesis}"},
                "expect_schema": {"results": "list"},
                "fail_modes": ["no_results"],
                "budget_ru": 2,
            }
        ],
        "cost_class": "cheap",
        "required_techniques": ["web_search"],
        "enforcement": {"min_distinct_outputs": 3},
    }


def _valid_technique() -> dict:
    return {
        "id": "web_search",
        "tool_name": "run_web_search",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"results": {"type": "array"}}},
        "cost_class": "cheap",
        "failure_modes": ["no_results", "rate_limited"],
        "retry_policy": {"max_retries": 2, "backoff_s": 1},
    }


def _valid_mode() -> dict:
    return {
        "id": "investigation",
        "dial_defaults": {
            "speed": "slow",
            "capability": "high",
            "resource": "heavy",
            "depth": "deep",
            "hypothesis_count": "adversarial",
        },
        "tactic_bias": {"hypothesis_first_search": 1.5, "disconfirm_default": 1.2},
        "strategy_suggestions": ["media_identification", "person"],
    }


# ---------------------------------------------------------------------------
# Strategy schema tests
# ---------------------------------------------------------------------------


class TestStrategySchema:
    def test_strategy_schema_valid(self):
        s = Strategy.model_validate(_valid_strategy())
        assert s.id == "media_identification"
        assert len(s.phases) == 3
        assert s.phases[0].id == "gather"

    def test_strategy_schema_rejects_missing_phases(self):
        data = _valid_strategy()
        data["phases"] = []
        with pytest.raises(Exception):  # ValidationError wraps ValueError
            Strategy.model_validate(data)

    def test_strategy_schema_rejects_missing_id(self):
        data = _valid_strategy()
        del data["id"]
        with pytest.raises(Exception):
            Strategy.model_validate(data)

    def test_phase_dependency_cycle_rejected(self):
        """A → B → A cycle must be caught at schema validation time."""
        data = _valid_strategy()
        data["phases"] = [
            _phase("gather", depends_on=["disconfirm"]),
            _phase("disconfirm", depends_on=["gather"]),
        ]
        with pytest.raises(Exception, match="cycle"):
            Strategy.model_validate(data)

    def test_phase_unknown_dependency_rejected(self):
        data = _valid_strategy()
        data["phases"] = [_phase("gather", depends_on=["nonexistent"])]
        with pytest.raises(Exception):
            Strategy.model_validate(data)

    def test_phase_self_loop_rejected(self):
        data = _valid_strategy()
        data["phases"] = [_phase("gather", depends_on=["gather"])]
        with pytest.raises(Exception):
            Strategy.model_validate(data)

    def test_gate_on_fail_literal_validated(self):
        data = _valid_strategy()
        data["phases"][0]["gate"]["on_fail"] = "invalid_action"
        with pytest.raises(Exception):
            Strategy.model_validate(data)


# ---------------------------------------------------------------------------
# Tactic / TaskSpec schema tests
# ---------------------------------------------------------------------------


class TestTacticSchema:
    def test_tactic_schema_valid(self):
        t = Tactic.model_validate(_valid_tactic())
        assert t.id == "hypothesis_first_search"
        assert t.cost_class == "cheap"
        assert len(t.produces) == 1
        assert t.produces[0].technique_id == "web_search"

    def test_tactic_cost_class_validated(self):
        data = _valid_tactic()
        data["cost_class"] = "free"
        with pytest.raises(Exception):
            Tactic.model_validate(data)


# ---------------------------------------------------------------------------
# Technique schema tests
# ---------------------------------------------------------------------------


class TestTechniqueSchema:
    def test_technique_schema_valid(self):
        t = Technique.model_validate(_valid_technique())
        assert t.id == "web_search"
        assert t.tool_name == "run_web_search"


# ---------------------------------------------------------------------------
# OptimizationMode schema tests
# ---------------------------------------------------------------------------


class TestOptimizationModeSchema:
    def test_mode_schema_valid(self):
        m = OptimizationMode.model_validate(_valid_mode())
        assert m.id == "investigation"
        assert m.tactic_bias["hypothesis_first_search"] == 1.5

    def test_mode_defaults_to_empty_bias(self):
        data = {"id": "quick_lookup", "dial_defaults": {"speed": "fast"}}
        m = OptimizationMode.model_validate(data)
        assert m.tactic_bias == {}
        assert m.strategy_suggestions == []


# ---------------------------------------------------------------------------
# BudgetEnvelope tests
# ---------------------------------------------------------------------------


class TestBudgetEnvelope:
    def test_default_envelope_dials(self):
        env = default_envelope()
        assert env.speed == "normal"
        assert env.capability == "general"
        assert env.resource == "medium"
        assert env.depth == "search"
        assert env.hypothesis_count == "competing"

    def test_budget_envelope_rejects_invalid_dial_value(self):
        with pytest.raises(ValueError, match="speed"):
            BudgetEnvelope(speed="turbo")

    def test_budget_envelope_rejects_invalid_capability(self):
        with pytest.raises(ValueError, match="capability"):
            BudgetEnvelope(capability="extreme")

    def test_budget_envelope_rejects_invalid_depth(self):
        with pytest.raises(ValueError, match="depth"):
            BudgetEnvelope(depth="infinite")

    def test_budget_envelope_rejects_invalid_hypothesis_count(self):
        with pytest.raises(ValueError, match="hypothesis_count"):
            BudgetEnvelope(hypothesis_count="many")

    def test_budget_envelope_accepts_all_speed_levels(self):
        from app.pipeline.catalogs.budget import SPEED_LEVELS
        for level in SPEED_LEVELS:
            env = BudgetEnvelope(speed=level)
            assert env.speed == level

    def test_budget_envelope_as_dict_returns_five_dials(self):
        env = default_envelope()
        d = env.as_dict()
        assert set(d.keys()) == {"speed", "capability", "resource", "depth", "hypothesis_count"}

    def test_budget_envelope_cu_ceiling_default(self):
        env = default_envelope()
        assert env.cu_ceiling == 500

    def test_budget_envelope_wall_clock_default(self):
        env = default_envelope()
        assert env.wall_clock_s == 1800


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------


class TestLoader:
    def test_loader_discovers_modules(self, tmp_path: Path):
        """Valid strategy module is discovered and returned by id.

        An invalid module (empty phases) in a separate dir raises CatalogValidationError.
        The two cases are kept in separate directories so sorted discovery order
        doesn't cause the invalid module to raise before the valid one is tested.
        """
        # --- valid-only directory -------------------------------------------
        valid_dir = tmp_path / "valid_only"
        valid_dir.mkdir()
        valid_module = valid_dir / "valid_strategy.py"
        valid_module.write_text(
            textwrap.dedent(
                """\
                STRATEGY = {
                    "id": "test_strategy",
                    "applies_to": {"entity_type": "test"},
                    "phases": [
                        {
                            "id": "gather",
                            "depends_on": [],
                            "unit_of_work_contract": {"objective": "find things"},
                            "hypothesis_count_policy": "from_dial",
                            "gate": {
                                "checks": [{"kind": "min_results", "params": {"min": 1}}],
                                "on_fail": "terminate",
                            },
                        }
                    ],
                    "default_mode": "investigation",
                    "budget_minimums": {"depth": "shallow"},
                }
                """
            )
        )
        catalog = load_catalog("strategy", valid_dir)
        assert "test_strategy" in catalog
        assert catalog["test_strategy"].id == "test_strategy"

        # --- invalid-only directory -----------------------------------------
        invalid_dir = tmp_path / "invalid_only"
        invalid_dir.mkdir()
        invalid_module = invalid_dir / "invalid_strategy.py"
        invalid_module.write_text(
            textwrap.dedent(
                """\
                STRATEGY = {
                    "id": "bad_strategy",
                    "applies_to": {},
                    "phases": [],
                    "default_mode": "investigation",
                    "budget_minimums": {},
                }
                """
            )
        )
        with pytest.raises(CatalogValidationError):
            load_catalog("strategy", invalid_dir)

    def test_loader_raises_on_invalid_module(self, tmp_path: Path):
        bad = tmp_path / "bad.py"
        bad.write_text(
            textwrap.dedent(
                """\
                STRATEGY = {
                    "id": "broken",
                    "applies_to": {},
                    "phases": [],          # empty phases → validation error
                    "default_mode": "x",
                    "budget_minimums": {},
                }
                """
            )
        )
        with pytest.raises(CatalogValidationError) as exc_info:
            load_catalog("strategy", tmp_path)
        assert exc_info.value.file == bad

    def test_loader_skips_files_without_constant(self, tmp_path: Path):
        helper = tmp_path / "helpers.py"
        helper.write_text("def util(): pass\n")
        catalog = load_catalog("strategy", tmp_path)
        assert catalog == {}

    def test_loader_skips_init_files(self, tmp_path: Path):
        init = tmp_path / "__init__.py"
        init.write_text("# init\n")
        catalog = load_catalog("tactic", tmp_path)
        assert catalog == {}

    def test_loader_empty_dir_returns_empty_dict(self, tmp_path: Path):
        catalog = load_catalog("technique", tmp_path)
        assert catalog == {}

    def test_loader_nonexistent_dir_returns_empty_dict(self, tmp_path: Path):
        catalog = load_catalog("mode", tmp_path / "nonexistent")
        assert catalog == {}

    def test_loader_rejects_unknown_kind(self, tmp_path: Path):
        with pytest.raises(ValueError, match="Unknown catalog kind"):
            load_catalog("unknown_kind", tmp_path)  # type: ignore[arg-type]
