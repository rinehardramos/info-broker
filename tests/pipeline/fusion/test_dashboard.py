"""Tests for global performance dashboard."""
from unittest.mock import patch

from app.pipeline.fusion.dashboard import build_dashboard, _numeric_to_grade


def test_numeric_to_grade():
    assert _numeric_to_grade(5.0) == "A"
    assert _numeric_to_grade(4.0) == "B"
    assert _numeric_to_grade(3.0) == "C"
    assert _numeric_to_grade(2.0) == "D"
    assert _numeric_to_grade(1.0) == "E"
    assert _numeric_to_grade(0.0) == "F"


def test_numeric_to_grade_rounds():
    assert _numeric_to_grade(4.6) == "A"   # round(4.6) = 5 = A
    assert _numeric_to_grade(3.4) == "C"   # round(3.4) = 3 = C
    # Python banker's rounding: round(1.5) = 2 = D (not B — spec comment was wrong)
    assert _numeric_to_grade(1.5) == "D"


def test_build_dashboard_empty():
    with patch("app.routers.v3.db.fetch_all", return_value=[]):
        result = build_dashboard()
    assert result["techniques"] == []
    assert result["tactics"] == []
    assert result["total_runs"] == 0


def test_build_dashboard_with_data():
    mock_rows = [
        {"scorecard": {
            "strategy": {"name": "person", "auto_grade": "B"},
            "tactics": [
                {
                    "name": "email_investigation",
                    "auto_grade": "A",
                    "yield_rate": 0.8,
                    "techniques": [
                        {"tool": "run_email_enumerator", "result_count": 3, "auto_grade": "A"},
                        {"tool": "run_smtp_verifier", "result_count": 2, "auto_grade": "A"},
                    ],
                },
                {
                    "name": "full_name_investigation",
                    "auto_grade": "D",
                    "yield_rate": 0.1,
                    "techniques": [
                        {"tool": "run_ddg_search", "result_count": 0, "auto_grade": "C"},
                    ],
                },
            ],
        }},
    ]
    with patch("app.routers.v3.db.fetch_all", return_value=mock_rows):
        result = build_dashboard()

    assert result["total_runs"] == 1
    assert len(result["techniques"]) == 3
    assert len(result["tactics"]) == 2

    # Best technique should be first (sorted by avg_numeric desc)
    assert result["techniques"][0]["tool"] in ("run_email_enumerator", "run_smtp_verifier")
    assert result["techniques"][0]["avg_grade"] == "A"

    # Tactic with grade A should be first
    assert result["tactics"][0]["avg_grade"] == "A"


def test_build_dashboard_aggregates_across_runs():
    mock_rows = [
        {"scorecard": {"strategy": {"name": "person", "auto_grade": "B"}, "tactics": [
            {
                "name": "email_investigation",
                "auto_grade": "A",
                "yield_rate": 0.9,
                "techniques": [
                    {"tool": "run_hibp_lookup", "result_count": 2, "auto_grade": "A"},
                ],
            },
        ]}},
        {"scorecard": {"strategy": {"name": "person", "auto_grade": "C"}, "tactics": [
            {
                "name": "email_investigation",
                "auto_grade": "C",
                "yield_rate": 0.3,
                "techniques": [
                    {"tool": "run_hibp_lookup", "result_count": 0, "auto_grade": "C"},
                ],
            },
        ]}},
    ]
    with patch("app.routers.v3.db.fetch_all", return_value=mock_rows):
        result = build_dashboard()

    # hibp_lookup should aggregate: (A+C)/2 = (5+3)/2 = 4.0 = B
    hibp = next(t for t in result["techniques"] if t["tool"] == "run_hibp_lookup")
    assert hibp["runs"] == 2
    assert hibp["avg_grade"] == "B"
    assert hibp["total_results"] == 2


def test_build_dashboard_error_rate():
    mock_rows = [
        {"scorecard": {"strategy": {"name": "person", "auto_grade": "B"}, "tactics": [
            {
                "name": "email_investigation",
                "auto_grade": "B",
                "yield_rate": 0.5,
                "techniques": [
                    {"tool": "run_flaky_tool", "result_count": 0, "auto_grade": "F", "error": "timeout"},
                    {"tool": "run_flaky_tool", "result_count": 1, "auto_grade": "C"},
                ],
            },
        ]}},
    ]
    with patch("app.routers.v3.db.fetch_all", return_value=mock_rows):
        result = build_dashboard()

    flaky = next(t for t in result["techniques"] if t["tool"] == "run_flaky_tool")
    assert flaky["runs"] == 2
    assert flaky["errors"] == 1
    assert flaky["error_rate"] == 0.5


def test_build_dashboard_user_grade_takes_precedence():
    """user_grade should override auto_grade when both exist."""
    mock_rows = [
        {"scorecard": {"strategy": {"name": "person", "auto_grade": "C"}, "tactics": [
            {
                "name": "email_investigation",
                "auto_grade": "C",
                "user_grade": "A",
                "yield_rate": 0.8,
                "techniques": [
                    {
                        "tool": "run_email_enumerator",
                        "result_count": 5,
                        "auto_grade": "C",
                        "user_grade": "A",
                    },
                ],
            },
        ]}},
    ]
    with patch("app.routers.v3.db.fetch_all", return_value=mock_rows):
        result = build_dashboard()

    # User graded A should dominate, not the auto_grade C
    assert result["techniques"][0]["avg_grade"] == "A"
    assert result["tactics"][0]["avg_grade"] == "A"


def test_build_dashboard_skips_invalid_scorecards():
    """Rows with null or non-dict scorecard should be silently skipped."""
    mock_rows = [
        {"scorecard": None},
        {"scorecard": "not_a_dict"},
        {"scorecard": {"strategy": {"name": "person", "auto_grade": "B"}, "tactics": [
            {
                "name": "good_tactic",
                "auto_grade": "B",
                "yield_rate": 0.5,
                "techniques": [
                    {"tool": "run_good_tool", "result_count": 2, "auto_grade": "B"},
                ],
            },
        ]}},
    ]
    with patch("app.routers.v3.db.fetch_all", return_value=mock_rows):
        result = build_dashboard()

    # All 3 rows are counted by total_runs; only the valid one contributes stats
    assert result["total_runs"] == 3
    assert len(result["techniques"]) == 1
    assert result["techniques"][0]["tool"] == "run_good_tool"
