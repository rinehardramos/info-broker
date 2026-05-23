# app/pipeline/catalogs/registries/tactics/synthesize_default.py
"""Default synthesize-phase tactic — rank, dedupe, finalize. No tools.

The brain receives prior_findings_slice from gather (and disconfirm, if
present), then emits a ranked / deduped set of final findings.
"""
from app.pipeline.catalogs.schemas import Tactic


TACTIC = Tactic(
    id="synthesize_default",
    phase_compatibility=["synthesize"],
    accepts={
        "evidence": "list of findings from gather/disconfirm",
        "briefing": "phase briefing from the strategy",
    },
    produces=[],
    cost_class="cheap",
    required_techniques=[],
    enforcement={"min_distinct_outputs": 0, "no_tool_calls_required": True},
)
