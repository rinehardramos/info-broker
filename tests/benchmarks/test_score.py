"""Unit tests for benchmarks/score.py.

All tests use INLINE FIXTURES — no live stack, no network, no DB.
Exercises: the 4 anti-gaming guards, scoring, partial coverage,
source_quality weighting, gold-set YAML parsing, and module importability.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# Ensure repo root is on path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from benchmarks.score import (  # noqa: E402
    SOURCE_CLASS_WEIGHTS,
    _claim_matches,
    _guard_rag_shortcut,
    _guard_skipped_phases,
    _guard_training_only,
    _guard_unregistered_tools,
    aggregate_scores,
    render_summary_table,
    score_item,
)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_REGISTERED_IDS: frozenset[str] = frozenset(
    {
        "web_search",
        "image_search",
        "opencorporates_owner",
        "apollo_contact",
        "hunter_email_search",
        "google_news",
        "whois_owner",
        "phone_osint",
        "pipl_people",
        "tmdb_search",
        "prior_research",
        "apify_listings_search",
    }
)

_STRATEGY_PHASES: list[str] = ["extract", "gather", "disconfirm", "synthesize"]

_GOLD_ITEM = {
    "id": "test-item-001",
    "query": "Who is Tim Cook and what company does he lead?",
    "domain": "person",
    "expected_facts": [
        {
            "claim": "Tim Cook is the CEO of Apple Inc",
            "authoritative_source": "https://www.apple.com/leadership/tim-cook/",
            "must_be_live": False,
        },
        {
            "claim": "Tim Cook succeeded Steve Jobs as Apple CEO",
            "authoritative_source": "https://example.com/jobs-apple",
            "must_be_live": False,
        },
    ],
}

_GOLD_ITEM_LIVE = {
    "id": "test-live-001",
    "query": "Who owns One Microsoft Way Redmond WA?",
    "domain": "real_estate",
    "expected_facts": [
        {
            "claim": "One Microsoft Way Redmond WA is owned by Microsoft Corporation",
            "authoritative_source": "https://info.kingcounty.gov/",
            "must_be_live": True,
        },
    ],
}


def _make_trail(
    *,
    branches: list[dict] | None = None,
    phases: list[str] | None = None,
    tool_calls: int = 5,
) -> dict:
    return {
        "branches": branches if branches is not None else [],
        "phases": phases if phases is not None else _STRATEGY_PHASES[:],
        "phases_full": [],
        "tool_calls": tool_calls,
    }


def _make_finding(
    *,
    source_class: str = "live_search",
    source_url: str = "https://example.com/source",
    claim: str = "",
    evidence_summary: str = "",
) -> dict:
    return {
        "source_class": source_class,
        "source_url": source_url,
        "claim": claim,
        "evidence_summary": evidence_summary,
    }


def _live_branch(technique_id: str = "web_search") -> dict:
    return {
        "technique_id": technique_id,
        "source_class": "live_search",
        "confidence": 0.9,
    }


# ===========================================================================
# Guard 1 — training_only
# ===========================================================================


class TestGuardTrainingOnly:
    def test_fires_when_zero_tool_calls_and_branches_present(self):
        trail = _make_trail(
            branches=[{"technique_id": "web_search", "source_class": "live_search"}],
            tool_calls=0,
        )
        assert _guard_training_only(trail) == "training_only"

    def test_fires_when_all_branches_are_training(self):
        trail = _make_trail(
            branches=[
                {"technique_id": "recall", "source_class": "training_knowledge"},
                {"technique_id": "recall", "source_class": "training_knowledge"},
            ],
            tool_calls=2,
        )
        assert _guard_training_only(trail) == "training_only"

    def test_fires_when_no_branches_at_all(self):
        trail = _make_trail(branches=[], tool_calls=0)
        assert _guard_training_only(trail) == "training_only"

    def test_clean_when_live_branch_present(self):
        trail = _make_trail(
            branches=[_live_branch("web_search")],
            tool_calls=3,
        )
        assert _guard_training_only(trail) is None

    def test_clean_when_mixed_sources(self):
        trail = _make_trail(
            branches=[
                {"technique_id": "web_search", "source_class": "live_search"},
                {"technique_id": "recall", "source_class": "training_knowledge"},
            ],
            tool_calls=1,
        )
        assert _guard_training_only(trail) is None

    def test_score_is_zero_when_guard_fires(self):
        trail = _make_trail(branches=[], tool_calls=0)
        findings = [_make_finding(claim="Tim Cook is the CEO of Apple Inc", source_class="live_search")]
        result = score_item(
            _GOLD_ITEM,
            trail,
            findings,
            registered_technique_ids=_REGISTERED_IDS,
            strategy_phases=_STRATEGY_PHASES,
        )
        assert result["item_score"] == 0.0
        assert "training_only" in result["gaming_flags"]
        assert result["tripped_guard"] == "training_only"


# ===========================================================================
# Guard 2 — unregistered_tool
# ===========================================================================


class TestGuardUnregisteredTool:
    def test_fires_when_unknown_technique(self):
        trail = _make_trail(
            branches=[
                {"technique_id": "web_search", "source_class": "live_search"},
                {"technique_id": "shadow_scraper", "source_class": "live_search"},
            ],
            tool_calls=2,
        )
        assert _guard_unregistered_tools(trail, _REGISTERED_IDS) == "unregistered_tool"

    def test_clean_when_all_registered(self):
        trail = _make_trail(
            branches=[
                {"technique_id": "web_search", "source_class": "live_search"},
                {"technique_id": "image_search", "source_class": "live_search"},
            ],
            tool_calls=4,
        )
        assert _guard_unregistered_tools(trail, _REGISTERED_IDS) is None

    def test_skips_check_when_empty_registered_ids(self):
        trail = _make_trail(
            branches=[{"technique_id": "anything", "source_class": "live_search"}],
            tool_calls=1,
        )
        assert _guard_unregistered_tools(trail, frozenset()) is None

    def test_skips_branches_with_no_technique_id(self):
        trail = _make_trail(
            branches=[{"source_class": "live_search"}],  # no technique_id key
            tool_calls=1,
        )
        assert _guard_unregistered_tools(trail, _REGISTERED_IDS) is None

    def test_score_zero_when_guard_fires(self):
        trail = _make_trail(
            branches=[
                {"technique_id": "web_search", "source_class": "live_search"},
                {"technique_id": "EVIL_TOOL_42", "source_class": "live_search"},
            ],
            tool_calls=3,
        )
        findings = [_make_finding(claim="Tim Cook is the CEO of Apple Inc")]
        result = score_item(
            _GOLD_ITEM,
            trail,
            findings,
            registered_technique_ids=_REGISTERED_IDS,
            strategy_phases=_STRATEGY_PHASES,
        )
        assert result["item_score"] == 0.0
        assert "unregistered_tool" in result["gaming_flags"]
        assert result["tripped_guard"] == "unregistered_tool"


# ===========================================================================
# Guard 3 — skipped_phases
# ===========================================================================


class TestGuardSkippedPhases:
    def test_fires_when_required_phase_missing(self):
        trail = _make_trail(phases=["extract", "gather"])  # missing disconfirm, synthesize
        assert _guard_skipped_phases(trail, _STRATEGY_PHASES) == "skipped_phases"

    def test_fires_when_phases_empty(self):
        trail = _make_trail(phases=[])
        assert _guard_skipped_phases(trail, _STRATEGY_PHASES) == "skipped_phases"

    def test_clean_when_all_phases_ran(self):
        trail = _make_trail(phases=["extract", "gather", "disconfirm", "synthesize"])
        assert _guard_skipped_phases(trail, _STRATEGY_PHASES) is None

    def test_clean_when_extra_phases(self):
        trail = _make_trail(phases=["extract", "gather", "disconfirm", "synthesize", "bonus"])
        assert _guard_skipped_phases(trail, _STRATEGY_PHASES) is None

    def test_skips_check_when_no_strategy_phases(self):
        trail = _make_trail(phases=[])
        assert _guard_skipped_phases(trail, []) is None

    def test_score_zero_when_guard_fires(self):
        trail = _make_trail(
            branches=[_live_branch("web_search")],
            phases=["extract"],  # missing gather/disconfirm/synthesize
            tool_calls=3,
        )
        findings = [_make_finding(claim="Tim Cook is the CEO of Apple Inc")]
        result = score_item(
            _GOLD_ITEM,
            trail,
            findings,
            registered_technique_ids=_REGISTERED_IDS,
            strategy_phases=_STRATEGY_PHASES,
        )
        assert result["item_score"] == 0.0
        assert "skipped_phases" in result["gaming_flags"]
        assert result["tripped_guard"] == "skipped_phases"


# ===========================================================================
# Guard 4 — rag_shortcut
# ===========================================================================


class TestGuardRagShortcut:
    def test_fires_when_live_fact_matched_only_via_prior_research(self):
        """must_be_live fact matched, but contributing finding is prior_research."""
        findings = [
            _make_finding(
                source_class="prior_research",
                source_url="https://cache.example.com",
                claim="One Microsoft Way Redmond WA is owned by Microsoft Corporation",
            )
        ]
        findings_blob = "One Microsoft Way Redmond WA is owned by Microsoft Corporation"
        result = _guard_rag_shortcut(
            _GOLD_ITEM_LIVE["expected_facts"], findings, findings_blob
        )
        assert result == "rag_shortcut"

    def test_clean_when_live_fact_matched_via_live_search(self):
        findings = [
            _make_finding(
                source_class="live_search",
                source_url="https://kingcounty.gov/property/123",
                claim="One Microsoft Way Redmond WA is owned by Microsoft Corporation",
            )
        ]
        findings_blob = "One Microsoft Way Redmond WA is owned by Microsoft Corporation"
        result = _guard_rag_shortcut(
            _GOLD_ITEM_LIVE["expected_facts"], findings, findings_blob
        )
        assert result is None

    def test_skips_check_when_no_live_facts(self):
        """Items where must_be_live is always False — guard should not fire."""
        findings = [
            _make_finding(source_class="prior_research", claim="Tim Cook is CEO of Apple")
        ]
        findings_blob = "Tim Cook is CEO of Apple"
        result = _guard_rag_shortcut(
            _GOLD_ITEM["expected_facts"], findings, findings_blob
        )
        assert result is None

    def test_skips_check_when_live_fact_did_not_match(self):
        """If the fact didn't match at all, it's a coverage miss, not a RAG shortcut."""
        findings = [
            _make_finding(source_class="prior_research", claim="completely unrelated text")
        ]
        findings_blob = "completely unrelated text"
        result = _guard_rag_shortcut(
            _GOLD_ITEM_LIVE["expected_facts"], findings, findings_blob
        )
        assert result is None

    def test_score_zero_when_guard_fires(self):
        trail = _make_trail(
            branches=[_live_branch("prior_research")],
            tool_calls=1,
        )
        # Findings with prior_research source_class
        findings = [
            _make_finding(
                source_class="prior_research",
                source_url="https://cache.example.com",
                claim="One Microsoft Way Redmond WA is owned by Microsoft Corporation",
            )
        ]
        result = score_item(
            _GOLD_ITEM_LIVE,
            trail,
            findings,
            registered_technique_ids=_REGISTERED_IDS,
            strategy_phases=["extract", "gather", "synthesize"],
        )
        assert result["item_score"] == 0.0
        assert "rag_shortcut" in result["gaming_flags"]
        assert result["tripped_guard"] == "rag_shortcut"


# ===========================================================================
# Clean run — correct scoring
# ===========================================================================


class TestCleanRunScoring:
    def _clean_trail(self) -> dict:
        return _make_trail(
            branches=[
                _live_branch("web_search"),
                _live_branch("web_search"),
            ],
            phases=["extract", "gather", "disconfirm", "synthesize"],
            tool_calls=8,
        )

    def _full_findings(self) -> list[dict]:
        """Findings that match both expected_facts in _GOLD_ITEM."""
        return [
            _make_finding(
                source_class="live_search",
                source_url="https://apple.com/leadership/tim-cook/",
                claim="Tim Cook is the CEO of Apple Inc",
                evidence_summary="Tim Cook succeeded Steve Jobs as Apple CEO in 2011",
            ),
        ]

    def test_full_coverage_scores_high(self):
        result = score_item(
            _GOLD_ITEM,
            self._clean_trail(),
            self._full_findings(),
            registered_technique_ids=_REGISTERED_IDS,
            strategy_phases=_STRATEGY_PHASES,
        )
        assert result["item_score"] > 0.0
        assert result["coverage"] > 0.0
        assert result["source_quality"] > 0.0
        assert not result["gaming_flags"]
        assert result["tripped_guard"] is None

    def test_source_quality_live_search_weight(self):
        """live_search source_class should give 0.75 quality weight."""
        result = score_item(
            _GOLD_ITEM,
            self._clean_trail(),
            self._full_findings(),
            registered_technique_ids=_REGISTERED_IDS,
            strategy_phases=_STRATEGY_PHASES,
        )
        # live_search weight is 0.75 — source_quality should be around that
        assert abs(result["source_quality"] - SOURCE_CLASS_WEIGHTS["live_search"]) < 0.01

    def test_primary_official_scores_higher_than_live_search(self):
        """primary_official (1.0) > live_search (0.75)."""
        official_findings = [
            _make_finding(
                source_class="primary_official",
                source_url="https://apple.com/leadership/tim-cook/",
                claim="Tim Cook is the CEO of Apple Inc",
                evidence_summary="Tim Cook succeeded Steve Jobs as Apple CEO",
            )
        ]
        live_findings = [
            _make_finding(
                source_class="live_search",
                source_url="https://news.com/timcook",
                claim="Tim Cook is the CEO of Apple Inc",
                evidence_summary="Tim Cook succeeded Steve Jobs as Apple CEO",
            )
        ]
        trail = self._clean_trail()
        result_official = score_item(
            _GOLD_ITEM, trail, official_findings,
            registered_technique_ids=_REGISTERED_IDS, strategy_phases=_STRATEGY_PHASES
        )
        result_live = score_item(
            _GOLD_ITEM, trail, live_findings,
            registered_technique_ids=_REGISTERED_IDS, strategy_phases=_STRATEGY_PHASES
        )
        assert result_official["source_quality"] > result_live["source_quality"]

    def test_no_citation_lowers_score_to_zero(self):
        """Findings with no source_url should count as unmatched (citation required)."""
        findings_no_url = [
            {
                "source_class": "live_search",
                "source_url": "",  # empty URL
                "claim": "Tim Cook is the CEO of Apple Inc",
                "evidence_summary": "Tim Cook succeeded Steve Jobs as Apple CEO",
            }
        ]
        result = score_item(
            _GOLD_ITEM,
            self._clean_trail(),
            findings_no_url,
            registered_technique_ids=_REGISTERED_IDS,
            strategy_phases=_STRATEGY_PHASES,
        )
        # No citation → all facts unmatched → coverage = 0, score = 0
        assert result["item_score"] == 0.0
        assert result["coverage"] == 0.0


# ===========================================================================
# Partial coverage
# ===========================================================================


class TestPartialCoverage:
    def _partial_findings(self) -> list[dict]:
        """Only matches the first of the two expected_facts."""
        return [
            _make_finding(
                source_class="live_search",
                source_url="https://apple.com/leadership/tim-cook/",
                claim="Tim Cook is the CEO of Apple Inc",
                evidence_summary="Tim Cook leads Apple Inc as CEO",
            ),
            # Second finding does NOT contain "Steve Jobs" or "succeeded" tokens
            _make_finding(
                source_class="live_search",
                source_url="https://some-other-source.com",
                claim="Cook earned an MBA from Duke University",
                evidence_summary="Cook studied at Auburn and Duke",
            ),
        ]

    def test_partial_coverage_is_proportional(self):
        trail = _make_trail(
            branches=[_live_branch("web_search")],
            phases=["extract", "gather", "disconfirm", "synthesize"],
            tool_calls=4,
        )
        result = score_item(
            _GOLD_ITEM,
            trail,
            self._partial_findings(),
            registered_technique_ids=_REGISTERED_IDS,
            strategy_phases=_STRATEGY_PHASES,
        )
        # 1 of 2 facts matched → coverage ≈ 0.5
        assert result["coverage"] == pytest.approx(0.5, abs=0.01)
        # item_score = coverage * source_quality = 0.5 * 0.75 ≈ 0.375
        assert result["item_score"] == pytest.approx(0.5 * 0.75, abs=0.01)
        assert not result["gaming_flags"]

    def test_zero_coverage_gives_zero_score(self):
        trail = _make_trail(
            branches=[_live_branch("web_search")],
            phases=_STRATEGY_PHASES,
            tool_calls=3,
        )
        # Findings that don't match anything
        findings = [
            _make_finding(
                source_class="live_search",
                source_url="https://unrelated.com",
                claim="Completely unrelated content about something else entirely",
            )
        ]
        result = score_item(
            _GOLD_ITEM,
            trail,
            findings,
            registered_technique_ids=_REGISTERED_IDS,
            strategy_phases=_STRATEGY_PHASES,
        )
        assert result["coverage"] == 0.0
        assert result["item_score"] == 0.0


# ===========================================================================
# Source-quality weighting
# ===========================================================================


class TestSourceQualityWeighting:
    _SINGLE_FACT_ITEM = {
        "id": "sq-test-001",
        "query": "test query",
        "domain": "person",
        "expected_facts": [
            {
                "claim": "Tim Cook is the CEO of Apple Inc",
                "authoritative_source": "https://example.com",
                "must_be_live": False,
            }
        ],
    }

    def _trail(self) -> dict:
        return _make_trail(
            branches=[_live_branch("web_search")],
            phases=_STRATEGY_PHASES,
            tool_calls=3,
        )

    def _finding_with_class(self, sc: str) -> list[dict]:
        return [
            _make_finding(
                source_class=sc,
                source_url="https://example.com/source",
                claim="Tim Cook is the CEO of Apple Inc",
            )
        ]

    @pytest.mark.parametrize("source_class,expected_weight", [
        ("live_official",    1.00),
        ("primary_official", 1.00),
        ("registry",         0.95),
        ("live_search",      0.75),
        ("prior_research",   0.30),
        ("training_knowledge", 0.10),
    ])
    def test_source_quality_matches_weight_table(self, source_class, expected_weight):
        result = score_item(
            self._SINGLE_FACT_ITEM,
            self._trail(),
            self._finding_with_class(source_class),
            registered_technique_ids=_REGISTERED_IDS,
            strategy_phases=_STRATEGY_PHASES,
        )
        assert result["source_quality"] == pytest.approx(expected_weight, abs=0.01)
        assert result["item_score"] == pytest.approx(1.0 * expected_weight, abs=0.01)


# ===========================================================================
# Aggregate scores
# ===========================================================================


class TestAggregateScores:
    def test_empty_results(self):
        agg = aggregate_scores([])
        assert agg["overall"]["total_items"] == 0

    def test_overall_mean_and_gamed_count(self):
        results = [
            {"item_id": "a", "item_score": 0.8, "gaming_flags": [], "domain": "person"},
            {"item_id": "b", "item_score": 0.0, "gaming_flags": ["training_only"], "domain": "company"},
            {"item_id": "c", "item_score": 0.6, "gaming_flags": [], "domain": "person"},
        ]
        meta = [
            {"strategy": "person", "mode": "investigation", "domain": "person", "technique_ids": ["web_search"]},
            {"strategy": "company", "mode": "investigation", "domain": "company", "technique_ids": []},
            {"strategy": "person", "mode": "investigation", "domain": "person", "technique_ids": ["web_search"]},
        ]
        agg = aggregate_scores(results, meta)
        assert agg["overall"]["total_items"] == 3
        assert agg["overall"]["gamed_items"] == 1
        assert agg["overall"]["mean_score"] == pytest.approx((0.8 + 0.0 + 0.6) / 3, abs=0.01)

    def test_by_strategy_grouping(self):
        results = [
            {"item_id": "a", "item_score": 1.0, "gaming_flags": []},
            {"item_id": "b", "item_score": 0.5, "gaming_flags": []},
        ]
        meta = [
            {"strategy": "person", "mode": "i", "domain": "x", "technique_ids": []},
            {"strategy": "company", "mode": "i", "domain": "y", "technique_ids": []},
        ]
        agg = aggregate_scores(results, meta)
        assert "person" in agg["by_strategy"]
        assert "company" in agg["by_strategy"]
        assert agg["by_strategy"]["person"]["mean_score"] == pytest.approx(1.0)
        assert agg["by_strategy"]["company"]["mean_score"] == pytest.approx(0.5)

    def test_render_summary_table_runs(self):
        results = [
            {"item_id": "test-001", "item_score": 0.75, "coverage": 1.0,
             "source_quality": 0.75, "gaming_flags": [], "tripped_guard": None},
        ]
        agg = aggregate_scores(results)
        table = render_summary_table(results, agg)
        assert "test-001" in table
        assert "0.750" in table


# ===========================================================================
# Gold-set YAML parsing
# ===========================================================================


class TestGoldSetParsing:
    GOLDSET_DIR = Path(__file__).resolve().parent.parent.parent / "benchmarks" / "goldset"

    def test_items_yaml_parses(self):
        items_file = self.GOLDSET_DIR / "items.yaml"
        assert items_file.exists(), f"items.yaml not found at {items_file}"
        raw = yaml.safe_load(items_file.read_text())
        assert isinstance(raw, list)
        assert len(raw) >= 3  # at least 3 items

    def test_all_items_have_required_fields(self):
        items_file = self.GOLDSET_DIR / "items.yaml"
        raw = yaml.safe_load(items_file.read_text())
        required = ("id", "query", "expected_facts", "domain")
        for item in raw:
            for field in required:
                assert field in item, f"Item {item.get('id')!r} missing field {field!r}"

    def test_all_expected_facts_have_required_fields(self):
        items_file = self.GOLDSET_DIR / "items.yaml"
        raw = yaml.safe_load(items_file.read_text())
        ef_required = ("claim", "authoritative_source", "must_be_live")
        for item in raw:
            for ef in item.get("expected_facts", []):
                for field in ef_required:
                    assert field in ef, (
                        f"Item {item.get('id')!r} expected_fact missing {field!r}"
                    )

    def test_no_duplicate_ids(self):
        items_file = self.GOLDSET_DIR / "items.yaml"
        raw = yaml.safe_load(items_file.read_text())
        ids = [item["id"] for item in raw]
        assert len(ids) == len(set(ids)), "Duplicate ids in gold-set"

    def test_domains_are_valid(self):
        valid_domains = {"person", "company", "real_estate", "real_estate_leads", "due_diligence"}
        items_file = self.GOLDSET_DIR / "items.yaml"
        raw = yaml.safe_load(items_file.read_text())
        for item in raw:
            assert item["domain"] in valid_domains, (
                f"Item {item['id']!r} has invalid domain {item['domain']!r}"
            )

    def test_schema_yaml_exists(self):
        schema_file = self.GOLDSET_DIR / "schema.yaml"
        assert schema_file.exists()

    def test_goldset_loader_from_run_benchmark(self):
        """Integration: use the run_benchmark loader (no network)."""
        from benchmarks.run_benchmark import load_goldset  # noqa: E402
        items = load_goldset()
        assert len(items) >= 3
        for item in items:
            assert "id" in item
            assert "expected_facts" in item

    def test_goldset_loader_filter_by_ids(self):
        from benchmarks.run_benchmark import load_goldset  # noqa: E402
        items = load_goldset(item_ids=["person-jobs-001"])
        assert len(items) == 1
        assert items[0]["id"] == "person-jobs-001"


# ===========================================================================
# Module importability
# ===========================================================================


class TestImportability:
    def test_score_module_imports(self):
        import benchmarks.score  # noqa: F401

    def test_run_benchmark_module_imports(self):
        import benchmarks.run_benchmark  # noqa: F401

    def test_score_item_is_callable(self):
        from benchmarks.score import score_item as _si
        assert callable(_si)

    def test_aggregate_scores_is_callable(self):
        from benchmarks.score import aggregate_scores as _as
        assert callable(_as)


# ===========================================================================
# Claim matching helpers
# ===========================================================================


class TestClaimMatching:
    def test_exact_match(self):
        assert _claim_matches(
            "Tim Cook is the CEO of Apple Inc",
            "Tim Cook is the CEO of Apple Inc",
        )

    def test_partial_token_match_above_threshold(self):
        # "tim cook ceo apple" — 4 tokens. "tim cook ceo" present = 3/4 = 75%
        assert _claim_matches(
            "Tim Cook is the CEO of Apple Inc",
            "tim cook ceo technology leader at apple company",
        )

    def test_no_match_on_unrelated_text(self):
        assert not _claim_matches(
            "Tim Cook is the CEO of Apple Inc",
            "The weather today is sunny and warm in Seattle",
        )

    def test_empty_claim(self):
        assert not _claim_matches("", "some text")
