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


def test_default_tactics_exist_with_correct_phase_compatibility():
    """All 4 default tactics are importable and declare the right phases."""
    from app.pipeline.catalogs.registries.tactics.extract_default import TACTIC as EXTRACT
    from app.pipeline.catalogs.registries.tactics.gather_default import TACTIC as GATHER
    from app.pipeline.catalogs.registries.tactics.disconfirm_default import TACTIC as DISCONFIRM
    from app.pipeline.catalogs.registries.tactics.synthesize_default import TACTIC as SYNTHESIZE

    from app.pipeline.catalogs.audit import _get_phase_compatibility

    assert _get_phase_compatibility(EXTRACT) == ["extract"]
    assert _get_phase_compatibility(GATHER) == ["gather"]
    assert _get_phase_compatibility(DISCONFIRM) == ["disconfirm"]
    assert _get_phase_compatibility(SYNTHESIZE) == ["synthesize"]


def test_extract_default_requires_no_techniques():
    """extract phase is pure analysis — no tool calls."""
    from app.pipeline.catalogs.registries.tactics.extract_default import TACTIC
    required = TACTIC.required_techniques if hasattr(TACTIC, "required_techniques") else TACTIC.get("required_techniques", [])
    assert required == []


def test_synthesize_default_requires_no_techniques():
    from app.pipeline.catalogs.registries.tactics.synthesize_default import TACTIC
    required = TACTIC.required_techniques if hasattr(TACTIC, "required_techniques") else TACTIC.get("required_techniques", [])
    assert required == []


def test_gather_default_uses_web_search_and_google_news():
    from app.pipeline.catalogs.registries.tactics.gather_default import TACTIC
    required = TACTIC.required_techniques if hasattr(TACTIC, "required_techniques") else TACTIC.get("required_techniques", [])
    assert set(required) == {"web_search", "google_news"}


def test_listings_gather_tactic_registered():
    from app.pipeline.catalogs.registries.tactics.listings_gather import TACTIC
    from app.pipeline.catalogs.audit import _get_phase_compatibility
    assert _get_phase_compatibility(TACTIC) == ["gather"]
    required = TACTIC.required_techniques if hasattr(TACTIC, "required_techniques") else TACTIC.get("required_techniques", [])
    assert required == ["apify_listings_search"]


def test_apify_listings_search_technique_registered():
    from app.pipeline.catalogs.registries.techniques.apify_listings_search import TECHNIQUE
    actor_slug = TECHNIQUE.get("actor_slug") if isinstance(TECHNIQUE, dict) else getattr(TECHNIQUE, "actor_slug", None)
    assert actor_slug == "apify/zillow-search-scraper"


def test_listings_gather_uses_expensive_cost_class():
    """Apify calls are paid — cost_class must signal that to the budget layer."""
    from app.pipeline.catalogs.registries.tactics.listings_gather import TACTIC
    cost_class = TACTIC.cost_class if hasattr(TACTIC, "cost_class") else TACTIC.get("cost_class")
    assert cost_class == "expensive"


def test_phasespec_preferred_tactic_id_field_optional_and_defaults_none():
    """PhaseSpec accepts None / valid string; defaults to None when omitted."""
    from app.pipeline.catalogs.schemas import PhaseSpec, GateSpec, CheckSpec

    gate = GateSpec(checks=[CheckSpec(kind="min_primary_signals", params={"min": 1})], on_fail="ask_user")

    # Omitted entirely → None
    p1 = PhaseSpec(
        id="extract",
        unit_of_work_contract={},
        hypothesis_count_policy="fixed:1",
        gate=gate,
    )
    assert p1.preferred_tactic_id is None

    # Explicit None
    p2 = PhaseSpec(
        id="gather",
        unit_of_work_contract={},
        hypothesis_count_policy="fixed:1",
        gate=gate,
        preferred_tactic_id=None,
    )
    assert p2.preferred_tactic_id is None

    # Valid string
    p3 = PhaseSpec(
        id="gather",
        unit_of_work_contract={},
        hypothesis_count_policy="fixed:1",
        gate=gate,
        preferred_tactic_id="listings_gather",
    )
    assert p3.preferred_tactic_id == "listings_gather"


def test_phasespec_preferred_tactic_id_format_validator_rejects_empty():
    """Empty / whitespace-only strings are rejected by the format validator."""
    from app.pipeline.catalogs.schemas import PhaseSpec, GateSpec, CheckSpec
    from pydantic import ValidationError

    gate = GateSpec(checks=[CheckSpec(kind="min_primary_signals", params={"min": 1})], on_fail="ask_user")

    with pytest.raises(ValidationError):
        PhaseSpec(
            id="gather",
            unit_of_work_contract={},
            hypothesis_count_policy="fixed:1",
            gate=gate,
            preferred_tactic_id="   ",
        )


