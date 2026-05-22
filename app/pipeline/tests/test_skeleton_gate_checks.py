"""Gate check kinds used by the skeleton-based research strategies.

The 8 strategies built atop research_skeleton (real_estate, lead, company,
place, generation, explanation, prediction, synthesis) each declare a
domain-specific gate check kind. Before this batch those kinds were
declared but not registered — the strategist fail-OPENed on them, so
runs sailed through every gate and reported success with 0 work done.

This module pins the behaviour of each new check function. All 8 are
intentionally generic (count-based, presence-based) so they enforce
"the brain returned SOMETHING" rather than "the brain returned the
right thing" — leave specificity to future iteration.
"""
from __future__ import annotations

from app.pipeline.catalogs.budget import BudgetEnvelope
from app.pipeline.strategist import (
    PhaseOutput,
    _GATE_CHECKS,
    _gate_min_listings_returned,
    _gate_contact_info_per_target,
    _gate_min_signal_classes_covered,
    _gate_coordinates_present,
    _gate_min_options_with_rationale,
    _gate_min_mechanisms_with_support,
    _gate_confidence_band_present,
    _gate_min_sources_synthesized,
)


def _env() -> BudgetEnvelope:
    return BudgetEnvelope(
        capability="general", hypothesis_count="competing", depth="search",
        speed="normal", resource="medium", mode="quick_lookup",
    )


