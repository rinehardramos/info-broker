# app/pipeline/catalogs/registries/tactics/gather_default.py
"""Default gather-phase tactic — generic live retrieval via web + news search.

Used by skeleton strategies that don't override with a domain-specific
gather tactic (e.g., real_estate uses listings_gather instead).
"""
from app.pipeline.catalogs.schemas import Tactic


TACTIC = Tactic(
    id="gather_default",
    phase_compatibility=["gather"],
    accepts={
        "signals": "dict — parsed signal hierarchy from extract phase",
        "briefing": "phase briefing from the strategy",
    },
    produces=[
        {
            "technique_id": "web_search",
            "params_template": {"query": "{gather_query}", "max_results": 8},
            "expect_schema": {"min_results": 1},
            "fail_modes": ["no_evidence", "tool_error", "schema_violation"],
            "budget_ru": 1,
        },
        {
            "technique_id": "google_news",
            "params_template": {"query": "{gather_query}", "days_back": 90},
            "expect_schema": {},
            "fail_modes": ["no_evidence", "tool_error", "schema_violation"],
            "budget_ru": 1,
        },
    ],
    cost_class="moderate",
    required_techniques=["web_search", "google_news"],
    enforcement={"min_distinct_outputs": 1},
)
