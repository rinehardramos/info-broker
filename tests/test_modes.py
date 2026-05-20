"""Tests for Modes (slice A1) — schema validation, loader fallback, ID enumeration."""
import pytest

from app.modes.loader import list_modes, get_mode
from app.modes.schema import Mode


def test_list_modes_returns_at_least_launch_set():
    modes = list_modes()
    ids = {m.id for m in modes}
    # Launch set must include these four
    assert {"general", "kyc_edd", "competitive_intel", "lead_gen"}.issubset(ids)


def test_get_mode_by_id_succeeds():
    mode = get_mode("kyc_edd")
    assert mode.id == "kyc_edd"
    assert "KYC" in mode.label
    assert mode.confidence_threshold_to_claim == 0.9
    assert mode.termination.require_contradiction_resolution is True
    assert len(mode.hypothesis_seeds) >= 1


def test_unknown_mode_falls_back_to_general():
    fallback = get_mode("does_not_exist")
    assert fallback.id == "general"


def test_none_mode_id_returns_default():
    default = get_mode(None)
    assert default.id == "general"


def test_modes_validate_against_schema():
    for mode in list_modes():
        # roundtrip dump/parse to catch any drift
        roundtrip = Mode.model_validate(mode.model_dump())
        assert roundtrip.id == mode.id
        assert 0.0 <= roundtrip.confidence_threshold_to_claim <= 1.0
        assert roundtrip.termination.max_turns >= 2


def test_competitive_intel_emphasizes_news():
    mode = get_mode("competitive_intel")
    assert mode.tool_weights.get("run_news_search", 0) > 1.0
    assert mode.source_class_weights.get("news", 0) >= 0.9


def test_lead_gen_is_bulk_oriented():
    mode = get_mode("lead_gen")
    assert "csv" in mode.export_formats
    assert mode.confidence_threshold_to_claim < 0.7  # bulk leads tolerate lower confidence
