"""ACH rank tactic — final ranking phase. Pure analysis, no tool calls.

The strategist's _enrich_ranked_candidates() (which uses Heuer ACH) does
the actual matrix computation. This tactic exists so the rank_verify phase
has a registered tactic to satisfy the phase-compatibility check; the
brain's job is to emit a final ranking narrative + confidence summary.
"""
from app.pipeline.catalogs import Tactic


TACTIC = Tactic(
    id="ach_rank",
    phase_compatibility=["rank_verify"],
    accepts={
        "ach_inputs_from_red_team": "ranked hypotheses with disconfirm evidence",
        "pir_criteria": "primary information requirements + signal weights",
    },
    produces=[],  # No tool calls; pure analytical reasoning
    cost_class="cheap",
    required_techniques=[],
    enforcement={"min_distinct_outputs": 0, "no_tool_calls_required": True},
)
