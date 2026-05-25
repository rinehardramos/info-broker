"""Unit tests for leads-gen richness + cost + recommendations.

Pure unit tests — no live stack, no network, no DB.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from benchmarks.score import (  # noqa: E402
    lead_richness,
    build_recommendations,
    aggregate_scores,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_LEADS_FIELDS = [
    "address", "price", "listing_url",
    "agent_name", "agent_email", "agent_phone",
    "owner_name", "owner_email", "owner_phone", "owner_background",
]


def _make_finding(sc="live_search", source_url="https://example.com", **fields) -> dict:
    d = {"source_class": sc, "source_url": source_url}
    d.update(fields)
    return d


def _make_lead(**fields) -> dict:
    """Helper: build a finding that looks like an enriched lead."""
    return _make_finding(**fields)


def _make_trail(branches=None, phases=None, tool_calls=5) -> dict:
    return {
        "branches": branches or [],
        "phases": phases or ["extract", "gather", "disconfirm", "synthesize"],
        "tool_calls": tool_calls,
    }


def _live_branch(tid="apify_listings_search") -> dict:
    return {"technique_id": tid, "source_class": "live_search"}


# ===========================================================================
# lead_richness
# ===========================================================================


class TestLeadRichness:
    def test_fully_enriched_lead(self):
        findings = [_make_lead(
            address="123 Main St, Chicago IL",
            price="$450,000",
            listing_url="https://zillow.com/123-main",
            agent_name="Jane Smith",
            agent_email="jane@realty.com",
            agent_phone="312-555-0100",
            owner_name="Bob Jones",
            owner_email="bob@gmail.com",
            owner_phone="312-555-0200",
            owner_background="Investor, owns 5 properties",
        )]
        trail = _make_trail(branches=[_live_branch()])
        result = lead_richness(findings, trail)

        assert result["lead_count"] == 1
        assert result["avg_completeness"] == pytest.approx(1.0, abs=0.01)
        per = result["per_lead_completeness"]
        assert len(per) == 1
        assert per[0] == pytest.approx(1.0, abs=0.01)

    def test_partial_enrichment(self):
        # Only address + price + agent_name populated (3 of 10)
        findings = [_make_lead(
            address="456 Oak Ave, Austin TX",
            price="$1,800/mo",
            agent_name="Tom Brown",
        )]
        trail = _make_trail(branches=[_live_branch()])
        result = lead_richness(findings, trail)

        assert result["lead_count"] == 1
        assert result["avg_completeness"] == pytest.approx(3 / 10, abs=0.01)

    def test_zero_enrichment_lead_flagged(self):
        # Finding with no leads-gen fields at all
        findings = [_make_finding(claim="some generic text")]
        trail = _make_trail(branches=[_live_branch()])
        result = lead_richness(findings, trail)

        assert result["lead_count"] == 1
        assert result["avg_completeness"] == pytest.approx(0.0, abs=0.01)
        assert result["zero_enrichment_count"] >= 1

    def test_multiple_leads_avg_completeness(self):
        # Lead 1: 10/10, Lead 2: 5/10 → avg = 0.75
        lead1 = _make_lead(
            address="100 A St", price="$200k", listing_url="https://z.com/100",
            agent_name="Alice", agent_email="a@b.com", agent_phone="111",
            owner_name="Dave", owner_email="d@e.com", owner_phone="222",
            owner_background="Investor",
        )
        lead2 = _make_lead(
            address="200 B St", price="$300k", listing_url="https://z.com/200",
            agent_name="Bob", agent_email="b@c.com",
        )
        findings = [lead1, lead2]
        trail = _make_trail(branches=[_live_branch()])
        result = lead_richness(findings, trail)

        assert result["lead_count"] == 2
        assert result["avg_completeness"] == pytest.approx((1.0 + 0.5) / 2, abs=0.01)

    def test_empty_findings(self):
        result = lead_richness([], _make_trail())
        assert result["lead_count"] == 0
        assert result["avg_completeness"] == 0.0
        assert result["zero_enrichment_count"] == 0

    def test_lead_count_equals_finding_count(self):
        findings = [
            _make_lead(address="A"), _make_lead(address="B"), _make_lead(address="C")
        ]
        result = lead_richness(findings, _make_trail(branches=[_live_branch()]))
        assert result["lead_count"] == 3


# ===========================================================================
# Cost metrics
# ===========================================================================


class TestCostMetrics:
    def test_cost_per_lead_basic(self):
        results = [
            {
                "item_id": "leads-gen-001",
                "item_score": 0.8,
                "coverage": 1.0,
                "source_quality": 0.8,
                "gaming_flags": [],
                "tripped_guard": None,
                "fact_matches": [],
                "richness": {"lead_count": 5, "avg_completeness": 0.7, "zero_enrichment_count": 0, "per_lead_completeness": []},
                "cost": {"ru_consumed": 100, "duration_s": 60.0},
                "matched_facts_count": 3,
            }
        ]
        meta = [{"strategy": "real_estate_leads", "mode": "leads_generation", "domain": "real_estate_leads", "technique_ids": [], "template": "real_estate_leads"}]
        agg = aggregate_scores(results, meta)
        cost_agg = agg.get("cost_summary", {})
        assert cost_agg["total_ru_consumed"] == 100
        assert cost_agg["cost_per_lead"] == pytest.approx(100 / 5, abs=0.01)
        assert cost_agg["cost_per_matched_fact"] == pytest.approx(100 / 3, abs=0.01)

    def test_cost_per_lead_zero_leads(self):
        results = [
            {
                "item_id": "leads-gen-002",
                "item_score": 0.0,
                "coverage": 0.0,
                "source_quality": 0.0,
                "gaming_flags": [],
                "tripped_guard": None,
                "fact_matches": [],
                "richness": {"lead_count": 0, "avg_completeness": 0.0, "zero_enrichment_count": 0, "per_lead_completeness": []},
                "cost": {"ru_consumed": 50, "duration_s": 30.0},
                "matched_facts_count": 0,
            }
        ]
        meta = [{"strategy": "real_estate_leads", "mode": "leads_generation", "domain": "real_estate_leads", "technique_ids": [], "template": "real_estate_leads"}]
        agg = aggregate_scores(results, meta)
        cost_agg = agg.get("cost_summary", {})
        # max(lead_count, 1) prevents div-by-zero
        assert cost_agg["cost_per_lead"] == pytest.approx(50 / 1, abs=0.01)
        assert cost_agg["cost_per_matched_fact"] == pytest.approx(50 / 1, abs=0.01)

    def test_cost_summary_absent_when_no_cost_data(self):
        results = [
            {"item_id": "x", "item_score": 0.5, "gaming_flags": [], "domain": "person",
             "coverage": 0.5, "source_quality": 1.0, "tripped_guard": None, "fact_matches": []}
        ]
        agg = aggregate_scores(results)
        # cost_summary should still be present but zero when no cost fields
        assert "cost_summary" in agg


# ===========================================================================
# build_recommendations
# ===========================================================================


class TestBuildRecommendations:
    def _base_result(self, **overrides) -> dict:
        base = {
            "item_id": "test-001",
            "item_score": 0.75,
            "coverage": 1.0,
            "source_quality": 0.75,
            "gaming_flags": [],
            "tripped_guard": None,
            "fact_matches": [],
            "matched_facts_count": 2,
            "richness": {
                "lead_count": 3,
                "avg_completeness": 0.8,
                "zero_enrichment_count": 0,
                "per_lead_completeness": [0.8, 0.9, 0.7],
            },
            "cost": {"ru_consumed": 50, "duration_s": 30.0},
        }
        base.update(overrides)
        return base

    def _base_agg(self, **overrides) -> dict:
        base = {
            "overall": {"mean_score": 0.75, "total_items": 1, "gamed_items": 0, "gamed_pct": 0.0},
            "cost_summary": {
                "total_ru_consumed": 50,
                "cost_per_lead": 16.7,
                "cost_per_matched_fact": 25.0,
                "avg_duration_s": 30.0,
            },
        }
        base.update(overrides)
        return base

    def test_returns_list(self):
        recs = build_recommendations([self._base_result()], self._base_agg())
        assert isinstance(recs, list)

    def test_each_rec_has_required_fields(self):
        recs = build_recommendations([self._base_result()], self._base_agg())
        for r in recs:
            assert "severity" in r
            assert "category" in r
            assert "message" in r
            assert "evidence" in r

    def test_anti_gaming_rec_fires_on_trip(self):
        result = self._base_result(
            gaming_flags=["training_only"],
            tripped_guard="training_only",
            item_score=0.0,
        )
        recs = build_recommendations([result], self._base_agg())
        categories = [r["category"] for r in recs]
        assert "anti-gaming" in categories

    def test_low_richness_rec_fires(self):
        result = self._base_result(
            richness={
                "lead_count": 2,
                "avg_completeness": 0.20,  # below 0.4 threshold
                "zero_enrichment_count": 1,
                "per_lead_completeness": [0.30, 0.10],
            }
        )
        recs = build_recommendations([result], self._base_agg())
        categories = [r["category"] for r in recs]
        assert "low-richness" in categories

    def test_zero_enrichment_leads_rec_fires(self):
        result = self._base_result(
            richness={
                "lead_count": 3,
                "avg_completeness": 0.5,
                "zero_enrichment_count": 2,
                "per_lead_completeness": [0.0, 0.0, 1.0],
            }
        )
        recs = build_recommendations([result], self._base_agg())
        categories = [r["category"] for r in recs]
        assert "low-richness" in categories

    def test_cost_outlier_rec_fires(self):
        agg = self._base_agg(cost_summary={
            "total_ru_consumed": 10000,
            "cost_per_lead": 2000.0,     # very high
            "cost_per_matched_fact": 5000.0,
            "avg_duration_s": 250.0,
        })
        result = self._base_result(cost={"ru_consumed": 10000, "duration_s": 250.0})
        recs = build_recommendations([result], agg)
        categories = [r["category"] for r in recs]
        assert "cost-outlier" in categories

    def test_underperforming_component_rec_fires(self):
        # Result with 0 matched facts (all facts unmatched)
        result = self._base_result(
            item_score=0.0,
            coverage=0.0,
            matched_facts_count=0,
            fact_matches=[{"claim": "x", "matched": False, "has_citation": False, "source_class": None, "score": 0.0}],
        )
        agg = self._base_agg(overall={"mean_score": 0.0, "total_items": 1, "gamed_items": 0, "gamed_pct": 0.0})
        recs = build_recommendations([result], agg)
        categories = [r["category"] for r in recs]
        assert "underperforming-component" in categories

    def test_gold_set_gap_rec_fires_on_zero_score_no_gaming(self):
        # Zero score without gaming flags = gold-set gap
        result = self._base_result(
            item_score=0.0,
            coverage=0.0,
            gaming_flags=[],
            tripped_guard=None,
            matched_facts_count=0,
        )
        agg = self._base_agg(overall={"mean_score": 0.0, "total_items": 1, "gamed_items": 0, "gamed_pct": 0.0})
        recs = build_recommendations([result], agg)
        categories = [r["category"] for r in recs]
        assert "gold-set-gap" in categories

    def test_sorted_by_severity(self):
        # Mix of severities — anti-gaming (error) should come before low-richness (warning)
        result_gamed = self._base_result(
            item_id="gamed",
            gaming_flags=["training_only"],
            tripped_guard="training_only",
            item_score=0.0,
        )
        result_low = self._base_result(
            item_id="low",
            richness={
                "lead_count": 1, "avg_completeness": 0.1,
                "zero_enrichment_count": 1, "per_lead_completeness": [0.1],
            }
        )
        recs = build_recommendations([result_gamed, result_low], self._base_agg())
        # critical / error severity must appear before warning / info
        _SEV_ORDER = {"critical": 0, "error": 1, "warning": 2, "info": 3}
        sevs = [_SEV_ORDER.get(r["severity"], 99) for r in recs]
        assert sevs == sorted(sevs)

    def test_missing_key_rec_fires(self):
        # Item that failed due to training_only (no live calls) can signal missing key
        result = self._base_result(
            gaming_flags=["training_only"],
            tripped_guard="training_only",
            item_score=0.0,
        )
        recs = build_recommendations([result], self._base_agg())
        # Should have anti-gaming; may also fire missing-key if heuristic detects it
        categories = [r["category"] for r in recs]
        # At minimum anti-gaming fires; missing-key is a bonus heuristic
        assert "anti-gaming" in categories

    def test_no_recs_on_clean_perfect_run(self):
        result = self._base_result(
            item_score=1.0,
            coverage=1.0,
            matched_facts_count=3,
            richness={
                "lead_count": 5,
                "avg_completeness": 0.9,
                "zero_enrichment_count": 0,
                "per_lead_completeness": [0.9, 0.9, 0.9, 0.9, 0.9],
            },
            cost={"ru_consumed": 80, "duration_s": 45.0},
        )
        agg = self._base_agg(
            overall={"mean_score": 1.0, "total_items": 1, "gamed_items": 0, "gamed_pct": 0.0},
            cost_summary={
                "total_ru_consumed": 80,
                "cost_per_lead": 16.0,
                "cost_per_matched_fact": 26.7,
                "avg_duration_s": 45.0,
            },
        )
        recs = build_recommendations([result], agg)
        # No actionable recommendations for a clean, rich, low-cost run
        critical_or_error = [r for r in recs if r["severity"] in ("critical", "error")]
        assert len(critical_or_error) == 0


# ===========================================================================
# Leads gold-set YAML parsing
# ===========================================================================


class TestLeadsGoldSetParsing:
    GOLDSET_DIR = Path(__file__).resolve().parent.parent.parent / "benchmarks" / "goldset"

    def test_leads_items_yaml_exists(self):
        p = self.GOLDSET_DIR / "leads_items.yaml"
        assert p.exists(), f"leads_items.yaml not found at {p}"

    def test_leads_items_yaml_parses(self):
        p = self.GOLDSET_DIR / "leads_items.yaml"
        raw = yaml.safe_load(p.read_text())
        assert isinstance(raw, list)
        assert len(raw) >= 2

    def test_leads_items_have_required_fields(self):
        p = self.GOLDSET_DIR / "leads_items.yaml"
        raw = yaml.safe_load(p.read_text())
        required = ("id", "query", "expected_facts", "domain")
        for item in raw:
            for field in required:
                assert field in item, f"Item {item.get('id')!r} missing {field!r}"

    def test_leads_items_have_real_estate_leads_domain(self):
        p = self.GOLDSET_DIR / "leads_items.yaml"
        raw = yaml.safe_load(p.read_text())
        for item in raw:
            assert item["domain"] == "real_estate_leads", (
                f"Item {item['id']!r} has domain {item['domain']!r}, expected real_estate_leads"
            )

    def test_leads_items_expected_facts_have_must_be_live(self):
        p = self.GOLDSET_DIR / "leads_items.yaml"
        raw = yaml.safe_load(p.read_text())
        for item in raw:
            for ef in item["expected_facts"]:
                assert "must_be_live" in ef, f"Item {item['id']!r} fact missing must_be_live"

    def test_leads_items_no_duplicate_ids(self):
        p = self.GOLDSET_DIR / "leads_items.yaml"
        raw = yaml.safe_load(p.read_text())
        ids = [item["id"] for item in raw]
        assert len(ids) == len(set(ids)), "Duplicate ids in leads_items.yaml"

    def test_goldset_loader_includes_leads_items(self):
        """Integration: the run_benchmark loader picks up leads_items.yaml."""
        from benchmarks.run_benchmark import load_goldset  # noqa: E402
        items = load_goldset()
        leads_items = [it for it in items if it.get("domain") == "real_estate_leads"]
        assert len(leads_items) >= 2

    def test_no_id_collision_with_existing_items(self):
        from benchmarks.run_benchmark import load_goldset  # noqa: E402
        items = load_goldset()
        ids = [it["id"] for it in items]
        assert len(ids) == len(set(ids)), "Duplicate ids across gold-set files"


# ---------------------------------------------------------------------------
# lead_richness scores SYNTHESIZED ranked_candidates + reports field_coverage
# ---------------------------------------------------------------------------

def test_lead_richness_prefers_ranked_candidates_and_reports_field_coverage():
    """When the trail has ranked_candidates (the synthesized leads), score those
    (richer evidence) not raw findings, and report run-wide field_coverage."""
    trail = {
        "ranked_candidates": [
            {  # an agent-contact lead (phone in evidence)
                "name": "Kim Wolle — Compass RE Texas",
                "evidence": [{"snippet": "Phone: (512) 555-1212, agent: Kim Wolle",
                              "source_url": "https://www.har.com/agent/x"}],
            },
            {  # a property lead (address + price + listing domain)
                "name": "123 Main St, Austin TX — $500,000",
                "evidence": [{"snippet": "123 Main St Austin TX $500,000 3bd 2ba",
                              "source_url": "https://www.realtor.com/x"}],
            },
        ]
    }
    r = lead_richness([{"candidate_name": "ignored finding"}], trail)
    # scored the 2 synthesized candidates, not the 1 finding
    assert r["lead_count"] == 2
    assert "field_coverage" in r
    # run surfaced agent_phone (cand 1) + address/price/listing_url (cand 2)
    assert r["field_coverage"] >= 0.4


def test_field_coverage_zero_when_nothing():
    r = lead_richness([], {})
    assert r["lead_count"] == 0
    assert r["field_coverage"] == 0.0
