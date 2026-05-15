"""Disconfirm-search tactic — actively look for evidence AGAINST a hypothesis.

Used in the red_team phase. Each tactician slot is assigned one surviving
hypothesis from broaden; the brain runs falsification searches (e.g.
"does <candidate> NOT have the described feature", "evidence <candidate>
was not in <medium> in <year>"). Findings emitted by this tactic should
be flagged `is_disconfirm=True` so the strategist's ACH matrix can mark
them inconsistent.
"""
from app.pipeline.catalogs import Tactic, TaskSpec


TACTIC = Tactic(
    id="disconfirm_search",
    phase_compatibility=["red_team"],
    accepts={
        "target_hypothesis": "the candidate name being red-teamed",
        "signals_to_check": "list of signals (primary/supporting/medium/recency)",
    },
    produces=[
        TaskSpec(
            technique_id="web_search",
            params_template={"query": "{target_hypothesis} NOT {signal_descriptor}", "max_results": 5},
            budget_ru=1,
        ),
        TaskSpec(
            technique_id="google_news",
            params_template={"query": "{target_hypothesis} controversy debunked", "days_back": 365},
            budget_ru=1,
        ),
    ],
    cost_class="moderate",
    required_techniques=["web_search", "google_news"],
    enforcement={
        "min_distinct_outputs": 1,
        "all_findings_flagged_is_disconfirm": True,
    },
)
