"""Turn-scoped prompt builder for the orchestrated IS-brain loop (Path B)."""
from __future__ import annotations

from datetime import date

from app.is_prompt import render_past_research_blocks
from app.modes.loader import get_mode
from app.modes.schema import Mode
from app.pipeline.runners.working_memory import WorkingMemory, PHASE_TOOL_ALLOWLIST

TURN_TOOL_CALL_BUDGET = 6
TURN_REASONING_BUDGET_SECONDS = 30


def build_turn_prompt(
    wm: WorkingMemory,
    *,
    past_research: list[dict] | None = None,
    available_tools: list[str] | None = None,
) -> str:
    sections = wm.to_prompt_sections()
    today = date.today().isoformat()

    past_blocks = render_past_research_blocks(past_research)
    past_block_text = "\n\n".join(past_blocks) if past_blocks else "No prior research."

    tools_text = _render_tools(available_tools, wm.phase)

    # Mode-aware framing — persona + per-phase budget + rule overrides.
    mode = get_mode(wm.mode_id)
    role_block = _render_role(mode)
    mode_rules = _render_mode_rules(mode)
    tool_call_budget = _phase_tool_call_budget(mode, wm.phase)

    return _TEMPLATE.format(
        today=today,
        role=role_block,
        question=wm.question,
        turn=wm.turn,
        current_phase=sections["current_phase"],
        established_facts=sections["established_facts"],
        open_hypotheses=sections["open_hypotheses"],
        open_questions=sections["open_questions"],
        strategies_tried=sections["strategies_tried"],
        contradictions=sections["contradictions"],
        evidence_matrix=sections["evidence_matrix"],
        cross_run_priors=sections["cross_run_priors"],
        past_research=past_block_text,
        tools=tools_text,
        tool_call_budget=tool_call_budget,
        reasoning_budget=TURN_REASONING_BUDGET_SECONDS,
        delta_schema=_DELTA_SCHEMA,
        mode_rules=mode_rules,
    )


def _render_role(mode: Mode) -> str:
    """ROLE block — only emitted when the Mode actually has a persona. The
    general Mode ships an empty persona so this is a no-op for it, preserving
    the prior prompt shape exactly."""
    persona = (mode.prompt_persona or "").strip()
    if not persona:
        return ""
    return f"\nROLE ({mode.label})\n{persona}\n"


def _phase_tool_call_budget(mode: Mode, phase: str) -> int:
    """Per-Mode per-phase tool-call cap. Falls back to the constant if the
    phase isn't recognized (defensive — should never happen)."""
    phase_cfg = getattr(mode.phases, phase, None)
    if phase_cfg is None:
        return TURN_TOOL_CALL_BUDGET
    return phase_cfg.tool_call_budget


def _render_mode_rules(mode: Mode) -> str:
    """MODE-SPECIFIC RULES block — appended at the end of the rules list. Only
    emitted when at least one Mode-driven rule differs from default behavior;
    the general Mode renders an empty string here."""
    lines: list[str] = []

    if mode.id != "general":
        lines.append(f"MODE: {mode.label} (id={mode.id})")

    # Confidence threshold — drives when facts/findings can be promoted.
    # Default in the schema is 0.7; any other value is worth surfacing.
    if mode.confidence_threshold_to_claim != 0.7:
        lines.append(
            f"- Minimum confidence to claim or promote to established_facts: "
            f"{mode.confidence_threshold_to_claim:.2f}."
        )

    if mode.require_independent_corroboration:
        lines.append(
            "- A finding only becomes an established_fact when ≥2 independent "
            "sources agree. Single-source claims stay in findings."
        )

    if mode.treat_absence_as_finding:
        lines.append(
            "- If you checked a source and the subject was NOT present, emit a "
            'finding with source_class="negative" and note "checked, not found". '
            "Absence is itself a finding."
        )

    # Source-class weighting — give the brain the top tier so it knows what
    # to prioritize when multiple sources offer the same claim.
    if mode.source_class_weights:
        ranked = sorted(
            mode.source_class_weights.items(), key=lambda kv: kv[1], reverse=True
        )
        top = ", ".join(f"{cls}({w:.1f})" for cls, w in ranked[:3] if w > 0)
        if top:
            lines.append(f"- Prefer higher-weighted source classes: {top}.")

    # Termination tightening for KYC-shaped modes.
    if mode.termination.require_contradiction_resolution:
        lines.append(
            "- Every new_contradiction MUST be resolved (winner + resolution_note) "
            "before the run can enter SYNTHESIZE. Don't leave open contradictions."
        )

    if mode.termination.require_all_pir_satisfied:
        lines.append(
            "- All Priority Intelligence Requirements (PIR EEIs) must be resolved "
            "before SYNTHESIZE. If any remain unresolved, return to TEST."
        )

    if not lines:
        return ""
    body = "\n".join(lines)
    return f"\nMODE-SPECIFIC RULES\n{body}\n"


