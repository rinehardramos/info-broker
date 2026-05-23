# app/pipeline/catalogs/registries/tactics/disconfirm_default.py
"""Default disconfirm-phase tactic — actively seek refuting evidence (Heuer ACH).

Used by ACH-shaped strategies (person, due_diligence, media_identification).
Strategies that don't need disconfirmation simply omit the phase from their
research-skeleton build_research_strategy call.
"""
from app.pipeline.catalogs.schemas import Tactic


TACTIC = Tactic(
    id="disconfirm_default",
    phase_compatibility=["disconfirm"],
    accepts={
        "hypotheses": "list — leading hypotheses from gather",
        "briefing": "phase briefing from the strategy",
    },
    produces=[
        {
            "technique_id": "web_search",
            "params_template": {"query": "{counter_hypothesis_query}", "max_results": 6},
            "expect_schema": {},
            "fail_modes": ["no_evidence", "tool_error", "schema_violation"],
            "budget_ru": 1,
        },
    ],
    cost_class="moderate",
    required_techniques=["web_search"],
    enforcement={"min_distinct_outputs": 0},  # zero disconfirming findings is informative, not a failure
)
