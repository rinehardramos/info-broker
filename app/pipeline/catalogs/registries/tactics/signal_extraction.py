"""Signal extraction tactic — decompose the query into PRIMARY/SUPPORTING/CONTEXT signals.

The brain analyzes the query text WITHOUT tool calls in this phase. It identifies
what the user is looking for and tags signal weights. No specialist dispatch needed.
"""
from app.pipeline.catalogs import Tactic, TaskSpec


TACTIC = Tactic(
    id="decompose_query",
    phase_compatibility=["signal_extraction"],
    accepts={
        "query": "the user's original query string",
        "briefing": "phase briefing from the strategy",
    },
    produces=[
        # No specialist tasks — signal extraction is pure analysis.
        # The brain emits its analysis as the findings list with
        # source_class='training_knowledge' (it's reasoning from the query).
    ],
    cost_class="cheap",
    required_techniques=[],
    enforcement={"min_distinct_outputs": 0, "no_tool_calls_required": True},
)