def _po(findings=None, metadata=None) -> PhaseOutput:
    return PhaseOutput(
        phase_id="gather",
        aggregated_findings=findings or [],
        distinct_candidate_names=[],
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Registration — the audit at startup walks this
# ---------------------------------------------------------------------------


class TestRegistration:
    """Every new check kind must be in _GATE_CHECKS so the audit passes
    and the runtime can resolve it. This is the only thing that proves
    the strategies are no longer no-ops."""

    def test_all_eight_kinds_registered(self):
        for kind in [
            "min_listings_returned",
            "contact_info_per_target",
            "min_signal_classes_covered",
            "coordinates_present",
            "min_options_with_rationale",
            "min_mechanisms_with_support",
            "confidence_band_present",
            "min_sources_synthesized",
        ]:
            assert kind in _GATE_CHECKS, f"{kind!r} not in _GATE_CHECKS"


# ---------------------------------------------------------------------------
# real_estate — gather: ≥N findings (default 1)
# ---------------------------------------------------------------------------


class TestMinListingsReturned:
    def test_zero_findings_fails(self):
        assert _gate_min_listings_returned(_po(findings=[]), {"min": 1}, _env()) is False

    def test_threshold_met(self):
        f = [{"candidate_name": "listing-1"}, {"candidate_name": "listing-2"}]
        assert _gate_min_listings_returned(_po(findings=f), {"min": 2}, _env()) is True

    def test_below_threshold_fails(self):
        f = [{"candidate_name": "listing-1"}]
        assert _gate_min_listings_returned(_po(findings=f), {"min": 3}, _env()) is False


# ---------------------------------------------------------------------------
# lead — gather: at least N "targets" (distinct candidates) have a finding
# ---------------------------------------------------------------------------


class TestContactInfoPerTarget:
    def test_no_findings_fails(self):
        assert _gate_contact_info_per_target(_po(), {"min": 1}, _env()) is False

    def test_one_finding_per_target_passes(self):
        f = [
            {"candidate_name": "alice"},
            {"candidate_name": "bob"},
        ]
        po = PhaseOutput(phase_id="gather", aggregated_findings=f,
                         distinct_candidate_names=["alice", "bob"], metadata={})
        assert _gate_contact_info_per_target(po, {"min": 1}, _env()) is True

    def test_missing_target_fails(self):
        f = [{"candidate_name": "alice"}]
        po = PhaseOutput(phase_id="gather", aggregated_findings=f,
                         distinct_candidate_names=["alice", "bob"], metadata={})
        assert _gate_contact_info_per_target(po, {"min": 1}, _env()) is False


# ---------------------------------------------------------------------------
# company — gather: ≥N distinct source_class values represented in findings
# ---------------------------------------------------------------------------


class TestMinSignalClassesCovered:
    def test_one_class_below_min_fails(self):
        f = [{"source_class": "news"}, {"source_class": "news"}]
        assert _gate_min_signal_classes_covered(_po(findings=f), {"min": 2}, _env()) is False

    def test_two_distinct_classes_pass(self):
        f = [{"source_class": "news"}, {"source_class": "registry"}, {"source_class": "news"}]
        assert _gate_min_signal_classes_covered(_po(findings=f), {"min": 2}, _env()) is True

    def test_empty_findings_fail(self):
        assert _gate_min_signal_classes_covered(_po(), {"min": 1}, _env()) is False


# ---------------------------------------------------------------------------
# place — gather: at least one finding mentions coordinates
# ---------------------------------------------------------------------------


class TestCoordinatesPresent:
    def test_no_findings_fail(self):
        assert _gate_coordinates_present(_po(), {}, _env()) is False

    def test_finding_with_lat_lon_passes(self):
        f = [{"evidence_summary": "lat=40.7128 lon=-74.0060 NYC"}]
        assert _gate_coordinates_present(_po(findings=f), {}, _env()) is True

    def test_finding_with_decimal_pair_passes(self):
        f = [{"evidence_snippet": "Address resolves to 14.5995, 120.9842"}]
        assert _gate_coordinates_present(_po(findings=f), {}, _env()) is True

    def test_finding_without_coords_fails(self):
        f = [{"evidence_snippet": "Manila is in Luzon"}]
        assert _gate_coordinates_present(_po(findings=f), {}, _env()) is False


# ---------------------------------------------------------------------------
# generation — synthesize: ≥N distinct options proposed
# ---------------------------------------------------------------------------


class TestMinOptionsWithRationale:
    def test_zero_options_fail(self):
        assert _gate_min_options_with_rationale(_po(), {"min": 2}, _env()) is False

    def test_two_distinct_candidates_pass(self):
        po = PhaseOutput(phase_id="synthesize", aggregated_findings=[],
                         distinct_candidate_names=["opt-A", "opt-B"], metadata={})
        assert _gate_min_options_with_rationale(po, {"min": 2}, _env()) is True

    def test_default_min_is_two(self):
        po = PhaseOutput(phase_id="synthesize", aggregated_findings=[],
                         distinct_candidate_names=["opt-A"], metadata={})
        assert _gate_min_options_with_rationale(po, {}, _env()) is False  # default min=2


# ---------------------------------------------------------------------------
# explanation — synthesize: ≥N distinct mechanism candidates with evidence
# ---------------------------------------------------------------------------


class TestMinMechanismsWithSupport:
    def test_zero_fails(self):
        assert _gate_min_mechanisms_with_support(_po(), {"min": 2}, _env()) is False

    def test_two_distinct_pass(self):
        po = PhaseOutput(phase_id="synthesize",
                         aggregated_findings=[
                             {"candidate_name": "M1", "source_url": "https://a"},
                             {"candidate_name": "M2", "source_url": "https://b"},
                         ],
                         distinct_candidate_names=["M1", "M2"], metadata={})
        assert _gate_min_mechanisms_with_support(po, {"min": 2}, _env()) is True

    def test_distinct_count_but_no_source_fails(self):
        """A 'mechanism' without any source URL doesn't have support."""
        po = PhaseOutput(phase_id="synthesize",
                         aggregated_findings=[
                             {"candidate_name": "M1"},
                             {"candidate_name": "M2"},
                         ],
                         distinct_candidate_names=["M1", "M2"], metadata={})
        assert _gate_min_mechanisms_with_support(po, {"min": 2}, _env()) is False


# ---------------------------------------------------------------------------
# prediction — synthesize: at least one finding mentions a confidence band
# ---------------------------------------------------------------------------


class TestConfidenceBandPresent:
    def test_no_findings_fail(self):
        assert _gate_confidence_band_present(_po(), {}, _env()) is False

    def test_finding_with_confidence_key_passes(self):
        f = [{"candidate_name": "btc", "confidence": 0.6}]
        assert _gate_confidence_band_present(_po(findings=f), {}, _env()) is True

    def test_evidence_text_mentions_band_passes(self):
        f = [{"evidence_summary": "Forecast 70% confidence band: +10 to +25%"}]
        assert _gate_confidence_band_present(_po(findings=f), {}, _env()) is True

    def test_finding_with_no_confidence_signal_fails(self):
        f = [{"evidence_summary": "Bitcoin might go up"}]
        assert _gate_confidence_band_present(_po(findings=f), {}, _env()) is False


# ---------------------------------------------------------------------------
# synthesis — synthesize: ≥N distinct source URLs across findings
# ---------------------------------------------------------------------------


class TestMinSourcesSynthesized:
    def test_zero_sources_fail(self):
        assert _gate_min_sources_synthesized(_po(), {"min": 3}, _env()) is False

    def test_three_distinct_urls_pass(self):
        f = [
            {"source_url": "https://a.com/1"},
            {"source_url": "https://b.com/2"},
            {"source_url": "https://c.com/3"},
        ]
        assert _gate_min_sources_synthesized(_po(findings=f), {"min": 3}, _env()) is True

    def test_duplicate_urls_dont_count(self):
        f = [
            {"source_url": "https://a.com/1"},
            {"source_url": "https://a.com/1"},
            {"source_url": "https://a.com/1"},
        ]
        assert _gate_min_sources_synthesized(_po(findings=f), {"min": 3}, _env()) is False

    def test_empty_url_skipped(self):
        f = [
            {"source_url": ""},
            {"source_url": "https://a.com/1"},
        ]
        assert _gate_min_sources_synthesized(_po(findings=f), {"min": 1}, _env()) is True
        assert _gate_min_sources_synthesized(_po(findings=f), {"min": 2}, _env()) is False