def test_phasespec_preferred_tactic_id_strips_whitespace():
    """Surrounding whitespace is stripped, content preserved."""
    from app.pipeline.catalogs.schemas import PhaseSpec, GateSpec, CheckSpec
    gate = GateSpec(checks=[CheckSpec(kind="min_primary_signals", params={"min": 1})], on_fail="ask_user")
    p = PhaseSpec(
        id="gather",
        unit_of_work_contract={},
        hypothesis_count_policy="fixed:1",
        gate=gate,
        preferred_tactic_id="  listings_gather  ",
    )
    assert p.preferred_tactic_id == "listings_gather"


def test_apify_listings_search_loads_through_catalog_loader():
    """The technique passes Pydantic validation when loaded via the catalog loader.

    Regression test for the BLOCKER found in Task 3 review (commit 3861b2d):
    missing output_schema caused CatalogValidationError at startup.
    """
    from app.pipeline.catalogs.loader import load_catalog
    from pathlib import Path
    techniques_dir = Path(__file__).resolve().parents[2] / "pipeline" / "catalogs" / "registries" / "techniques"
    techniques = load_catalog("technique", techniques_dir)
    assert "apify_listings_search" in techniques
    t = techniques["apify_listings_search"]
    assert (t.id if hasattr(t, "id") else t.get("id")) == "apify_listings_search"
    # Verify actor_slug survived Pydantic validation (was silently dropped before schema fix)
    assert t.actor_slug == "apify/zillow-search-scraper"
    # Verify schemas are proper JSON Schema dicts (not prose strings)
    assert isinstance(t.input_schema, dict)
    assert t.input_schema.get("type") == "object"
    assert isinstance(t.output_schema, dict)
    assert t.output_schema.get("type") == "object"


def test_real_estate_gather_uses_listings_gather():
    """The real_estate strategy declares preferred_tactic_id='listings_gather' on its gather phase."""
    from app.pipeline.catalogs.registries.strategies.real_estate import STRATEGY
    gather_phase = next(p for p in STRATEGY["phases"] if p["id"] == "gather")
    assert gather_phase.get("preferred_tactic_id") == "listings_gather"


def test_hypothesis_first_search_phase_compat_migrated_to_gather():
    from app.pipeline.catalogs.registries.tactics.hypothesis_first_search import TACTIC
    from app.pipeline.catalogs.audit import _get_phase_compatibility
    assert _get_phase_compatibility(TACTIC) == ["gather"]


def test_prior_research_seed_phase_compat_migrated_to_gather():
    from app.pipeline.catalogs.registries.tactics.prior_research_seed import TACTIC
    from app.pipeline.catalogs.audit import _get_phase_compatibility
    assert _get_phase_compatibility(TACTIC) == ["gather"]


def test_ach_rank_phase_compat_migrated_to_synthesize():
    from app.pipeline.catalogs.registries.tactics.ach_rank import TACTIC
    from app.pipeline.catalogs.audit import _get_phase_compatibility
    assert _get_phase_compatibility(TACTIC) == ["synthesize"]


def test_person_strategy_uses_unified_phase_ids():
    """After migration, person.py declares extract/gather/disconfirm/synthesize."""
    from app.pipeline.catalogs.registries.strategies.person import STRATEGY
    phase_ids = [p["id"] for p in STRATEGY["phases"]]
    assert set(phase_ids) == {"extract", "gather", "disconfirm", "synthesize"}


def test_person_strategy_uses_hypothesis_first_search_for_gather():
    from app.pipeline.catalogs.registries.strategies.person import STRATEGY
    gather = next(p for p in STRATEGY["phases"] if p["id"] == "gather")
    assert gather.get("preferred_tactic_id") == "hypothesis_first_search"


def test_person_strategy_uses_ach_rank_for_synthesize():
    from app.pipeline.catalogs.registries.strategies.person import STRATEGY
    synth = next(p for p in STRATEGY["phases"] if p["id"] == "synthesize")
    assert synth.get("preferred_tactic_id") == "ach_rank"


def test_due_diligence_strategy_uses_unified_phase_ids():
    from app.pipeline.catalogs.registries.strategies.due_diligence import STRATEGY
    phase_ids = [p["id"] for p in STRATEGY["phases"]]
    assert set(phase_ids) == {"extract", "gather", "disconfirm", "synthesize"}


def test_due_diligence_uses_ach_rank_for_synthesize():
    from app.pipeline.catalogs.registries.strategies.due_diligence import STRATEGY
    synth = next(p for p in STRATEGY["phases"] if p["id"] == "synthesize")
    assert synth.get("preferred_tactic_id") == "ach_rank"


def test_media_identification_uses_unified_phase_ids():
    from app.pipeline.catalogs.registries.strategies.media_identification import STRATEGY
    phase_ids = [p["id"] for p in STRATEGY["phases"]]
    # Allow either 3-phase or 4-phase shape; assert all ids are legal
    legal = {"extract", "gather", "disconfirm", "synthesize"}
    assert set(phase_ids).issubset(legal)
    # Must have at least extract / gather / synthesize
    assert {"extract", "gather", "synthesize"}.issubset(set(phase_ids))
