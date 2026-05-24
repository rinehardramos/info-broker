"""Tests for strategy scorecard engine."""
from app.pipeline.fusion.scorecard import (
    build_scorecard, auto_grade_technique, auto_grade_tactic, auto_grade_strategy,
    grade_comment_technique, grade_comment_tactic, grade_comment_strategy,
    query_explanatory_score,
)


def test_auto_grade_technique_a():
    # 5 results → completely reliable / confirmed = A1
    assert auto_grade_technique(result_count=5, error=None) == "A1"


def test_auto_grade_technique_b():
    # 1 result → usually reliable / probably true = B2
    assert auto_grade_technique(result_count=1, error=None) == "B2"


def test_auto_grade_technique_c():
    # 0 results, no error → fairly reliable / possibly true = C3
    assert auto_grade_technique(result_count=0, error=None) == "C3"


def test_auto_grade_technique_f_error():
    # hard error → unreliable / improbable = E5
    assert auto_grade_technique(result_count=0, error="HTTP 403 blocked") == "E5"


def test_auto_grade_technique_e_timeout():
    # timeout → not usually reliable / doubtful = D4
    assert auto_grade_technique(result_count=0, error="timeout") == "D4"


def test_auto_grade_tactic_high_yield():
    techniques = [
        {"tool": "run_email_enumerator", "result_count": 3, "auto_grade": "A1"},
        {"tool": "run_smtp_verifier", "result_count": 2, "auto_grade": "A2"},
    ]
    grade = auto_grade_tactic(techniques)
    # High yield with multiple A grades → A1 or B2
    assert grade[0] in ("A", "B")


def test_auto_grade_tactic_all_failed():
    techniques = [
        {"tool": "run_instagram_profile", "result_count": 0, "auto_grade": "F6"},
    ]
    assert auto_grade_tactic(techniques) == "F6"


def test_auto_grade_tactic_mixed():
    techniques = [
        {"tool": "a", "result_count": 2, "auto_grade": "B2"},
        {"tool": "b", "result_count": 0, "auto_grade": "C3"},
    ]
    grade = auto_grade_tactic(techniques)
    assert grade[0] in ("B", "C")


def test_auto_grade_strategy_good():
    tactics = [
        {"name": "email", "auto_grade": "A1"},
        {"name": "social", "auto_grade": "B2"},
        {"name": "neg_screen", "auto_grade": "A2"},
    ]
    grade = auto_grade_strategy(tactics, completeness_pct=0.8)
    assert grade[0] in ("A", "B")


def test_auto_grade_strategy_poor():
    tactics = [
        {"name": "email", "auto_grade": "F6"},
    ]
    grade = auto_grade_strategy(tactics, completeness_pct=0.1)
    assert grade[0] in ("E", "F")


def test_build_scorecard_full():
    trail = {
        "branches": [
            {"name": "email_discovery", "depth": 2, "status": "fruit",
             "tools_used": ["run_email_enumerator", "run_smtp_verifier", "run_hibp_lookup"],
             "findings_count": 3},
            {"name": "social_mapping", "depth": 1, "status": "dead_end",
             "tools_used": ["run_instagram_profile", "run_ddg_search"],
             "findings_count": 0},
            {"name": "neg_screening", "depth": 1, "status": "fruit",
             "tools_used": ["run_pep_sanctions_screen", "run_adverse_media"],
             "findings_count": 2},
        ],
        "total_branches": 3
    }
    findings = [
        {"content": "email found", "source": "email_enumerator"},
        {"content": "breach found", "source": "hibp_lookup"},
        {"content": "clean record", "source": "pep_sanctions_screen"},
    ]
    scorecard = build_scorecard(trail, findings, completeness_pct=0.5, entity_type="person")

    assert "strategy" in scorecard
    assert "tactics" in scorecard
    assert scorecard["strategy"]["name"] == "person"
    # Admiralty 2-letter code: source letter (A-F) + credibility digit (1-6)
    assert scorecard["strategy"]["auto_grade"][0] in "ABCDEF"
    assert len(scorecard["tactics"]) >= 2

    # Each tactic should have techniques
    for tactic in scorecard["tactics"]:
        assert "techniques" in tactic
        assert "auto_grade" in tactic
        for tech in tactic["techniques"]:
            assert "tool" in tech
            assert "auto_grade" in tech


