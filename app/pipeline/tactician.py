"""Tactician runtime — scoped per-hypothesis subprocess (MVP-M7).

One tactician is spawned per parallel hypothesis slot per divergent phase.
It picks a tactic from the catalog, delegates task execution to specialists,
and returns a structured TacticianOutput for the strategist to aggregate.

Visibility invariant (§7.2 of docs/intelligence/three-tier-brain-architecture.md):
  - The tactician sees ONLY its own unit_of_work.
  - It does NOT see peer tacticians' data, other phases, or the full original query.
  - The function signature has no peer-state parameter — this is the structural guarantee.
  TODO(§7.2): When wiring into strategist in M6/M9, assert that the caller never
  injects cross-tactician data here. Add an integration test in M9 that verifies
  distinct candidate sets across sibling tacticians.

Subprocess invocation (§10.2 M7):
  For MVP the real Claude Code subprocess pattern (from app/is_brain.py) is
  injected as `tactic_runner_fn`. Tests inject a synchronous fake that returns
  a predetermined list of tool-call dicts. Production wiring (M9) will plug in
  the real async runner.

Model selection (§5.2.1):
  - capability_tier="light"   → claude-haiku-4-5-20251001
  - capability_tier="general" → claude-sonnet-4-6
  - capability_tier="high"    → claude-sonnet-4-6  (Opus is reserved for strategist)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from app.pipeline.catalogs.schemas import PhaseSpec, Tactic, Technique, TaskSpec

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model assignment per capability tier (§5.2.1)
# ---------------------------------------------------------------------------

_CAPABILITY_MODEL_MAP: dict[str, str] = {
    "light": "claude-haiku-4-5-20251001",
    "general": "claude-sonnet-4-6",
    "high": "claude-sonnet-4-6",  # Opus is reserved for strategist per §5.2.1
}


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------

@dataclass
class TacticianOutput:
    """Aggregated output for one hypothesis slot.

    Attributes:
        slot_idx:          Index of this hypothesis slot (0-based).
        candidate_names:   Deduped distinct identities produced by this slot.
        findings:          List of finding dicts with keys:
                           candidate, source_class, source_url, evidence_snippet, confidence.
        tactic_used:       id of the tactic that was selected.
        specialist_calls:  Total specialist invocations made.
        metadata:          Arbitrary strategist-level metadata (flags, warnings, etc.).
    """

    slot_idx: int
    candidate_names: list[str] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    tactic_used: str = ""
    specialist_calls: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Technique-id → source_class mapping (UI-P3 propagation)
# ---------------------------------------------------------------------------

# Maps technique catalog ids to the SourceClass values the frontend expects.
# Unmapped technique ids default to "training_knowledge" (safest non-live class).
# TODO(post-MVP): promote this into the Technique catalog schema as a source_class field.
_TECHNIQUE_SOURCE_CLASS: dict[str, str] = {
    "web_search": "live_search",
    "web_search_live": "live_search",
    "news_search": "live_search",
    "news_search_live": "live_search",
    "image_search": "live_search",
    "image_search_live": "live_search",
    "social_media_search": "live_search",
    "official_profile_lookup": "primary_official",
    "agency_roster_lookup": "primary_official",
    "imdb_lookup": "primary_official",
    "social_profile_direct": "primary_self",
    "prior_research_seed": "prior_research",
    "rag_lookup": "prior_research",
    "training_knowledge_recall": "training_knowledge",
}


def _technique_to_source_class(technique_id: str) -> str:
    """Resolve a technique catalog id to its SourceClass string.

    Falls back to "live_search" for any unknown technique whose id ends with
    '_search' or '_live', else "training_knowledge".
    """
    if technique_id in _TECHNIQUE_SOURCE_CLASS:
        return _TECHNIQUE_SOURCE_CLASS[technique_id]
    if technique_id.endswith(("_search", "_live", "_lookup")):
        return "live_search"
    return "training_knowledge"


# ---------------------------------------------------------------------------
# Tactic selection (deterministic, MVP — no LLM call)
# ---------------------------------------------------------------------------

def _phase_compat(tactic) -> list[str]:
    """Tolerate both dict-form and Pydantic-form tactic entries."""
    if hasattr(tactic, "phase_compatibility"):
        return list(tactic.phase_compatibility)
    if isinstance(tactic, dict):
        return list(tactic.get("phase_compatibility", []))
    return []


def _select_tactic(
    slot_idx: int,
    unit_of_work: dict[str, Any],
    tactics_catalog: dict[str, Tactic],
    phase: PhaseSpec,
) -> Tactic | None:
    """Deterministically pick a tactic for this slot.

    Resolution order:
    1. If phase.preferred_tactic_id is set AND in the compatible set, return it.
       (Cross-reference is enforced at startup audit; this runtime check is
       defensive — if audit passed, the override is always compatible.)
    2. slot_idx == 0 AND unit_of_work has a non-empty 'prior_research_summary'
       → prefer 'prior_research_seed' if present in filtered set.
    3. slot_idx >= 1 (or slot 0 without prior_research_summary)
       → prefer 'hypothesis_first_search' if present in filtered set.
    4. Fall back to the first compatible tactic if no preferred id is present.
    5. Returns None if no compatible tactic exists.

    Note: MVP uses deterministic selection. Full design may add LLM tactic
    selection driven by tactic_bias weights from OptimizationMode (§4.4).
    """
    compatible = {
        tid: t for tid, t in tactics_catalog.items()
        if phase.id in _phase_compat(t)
    }
    if not compatible:
        return None

    # NEW: honor strategy author's explicit override first.
    preferred_override = getattr(phase, "preferred_tactic_id", None)
    if preferred_override and preferred_override in compatible:
        return compatible[preferred_override]

    has_prior = bool(unit_of_work.get("prior_research_summary"))
    preferred_id = (
        "prior_research_seed"
        if (slot_idx == 0 and has_prior)
        else "hypothesis_first_search"
    )

    if preferred_id in compatible:
        return compatible[preferred_id]
    # Fallback: first compatible entry in insertion order
    return next(iter(compatible.values()))


# ---------------------------------------------------------------------------
# Prompt builder (subprocess input)
# ---------------------------------------------------------------------------

def _build_tactic_prompt(
    unit_of_work: dict[str, Any],
    tactic: Tactic,
    techniques_catalog: dict[str, Technique],
    model: str,
) -> str:
    """Build the scoped prompt for the tactic subprocess.

    The prompt includes ONLY:
    - unit_of_work fields (briefing, objective, scope_in, scope_out,
      prior_findings_slice, forbidden_candidates)
    - tactic.produces templates (so the brain knows what TaskSpecs to emit)
    - technique catalog entries for tactic.required_techniques

    It does NOT include:
    - Peer tacticians' data
    - Other phases
    - The full original query (only the objective slice)

    TODO(§7.2): This prompt boundary is the information-isolation enforcement
    layer. Any addition here must be reviewed against §7.2 visibility rules.
    """
    lines: list[str] = [
        "# Tactician Unit of Work",
        "",
        f"Objective: {unit_of_work.get('objective', '')}",
        f"Briefing: {unit_of_work.get('briefing', '')}",
        f"Scope in: {unit_of_work.get('scope_in', '')}",
        f"Scope out: {unit_of_work.get('scope_out', '')}",
        "",
    ]

    prior_slice = unit_of_work.get("prior_findings_slice")
    if prior_slice:
        lines += ["## Prior findings (filtered — no raw tool output)", str(prior_slice), ""]

    forbidden = unit_of_work.get("forbidden_candidates", [])
    if forbidden:
        lines += [
            "## FORBIDDEN_CANDIDATES (do not converge on any of these — explicitly investigate alternatives):",
        ]
        for name in forbidden:
            lines.append(f"- {name}")
        lines.append("")

    lines += [
        "# Tactic",
        f"tactic_id: {tactic.id}",
        "",
        "## TaskSpec templates (emit one per technique below)",
    ]
    for prod in tactic.produces:
        lines.append(f"  - technique_id: {prod.technique_id}, params_template: {prod.params_template}")

    lines += ["", "# Required techniques"]
    for tid in tactic.required_techniques:
        tech = techniques_catalog.get(tid)
        if tech:
            lines.append(f"  {tid}: tool={tech.tool_name}, input_schema={tech.input_schema}")
        else:
            lines.append(f"  {tid}: (not found in techniques_catalog)")

    lines += [
        "",
        f"# Model: {model}",
        "Emit tool calls matching the technique ids above. Return findings with fields:",
        "  candidate, source_class, source_url, evidence_snippet, confidence",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Candidate name extraction
# ---------------------------------------------------------------------------

def _extract_candidate_name(finding: dict[str, Any]) -> str | None:
    """Pull the entity/subject/candidate field from a finding dict."""
    for key in ("candidate", "entity", "subject"):
        val = finding.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def execute_tactician(
    phase: PhaseSpec,
    unit_of_work: dict[str, Any],
    slot_idx: int,
    tactics_catalog: dict[str, Tactic],
    techniques_catalog: dict[str, Technique],
    specialist_fn: Callable,
    mcp_invoke_fn: Callable,
    capability_tier: str,
    budget_ru: int,
    tactic_runner_fn: Callable,
) -> TacticianOutput:
    """Execute one tactician scoped to a single hypothesis slot.

    Args:
        phase:              The PhaseSpec this tactician operates in.
        unit_of_work:       Scoped context for this slot (objective, briefing,
                            scope_in, scope_out, prior_findings_slice,
                            forbidden_candidates, prior_research_summary).
        slot_idx:           0-based index of this hypothesis slot.
        tactics_catalog:    Full tactic catalog; filtered internally by phase.id.
        techniques_catalog: Full technique catalog; filtered by tactic.required_techniques.
        specialist_fn:      Injected specialist executor. Signature:
                            (task_spec, technique, mcp_invoke_fn) -> Finding | SpecialistError
        mcp_invoke_fn:      Passed through to specialist_fn unchanged.
        capability_tier:    "light" | "general" | "high" — drives model selection.
        budget_ru:          RU ceiling for this tactician's specialist calls.
        tactic_runner_fn:   Injected subprocess simulator. Signature:
                            (prompt: str, model: str) -> list[dict]
                            Each dict is a task_call: {technique_id, params_template,
                            expect_schema, fail_modes, budget_ru}.
                            In production (M9) this wraps app/is_brain.py subprocess.

    Returns:
        TacticianOutput with aggregated findings and candidate names.

    Visibility invariant (§7.2):
        This function accepts no peer-slot data. The caller (strategist) MUST NOT
        pass sibling tactician state here. The structural guarantee is in the
        signature: there is no peer_findings / peer_outputs parameter.

    TODO(§7.2): M9 integration — wire tactic_runner_fn to the real Claude Code
    subprocess pattern in app/is_brain.py. The prompt built here replaces
    build_prompt(); stream-json parsing and tool_result forwarding follow the
    same asyncio.create_subprocess_exec pattern as run_research().
    """
    model = _CAPABILITY_MODEL_MAP.get(capability_tier, _CAPABILITY_MODEL_MAP["general"])

    # 1. Select tactic
    tactic = _select_tactic(slot_idx, unit_of_work, tactics_catalog, phase)
    if tactic is None:
        log.warning(
            "tactician slot=%d: no compatible tactic for phase=%s — returning empty output",
            slot_idx, phase.id,
        )
        return TacticianOutput(
            slot_idx=slot_idx,
            tactic_used="",
            metadata={"no_tactic_for_phase": True, "phase_id": phase.id},
        )

    # 2. Build scoped prompt
    prompt = _build_tactic_prompt(unit_of_work, tactic, techniques_catalog, model)

    # 3. Run subprocess (injected — real or fake).
    # If the runner returns a coroutine (real Claude Code subprocess), await it.
    # Sync fakes used in tests return list[dict] directly.
    import inspect
    _maybe = tactic_runner_fn(prompt, model)
    if inspect.iscoroutine(_maybe):
        task_calls: list[dict[str, Any]] = await _maybe
    else:
        task_calls = _maybe

    # 4. Process task calls: call specialist, accumulate findings
    findings: list[dict[str, Any]] = []
    candidate_names_seen: set[str] = set()
    specialist_calls = 0
    ru_spent = 0

    # Fast path 0: brain emitted a structured findings JSON block (attached
    # to task_calls[0].structured_findings by scoped_brain). Use those real
    # entity-named findings directly — they're more useful than the
    # query-as-candidate fallback derived from inline_result.
    structured_findings: list[dict[str, Any]] = []
    for tc in task_calls:
        sf = tc.get("structured_findings")
        if sf:
            structured_findings = sf
            break
    if structured_findings:
        resolved_source_class = _technique_to_source_class(
            task_calls[0].get("technique_id", "") if task_calls else ""
        )
        # Tactic semantics: disconfirm_default (and legacy disconfirm_search)
        # produce refutation findings; the strategist's disconfirm gate counts these.
        is_disconfirm_tactic = tactic.id in ("disconfirm_default", "disconfirm_search")
        for sf in structured_findings:
            name = sf.get("candidate") or sf.get("name") or ""
            if not name:
                continue
            findings.append({
                "candidate": name,
                "candidate_name": name,
                "source_class": sf.get("source_class") or resolved_source_class or "live_search",
                "source_url": sf.get("source_url"),
                "evidence_snippet": (sf.get("evidence_snippet") or "")[:1500],
                "confidence": float(sf.get("confidence", 0.6)),
                "date": sf.get("date"),
                "is_disconfirm": bool(sf.get("is_disconfirm", is_disconfirm_tactic)),
            })
            candidate_names_seen.add(name)
        # We still record the task_calls as specialist_calls for accounting
        specialist_calls = len([tc for tc in task_calls if tc.get("technique_id") != "_structured_only"])
        ru_spent = specialist_calls  # 1 RU per tool call

        # Skip the per-task_call loop — structured findings replace it
        task_calls = []

    for task_call in task_calls:
        # Budget gate
        task_ru = task_call.get("budget_ru", 1)
        if ru_spent + task_ru > budget_ru:
            log.info(
                "tactician slot=%d: budget exhausted (spent=%d ceiling=%d), stopping",
                slot_idx, ru_spent, budget_ru,
            )
            break

        technique_id = task_call.get("technique_id", "")
        technique = techniques_catalog.get(technique_id)
        if technique is None:
            log.warning(
                "tactician slot=%d: unknown technique_id=%r in task_call — skipping",
                slot_idx, technique_id,
            )
            continue

        # Fast path: if the scoped subprocess already executed the tool via
        # stdio MCP, the tool_result is carried in task_call["inline_result"].
        # Skip the specialist HTTP re-call and synthesize a Finding directly.
        # See #19 — the brain executed inside the subprocess; we just harvest.
        inline = task_call.get("inline_result")
        if inline:
            resolved_source_class = _technique_to_source_class(technique_id)
            params = task_call.get("params_template", {})
            query_str = (
                params.get("query") or params.get("q") or params.get("name") or ""
            )
            findings.append({
                "candidate": query_str,
                "candidate_name": query_str,
                "source_class": resolved_source_class,
                "source_url": None,
                "evidence_snippet": str(inline)[:1500],
                "confidence": 0.6,
                "date": None,
            })
            specialist_calls += 1
            ru_spent += task_ru
            if query_str:
                candidate_names_seen.add(query_str)
            continue

        task_spec = TaskSpec(
            technique_id=technique_id,
            params_template=task_call.get("params_template", {}),
            expect_schema=task_call.get("expect_schema", {}),
            fail_modes=task_call.get("fail_modes", []),
            budget_ru=task_ru,
        )

        result = specialist_fn(task_spec, technique, mcp_invoke_fn)
        specialist_calls += 1
        ru_spent += task_ru

        # specialist_fn returns Finding or SpecialistError
        from app.pipeline.specialist import Finding

        if isinstance(result, Finding):
            # Annotate with source_class resolved from technique_id → SourceClass map.
            # Both "candidate" and "candidate_name" are set so the strategist's
            # _aggregate() (which looks for "candidate_name") and downstream
            # enrichment (which also uses "candidate_name") both work.
            raw = result.raw_output
            entity_name = (
                raw.get("candidate") or raw.get("entity") or raw.get("subject") or ""
            )
            resolved_source_class = _technique_to_source_class(technique_id)
            finding_entry: dict[str, Any] = {
                "candidate": entity_name,
                "candidate_name": entity_name,
                "source_class": resolved_source_class,
                "source_url": raw.get("url") or raw.get("source_url"),
                "evidence_snippet": raw.get("snippet") or raw.get("evidence_snippet") or "",
                "confidence": raw.get("confidence", 0.0),
                "date": raw.get("date"),
            }
            findings.append(finding_entry)
            name = _extract_candidate_name(finding_entry)
            if name:
                candidate_names_seen.add(name)
        else:
            log.debug(
                "tactician slot=%d: specialist returned error kind=%r for technique=%r",
                slot_idx, result.kind, technique_id,
            )

    # 5. Check enforcement floor (min_distinct_outputs)
    min_distinct = tactic.enforcement.get("min_distinct_outputs")
    if min_distinct and len(candidate_names_seen) < min_distinct:
        log.info(
            "tactician slot=%d: min_distinct_outputs floor=%d not met (got %d) — budget=%d spent=%d",
            slot_idx, min_distinct, len(candidate_names_seen), budget_ru, ru_spent,
        )

    # Derive metadata counters from finding content so phase gates don't
    # silently fail when the brain doesn't populate them itself.
    # This is the fallback contract — brain emissions that DO carry these
    # fields will override these counts via the strategist aggregator.
    findings_count = len(findings)
    live_findings_count = sum(
        1 for f in findings
        if f.get("source_class") in ("live_search", "primary_official")
    )
    disconfirm_findings_count = sum(1 for f in findings if f.get("is_disconfirm"))

    # Phase-specific signal-count derivation:
    # - signal_extraction: the brain analyzes the query (no tool calls expected).
    #   If we got HERE without error, signals were extracted — count as 1.
    # - broaden / red_team / rank_verify: use number of live findings as the
    #   primary-signal proxy. A candidate with a live source counts as a
    #   distinct primary signal evidenced.
    if phase.id == "signal_extraction":
        primary_signals_count = 1
    else:
        primary_signals_count = live_findings_count

    # surviving_hypothesis_count: each red_team tactician is scoped to one
    # surviving hypothesis. For other phases, leave at 0 (gate ignores).
    surviving_hypothesis_count = 1 if phase.id == "red_team" else 0

    return TacticianOutput(
        slot_idx=slot_idx,
        candidate_names=sorted(candidate_names_seen),
        findings=findings,
        tactic_used=tactic.id,
        specialist_calls=specialist_calls,
        metadata={
            "model": model,
            "ru_spent": ru_spent,
            "budget_ru": budget_ru,
            "actual_ru": ru_spent,
            "phase_id": phase.id,
            "enforcement": tactic.enforcement,
            # Derived counters for strategist gate checks (issue #8 contract):
            "findings_count": findings_count,
            "live_findings_count": live_findings_count,
            "disconfirm_findings_count": disconfirm_findings_count,
            "disconfirm_count": disconfirm_findings_count,
            "primary_signals_count": primary_signals_count,
            "surviving_hypothesis_count": surviving_hypothesis_count,
            "hypotheses_explored": 1,
        },
    )