def _render_tools(tools: list[str] | None, phase: str) -> str:
    """Render the phase-gated tool allowlist into the prompt.

    The brain sees ONLY the tools it can actually call this turn — explicit
    caller-provided list takes precedence, otherwise the phase allowlist from
    PHASE_TOOL_ALLOWLIST. Synthesize phase gets explicit "no research tools"
    framing so the brain understands it must use accumulated findings.
    """
    if not tools:
        tools = PHASE_TOOL_ALLOWLIST.get(phase, [])
    if phase == "synthesize":
        return (
            "TOOLS (PHASE-GATED): no research tools are available this turn.\n"
            "Use only the findings already in your working memory. The only "
            "callable tool is `ask_user` for a critical missing-fact clarification.\n"
            "If you need new data, you cannot get it — produce the best synthesis "
            "you can from what's there and note any unresolved gaps."
        )
    lines = [f"TOOLS (PHASE-GATED · {phase}):  only these MCP tools are callable this turn:"]
    for t in tools:
        lines.append(f"  - mcp__info-broker-mcp__{t}")
    lines.append(
        "Tools outside this list are HARD-BLOCKED by the workflow (permission "
        "denied at subprocess level). Don't try them; pick from the list above."
    )
    return "\n".join(lines)


_DELTA_SCHEMA = """{
  "new_hypotheses":        [{"statement": str, "confidence": 0.0-1.0,
                             "falsification_condition": str}],
  "hypothesis_updates":    [{"id": str, "status": "supported|refuted|abandoned",
                             "confidence": 0.0-1.0,
                             "add_supporting_finding_ids": [str],
                             "add_refuting_finding_ids":   [str]}],
  "new_facts":             [{"claim": str, "source_url": str, "source_tool": str,
                             "confidence": 0.0-1.0,
                             "verified_by": "user_grade_A|two_independents|registry"}],
  "new_findings_data":     [{"id": str,
                             "title": str, "content": str, "source_url": str,
                             "source_tool": str, "confidence": 0.0-1.0,
                             "source_class": "primary_official|registry|news|aggregator|social|training|unknown"}],
  "new_evidence_scores":   [{"finding_id": str, "hypothesis_id": str,
                             "consistency": "consistent|inconsistent|neutral|not_applicable",
                             "note": str}],
  "evidence_score_updates":[{"finding_id": str, "hypothesis_id": str,
                             "consistency": "consistent|inconsistent|neutral|not_applicable",
                             "note": str}],
  "new_open_questions":    [{"question": str}],
  "open_question_updates": [{"id": str, "status": "provisionally_absent|confirmed_absent"}],
  "new_strategies":        [{"strategy_id": str, "target_hypothesis_id": str|null,
                             "outcome": "succeeded|failed|partial",
                             "failure_reason": str|null, "turn": int}],
  "new_contradictions":    [{"statement_a": str, "statement_b": str,
                             "finding_id_a": str|null, "finding_id_b": str|null,
                             "hypothesis_id": str|null}],
  "contradiction_updates": [{"id": str,
                             "winner": "a|b|both|neither",
                             "resolution_note": str}],
  "synthesis_summary":     str
}"""


_TEMPLATE = """You are the info-broker IS research brain, running TURN {turn} of an orchestrated loop.
Today is {today}.
{role}
THE QUESTION
{question}

{current_phase}

----------------------------------------------------------------------------
WORKING MEMORY (read this carefully - it is the state of the run so far)
----------------------------------------------------------------------------
{established_facts}

{open_hypotheses}

{open_questions}

{contradictions}

{evidence_matrix}

{cross_run_priors}

{strategies_tried}

----------------------------------------------------------------------------
PRIOR RESEARCH (cross-run context, separate from this run's working memory)
----------------------------------------------------------------------------
{past_research}

----------------------------------------------------------------------------
TOOLS
----------------------------------------------------------------------------
{tools}

----------------------------------------------------------------------------
TURN BUDGET (HARD CAP - workflow will retry the turn if you exceed)
----------------------------------------------------------------------------
- Use AT MOST {tool_call_budget} tool calls in this turn.
- Aim for AT MOST {reasoning_budget} seconds of reasoning before emitting output.
- This is ONE turn of a multi-turn loop. Do NOT try to finish the entire research now.

----------------------------------------------------------------------------
OUTPUT (emit exactly one JSON object, no prose around it)
----------------------------------------------------------------------------
Emit a WorkingMemoryDelta - the CHANGES this turn produced. Do NOT re-emit
the full working memory; only what is new or updated.

Schema:
{delta_schema}

Rules:
1. Only emit hypothesis_updates for ids that appear in OPEN HYPOTHESES above.
   Use the FULL id, do not truncate.
2. When forming new hypotheses (EXPLORE phase), you MUST include a
   `falsification_condition`: a specific, testable statement of what evidence
   would refute the hypothesis. Empty/vacuous means too vague - rewrite it.
3. Open questions are capped - if you propose more than 5 will be open, the
   workflow drops the extras. Resolve before opening new ones.
4. If a strategy you tried failed, RECORD it in new_strategies with a reason.
5. For facts you promote to `established_facts`, you MUST cite a source_url
   AND a source_tool.
6. If two findings (or hypothesis vs finding) conflict, flag a new_contradiction
   with both statements verbatim. SYNTHESIZE is GATED on every contradiction
   being resolved.
7. ACH: in TEST phase, for every new finding you also emit new_evidence_scores
   for that finding against EVERY open hypothesis. Inconsistencies are more
   diagnostic than consistencies. Hypotheses are ranked by fewest inconsistencies.
8. Respect the current phase. EXPLORE forms hypotheses; TEST resolves them
   one target at a time + scores evidence; SYNTHESIZE produces the final answer.
{mode_rules}"""