def test_build_scorecard_empty_trail():
    scorecard = build_scorecard({"branches": []}, [], completeness_pct=0.0, entity_type="person")
    assert scorecard["strategy"]["auto_grade"] == "F6"
    assert scorecard["tactics"] == []


def test_build_scorecard_groups_by_tactic():
    trail = {
        "branches": [
            {"name": "b1", "tools_used": ["run_hibp_lookup", "run_smtp_verifier"], "findings_count": 2, "status": "fruit"},
        ]
    }
    scorecard = build_scorecard(trail, [], completeness_pct=0.3, entity_type="person")
    # hibp_lookup and smtp_verifier both map to "email" selector
    # They should be grouped into the same tactic
    email_tactics = [t for t in scorecard["tactics"] if t["selector_type"] == "email"]
    assert len(email_tactics) <= 1  # Should be grouped, not duplicated


def test_grade_comment_technique_a():
    # A1 = completely reliable / confirmed → effective comment
    c = grade_comment_technique("run_hibp_lookup", "A1", 5, None)
    assert "effective" in c.lower() or "prioritize" in c.lower()


def test_grade_comment_technique_f():
    # E5 = unreliable / improbable (hard error) → FAILED comment with error detail
    c = grade_comment_technique("run_instagram_profile", "E5", 0, "HTTP 403")
    assert "FAILED" in c or "failed" in c.lower()
    assert "403" in c


def test_grade_comment_tactic_good():
    # A1 = completely reliable → effective comment
    c = grade_comment_tactic("email_investigation", "A1", 0.8, ["A1", "B2"])
    assert "effective" in c.lower()


def test_grade_comment_tactic_bad():
    # F6 = completely failed → failed comment
    c = grade_comment_tactic("social_mapping", "F6", 0.0, ["F6", "F6"])
    assert "failed" in c.lower()


def test_grade_comment_strategy_good():
    # B2 = usually reliable → coverage comment
    c = grade_comment_strategy("person", "B2", 0.7, [])
    assert "coverage" in c.lower()


def test_grade_comment_strategy_gaps():
    # D4 = not usually reliable → gap details included
    c = grade_comment_strategy("person", "D4", 0.2, ["family", "financial", "breach"])
    assert "family" in c or "financial" in c


def test_query_explanatory_score_medium_type_penalty():
    """Non-ad candidate scored with medium_type='advertisement' gets a lower score."""
    signals = {"primary": "girl", "supporting": "shotgun", "context": "spiderman"}
    # A show candidate (no ad medium)
    candidate_show = {"medium_type": "show", "year": 2025, "branches": ["a", "b"]}
    score_without = query_explanatory_score(candidate_show, signals)
    score_with_ad = query_explanatory_score(candidate_show, signals, medium_type="advertisement")
    assert score_with_ad < score_without


def test_query_explanatory_score_medium_type_bonus():
    """Ad candidate scored with medium_type='advertisement' gets +0.15 bonus."""
    signals = {"primary": "girl", "supporting": "", "context": ""}
    candidate_ad = {"medium_type": "advertisement", "year": 2025, "branches": []}
    score_without = query_explanatory_score(candidate_ad, signals)
    score_with_ad = query_explanatory_score(candidate_ad, signals, medium_type="advertisement")
    assert score_with_ad > score_without


def test_query_explanatory_score_spider_noir_baseline():
    """Male-lead show candidate with medium_type='advertisement' scores <= 0.40."""
    # Spider-Noir baseline: male lead, no supporting signal match, franchise connection only
    signals = {"primary": "girl", "supporting": "shotgun", "context": "spiderman"}
    male_lead_show = {"medium_type": "show", "year": 2025, "branches": [], "title": "Spider-Noir"}
    score = query_explanatory_score(male_lead_show, signals, medium_type="advertisement")
    assert score <= 0.40


def test_build_scorecard_includes_comments():
    trail = {
        "branches": [
            {"name": "test", "tools_used": ["run_ddg_search"], "findings_count": 1, "status": "fruit"},
        ]
    }
    sc = build_scorecard(trail, [], completeness_pct=0.3, entity_type="person")
    assert "comment" in sc["strategy"]
    assert "comment" in sc["tactics"][0]
    assert "comment" in sc["tactics"][0]["techniques"][0]
