# app/pipeline/catalogs/registries/tactics/extract_default.py
"""Default extract-phase tactic — parse query into typed signals, no tools.

The brain analyzes the query text without tool calls. It emits findings
with source_class='training_knowledge' (reasoning from the query itself).
"""
from app.pipeline.catalogs.schemas import Tactic


TACTIC = Tactic(
    id="extract_default",
    phase_compatibility=["extract"],
    accepts={
        "query": "the user's original query string",
        "briefing": "phase briefing from the strategy",
    },
    produces=[],
    cost_class="cheap",
    required_techniques=[],
    enforcement={"min_distinct_outputs": 0, "no_tool_calls_required": True},
)
