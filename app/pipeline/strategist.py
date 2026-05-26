"""Strategist runtime — phase DAG executor for the three-tier brain (§7.1, §8).

MVP-M6 (lite): executes phases in dependency order, spawns N parallel tacticians
per phase, evaluates gates, and terminates on gate fail.  No replan logic (deferred
to post-MVP P3 per §10.1).

Design ref: docs/intelligence/three-tier-brain-architecture.md §3, §7.1, §8, §9
"""
from __future__ import annotations

import asyncio
import inspect
import os
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal, TypedDict

from app.pipeline.catalogs.budget import BudgetEnvelope
from app.pipeline.catalogs.schemas import PhaseSpec, Strategy
from app.pipeline import budget as wallet
from app.security import sanitize_check_detail
from app.pipeline.ach import (
    ACHSignal,
    ACHMatrix,
    compute_ach_matrix,
    ach_matrix_to_signal_scores,
    ach_matrix_to_dict,
    DEFAULT_ACH_SIGNALS,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Depth dial → replan budget (§5.2, §8.2 P3)
# ---------------------------------------------------------------------------

DEPTH_TO_REPLAN_BUDGET: dict[str, int] = {
    "shallow": 0,
    "search": 1,
    "deep": 3,
    "abyss": 99,  # effectively unlimited; cu_ceiling caps it
}

# ---------------------------------------------------------------------------
# Hypothesis-count dial → integer mapping (§5.2.3)
# ---------------------------------------------------------------------------

_HYPOTHESIS_COUNT_INT: dict[str, int] = {
    "single": 1,
    "paired": 2,
    "competing": 3,
    "adversarial": 5,
    "swarm": 8,
}


def _resolve_hypothesis_count(dial_value: str) -> int:
    return _HYPOTHESIS_COUNT_INT.get(dial_value, 3)


# ---------------------------------------------------------------------------
# Forbidden-candidates allocation (P4 — §11, §12 Q2 RESOLVED, §9)
# ---------------------------------------------------------------------------

_FORBIDDEN_ACTIVATION_THRESHOLD = 3  # competing and above
_FORBIDDEN_PRIOR_CAP = 5             # never forbid more than 5 priors per slot


def _compute_forbidden_per_slot(
    priors: dict,
    hypothesis_count_int: int,
) -> list[list[str]]:
    """Compute forbidden_candidates per tactician slot from priors only.

    Slot 0: empty (verifies the obvious H_PRIOR candidate).
    Slot 1: forbid top-1 prior.
    Slot N: forbid top-N priors.

    Priors are deduped from rag_hits + classifier_top_candidates, capped at 5.
    Activates only when hypothesis_count_int >= 3 (competing tier).
    When below threshold, all slots return empty lists so single/paired runs
    are unaffected and H_PRIOR is still tested at slot 0.

    Args:
        priors: {
            "rag_hits": [...],                   # candidate names from prior research / RAG
            "classifier_top_candidates": [...],  # candidate names from classifier LLM peek
        }
        hypothesis_count_int: resolved int from _resolve_hypothesis_count.

    Returns:
        list of length hypothesis_count_int; each element is a list[str].
    """
    if hypothesis_count_int < _FORBIDDEN_ACTIVATION_THRESHOLD:
        return [[] for _ in range(hypothesis_count_int)]

    # Dedupe while preserving order: rag_hits first, then classifier additions
    seen: set[str] = set()
    ordered: list[str] = []
    for name in list(priors.get("rag_hits", [])) + list(priors.get("classifier_top_candidates", [])):
        if isinstance(name, str) and name.strip() and name not in seen:
            seen.add(name)
            ordered.append(name)

    # Cap at _FORBIDDEN_PRIOR_CAP
    ordered = ordered[:_FORBIDDEN_PRIOR_CAP]

    slots: list[list[str]] = []
    for slot_idx in range(hypothesis_count_int):
        if slot_idx == 0:
            # Slot 0 always empty — verifies H_PRIOR
            slots.append([])
        else:
            # Slot N forbids top-N priors
            slots.append(ordered[:slot_idx])

    return slots


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class PhaseOutput:
    """Aggregated output from all tacticians for one phase.

    Only aggregated findings cross phase boundaries — raw tool results stay
    inside tactician memory (§7.1 visibility invariant).
    """

    phase_id: str
    aggregated_findings: list[dict]        # whitelisted keys only; no raw_tool_output
    distinct_candidate_names: list[str]
    metadata: dict = field(default_factory=dict)
    ranked_candidates: list[dict] = field(default_factory=list)
    gate_result: "GateResult | None" = None    # populated by _run_gate


@dataclass
class RunResult:
    run_id: str
    status: Literal["completed", "terminated", "ask_user"]
    phases: list[PhaseOutput] = field(default_factory=list)
    ranked_candidates: list[dict] = field(default_factory=list)
    terminate_reason: str | None = None
    user_question: "UserQuestionPayload | None" = None    # was: str | None
    ach_matrix: ACHMatrix | None = None


# ---------------------------------------------------------------------------
# Gate result types (spec: 2026-05-22-gather-ask-user-diagnostic-design.md)
# ---------------------------------------------------------------------------


class BrainSummary(TypedDict):
    tool_calls: int
    findings: int
    hypothesis_count: int       # surviving hypothesis count
    duration_ms: int            # phase wall-clock
    invoked_tools: list[str]    # distinct MCP / built-in tools touched, truncated to top 10


class GateResult(TypedDict):
    passed: bool
    failing_check_kind: str | None
    failing_check_detail: dict        # sanitized; see app/security.py:sanitize_check_detail
    brain_summary: BrainSummary


class UserQuestionPayload(TypedDict):
    summary: str           # user-safe; never blames the query
    detail: GateResult     # admin-only; emitted only via gate-detail endpoint
    run_id: str
    phase_id: str


_USER_QUESTION_SUMMARIES: dict[str, str] = {
    "no_brain_work": (
        "The system didn't gather any results for this query. "
        "This may be a temporary issue — please try again or contact support."
    ),
    "min_listings_returned": (
        "We couldn't find listings matching your criteria. "
        "Try broadening location or budget."
    ),
    "min_signal_classes_covered": (
        "Not enough information was gathered to answer this query. "
        "Please try a more specific query."
    ),
    # Strategy authors may extend; missing kinds use the fallback below.
}


def _build_user_question_summary(failing_check_kind: str | None, phase_id: str) -> str:
    if failing_check_kind and failing_check_kind in _USER_QUESTION_SUMMARIES:
        return _USER_QUESTION_SUMMARIES[failing_check_kind]
    # Fallback per spec — only substitutes phase_id, never check internals.
    return (
        f"We couldn't complete the '{phase_id}' phase for this query. "
        f"Please try a more specific query or contact support."
    )


# ---------------------------------------------------------------------------
# Whitelisted finding keys (visibility invariant enforcement)
# ---------------------------------------------------------------------------

# Keys tactician outputs may place in findings that are permitted to cross
# phase boundaries.  raw_tool_output and any other non-whitelisted keys are
# stripped during aggregation so the strategist never sees raw tool results.
_FINDING_WHITELIST = frozenset(
    [
        "candidate_name",
        "source_class",
        "source_url",
        "evidence_snippet",
        "confidence",
        "evidence_summary",
        "hypothesis_slot",
        "technique_id",
        "signals_matched",
        "disconfirm_logged",
        "date",
        "phase_id",
    ]
)


def _strip_finding(raw: dict[str, Any]) -> dict[str, Any]:
    """Return only whitelisted keys from a tactician finding dict."""
    return {k: v for k, v in raw.items() if k in _FINDING_WHITELIST}


# ---------------------------------------------------------------------------
# Topological sort (Kahn's algorithm)
# ---------------------------------------------------------------------------


def _topo_sort(phases: list[PhaseSpec]) -> list[PhaseSpec]:
    """Return phases in topological execution order.

    Cycles should have been caught at Strategy load time (schemas.py).
    Raises RuntimeError defensively if a cycle is detected at runtime.
    """
    phase_map = {p.id: p for p in phases}
    in_degree: dict[str, int] = {p.id: 0 for p in phases}
    adjacency: dict[str, list[str]] = {p.id: [] for p in phases}

    for phase in phases:
        for dep in phase.depends_on:
            adjacency[dep].append(phase.id)
            in_degree[phase.id] += 1

    queue = [pid for pid, deg in in_degree.items() if deg == 0]
    order: list[PhaseSpec] = []

    while queue:
        node = queue.pop(0)
        order.append(phase_map[node])
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(phases):
        raise RuntimeError("Cycle detected in strategy phase DAG at runtime")

    return order


# ---------------------------------------------------------------------------
# Gate check functions (§8.1)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Bounded fan-out — memory-safe parallel tactician spawning (#113)
# ---------------------------------------------------------------------------
#
# Each tactician slot spawns a Claude Code subprocess (~300 MB resident).
# At mem_limit=1g the container OOM-kills if >3-4 run concurrently. The
# unbounded ``asyncio.gather`` fan-out used previously hit this when
# disconfirm had 10+ surviving hypotheses (15 disconfirm slots in one run).
# This semaphore-bounded helper keeps peak concurrency at a configurable N.

_DEFAULT_MAX_PARALLEL_TACTICIANS = int(os.getenv("MAX_PARALLEL_TACTICIANS", "3"))


async def gather_bounded(
    awaitables: list, max_concurrent: int = _DEFAULT_MAX_PARALLEL_TACTICIANS,
) -> list:
    """asyncio.gather but with peak concurrency capped at ``max_concurrent``.

    Order of results matches the input order. Exceptions propagate exactly
    like ``asyncio.gather`` (first-error wins). ``max_concurrent <= 0`` falls
    back to unbounded gather for defensive safety on misconfiguration.
    """
    if not awaitables:
        return []
    if max_concurrent <= 0:
        return await asyncio.gather(*awaitables)

    sem = asyncio.Semaphore(max_concurrent)

    async def _bounded(coro):
        async with sem:
            return await coro

    return await asyncio.gather(*(_bounded(a) for a in awaitables))


def _gate_min_primary_signals(
    phase_output: PhaseOutput, params: dict, envelope: BudgetEnvelope
) -> bool:
    min_required = params.get("min", 1)
    return phase_output.metadata.get("primary_signals_count", 0) >= min_required


def _gate_distinct_identity_count(
    phase_output: PhaseOutput, params: dict, envelope: BudgetEnvelope
) -> bool:
    if params.get("min_from_dial"):
        min_required = _resolve_hypothesis_count(envelope.hypothesis_count)
    else:
        min_required = params.get("min", 1)
    return len(phase_output.distinct_candidate_names) >= min_required


def _gate_per_hypothesis_live_source(
    phase_output: PhaseOutput, params: dict, envelope: BudgetEnvelope
) -> bool:
    """Every distinct candidate must have at least min findings with a live source class.

    Findings whose source_class is 'prior_research' or 'training_knowledge' do NOT
    satisfy this gate — structural fix for the #89 RAG-anchor failure mode.
    """
    min_live = params.get("min", 1)
    if not phase_output.distinct_candidate_names:
        return False

    live_source_classes = {"prior_research", "training_knowledge"}

    # Group live-source findings per candidate
    live_per_candidate: dict[str, int] = {
        name: 0 for name in phase_output.distinct_candidate_names
    }
    for finding in phase_output.aggregated_findings:
        candidate = finding.get("candidate_name")
        source_class = finding.get("source_class", "")
        if candidate in live_per_candidate and source_class not in live_source_classes:
            live_per_candidate[candidate] += 1

    return all(count >= min_live for count in live_per_candidate.values())


def _gate_disconfirm_logged_per_hypothesis(
    phase_output: PhaseOutput, params: dict, envelope: BudgetEnvelope
) -> bool:
    disconfirm_count = phase_output.metadata.get("disconfirm_count", 0)
    surviving = phase_output.metadata.get("surviving_hypothesis_count", 0)
    return disconfirm_count >= surviving


def _gate_top_candidate_confidence(
    phase_output: PhaseOutput, params: dict, envelope: BudgetEnvelope
) -> bool:
    min_confidence = params.get("min", 0.4)
    if not phase_output.ranked_candidates:
        return False
    return phase_output.ranked_candidates[0].get("confidence", 0.0) >= min_confidence


# ---------------------------------------------------------------------------
# Skeleton-strategy gate check kinds (extract → gather → synthesize)
# ---------------------------------------------------------------------------
#
# The 8 strategies built atop research_skeleton (real_estate, lead, company,
# place, generation, explanation, prediction, synthesis) each declare a
# domain-specific gate check kind. These functions implement them.
#
# All are intentionally generic — they enforce "the brain returned SOMETHING
# usable" not "the brain returned the right thing". The strategies' briefings
# already describe the domain expectations; the gate checks only catch the
# no-op pattern (0 findings, 0 sources, 0 distinct results) which is what
# turns the strategy into theatre.


def _gate_min_listings_returned(
    phase_output: PhaseOutput, params: dict, envelope: BudgetEnvelope
) -> bool:
    """real_estate.gather — ≥N findings returned."""
    return len(phase_output.aggregated_findings) >= params.get("min", 1)


def _gate_contact_info_per_target(
    phase_output: PhaseOutput, params: dict, envelope: BudgetEnvelope
) -> bool:
    """lead.gather — at least ``min`` finding(s) per declared target.

    Every name in distinct_candidate_names must appear as candidate_name on
    at least ``min`` findings. Empty candidate list = no targets = fail.
    """
    if not phase_output.distinct_candidate_names:
        return False
    min_per = params.get("min", 1)
    counts: dict[str, int] = {n: 0 for n in phase_output.distinct_candidate_names}
    for f in phase_output.aggregated_findings:
        name = f.get("candidate_name")
        if name in counts:
            counts[name] += 1
    return all(c >= min_per for c in counts.values())


def _gate_min_signal_classes_covered(
    phase_output: PhaseOutput, params: dict, envelope: BudgetEnvelope
) -> bool:
    """company.gather — ≥N distinct source_class values across findings."""
    classes = {
        f.get("source_class") for f in phase_output.aggregated_findings
        if f.get("source_class")
    }
    return len(classes) >= params.get("min", 1)


# Coordinate-like patterns: "lat=40.7 lon=-74.0", "40.7,-74.0", "lat: 40.7".
# Loose on purpose — the brain may format coords in any of several ways.
import re as _re
_COORD_RE = _re.compile(
    r"(?:lat(?:itude)?\s*[:=]\s*[+-]?\d+(?:\.\d+)?)|"
    r"(?:[-+]?\d{1,3}\.\d+\s*[,\s]\s*[-+]?\d{1,3}\.\d+)",
    _re.IGNORECASE,
)


def _gate_coordinates_present(
    phase_output: PhaseOutput, params: dict, envelope: BudgetEnvelope
) -> bool:
    """place.gather — at least one finding mentions resolved coordinates."""
    for f in phase_output.aggregated_findings:
        haystack = " ".join(
            str(f.get(k, "")) for k in
            ("evidence_summary", "evidence_snippet", "candidate_name")
        )
        if _COORD_RE.search(haystack):
            return True
    return False


def _gate_min_options_with_rationale(
    phase_output: PhaseOutput, params: dict, envelope: BudgetEnvelope
) -> bool:
    """generation.synthesize — ≥N distinct options proposed.

    Default ``min`` is 2 (a single option isn't a "comparison of options").
    """
    return len(phase_output.distinct_candidate_names) >= params.get("min", 2)


def _gate_min_mechanisms_with_support(
    phase_output: PhaseOutput, params: dict, envelope: BudgetEnvelope
) -> bool:
    """explanation.synthesize — ≥N mechanism candidates, each with ≥1 source URL."""
    if not phase_output.distinct_candidate_names:
        return False
    with_source: set[str] = set()
    for f in phase_output.aggregated_findings:
        name = f.get("candidate_name")
        if name in phase_output.distinct_candidate_names and f.get("source_url"):
            with_source.add(name)
    return len(with_source) >= params.get("min", 2)


def _gate_confidence_band_present(
    phase_output: PhaseOutput, params: dict, envelope: BudgetEnvelope
) -> bool:
    """prediction.synthesize — at least one finding signals confidence.

    Accepts either an explicit ``confidence`` float field OR a textual
    mention of confidence/probability/likelihood/band in evidence text.
    """
    text_hints = ("confidence", "probability", "likelihood", "band", "%")
    for f in phase_output.aggregated_findings:
        if isinstance(f.get("confidence"), (int, float)):
            return True
        text = " ".join(
            str(f.get(k, "")) for k in ("evidence_summary", "evidence_snippet")
        ).lower()
        if any(h in text for h in text_hints):
            return True
    return False


def _gate_min_sources_synthesized(
    phase_output: PhaseOutput, params: dict, envelope: BudgetEnvelope
) -> bool:
    """synthesis.synthesize — ≥N distinct (non-empty) source URLs across findings."""
    urls = {
        f.get("source_url") for f in phase_output.aggregated_findings
        if f.get("source_url")
    }
    return len(urls) >= params.get("min", 3)


# Dispatch map: check kind → gate function
_GATE_CHECKS: dict[
    str,
    Callable[[PhaseOutput, dict, BudgetEnvelope], bool],
] = {
    # ACH-shaped strategies
    "min_primary_signals": _gate_min_primary_signals,
    "distinct_identity_count": _gate_distinct_identity_count,
    "per_hypothesis_live_source": _gate_per_hypothesis_live_source,
    "disconfirm_logged_per_hypothesis": _gate_disconfirm_logged_per_hypothesis,
    "top_candidate_confidence": _gate_top_candidate_confidence,
    # Skeleton-shaped strategies (real_estate, lead, company, place,
    # generation, explanation, prediction, synthesis)
    "min_listings_returned": _gate_min_listings_returned,
    "contact_info_per_target": _gate_contact_info_per_target,
    "min_signal_classes_covered": _gate_min_signal_classes_covered,
    "coordinates_present": _gate_coordinates_present,
    "min_options_with_rationale": _gate_min_options_with_rationale,
    "min_mechanisms_with_support": _gate_min_mechanisms_with_support,
    "confidence_band_present": _gate_confidence_band_present,
    "min_sources_synthesized": _gate_min_sources_synthesized,
}


# ---------------------------------------------------------------------------
# Startup audit — catch misconfigured strategies before they reach prod
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateAuditViolation:
    """A strategy declared a gate-check kind the runtime can't resolve.

    The strategist would fail-OPEN at runtime (treating unknown kinds as
    pass), so the gate becomes documentation instead of enforcement —
    runs report 'succeeded' with zero work done.
    """
    strategy_id: str
    phase_id: str
    unknown_kind: str


def audit_strategy_gates(
    strategies: dict[str, Any],
    registered_kinds: set[str] | None = None,
) -> list[GateAuditViolation]:
    """Walk every strategy's gate.checks; return violations for unknown kinds.

    Called once at app startup. ``strategies`` accepts either Pydantic
    ``Strategy`` objects (from load_catalog) or raw dicts (matching
    the catalog file shape) — both expose phases[].gate.checks[].kind.
    """
    if registered_kinds is None:
        registered_kinds = set(_GATE_CHECKS)
    violations: list[GateAuditViolation] = []
    for sid, s in strategies.items():
        phases = _phases_of(s)
        for phase in phases:
            phase_id = _phase_id(phase)
            for check in _checks_of(phase):
                kind = _check_kind(check)
                if kind not in registered_kinds:
                    violations.append(GateAuditViolation(
                        strategy_id=sid, phase_id=phase_id, unknown_kind=kind,
                    ))
    return violations


def _phases_of(strategy: Any) -> list:
    p = getattr(strategy, "phases", None)
    if p is not None:
        return p
    if isinstance(strategy, dict):
        return strategy.get("phases", [])
    return []


def _phase_id(phase: Any) -> str:
    pid = getattr(phase, "id", None)
    if pid is not None:
        return pid
    if isinstance(phase, dict):
        return phase.get("id", "?")
    return "?"


def _checks_of(phase: Any) -> list:
    gate = getattr(phase, "gate", None)
    if gate is None and isinstance(phase, dict):
        gate = phase.get("gate", {})
    if gate is None:
        return []
    checks = getattr(gate, "checks", None)
    if checks is not None:
        return checks
    if isinstance(gate, dict):
        return gate.get("checks", [])
    return []


def _check_kind(check: Any) -> str:
    kind = getattr(check, "kind", None)
    if kind is not None:
        return kind
    if isinstance(check, dict):
        return check.get("kind", "?")
    return "?"


def _build_brain_summary(phase_output: PhaseOutput) -> "BrainSummary":
    """Extract the brain-activity summary from a PhaseOutput's metadata.

    Tacticians attach `tool_calls`, `invoked_tools`, and `duration_ms` to the
    aggregated phase metadata. `findings` is len(aggregated_findings). The
    `invoked_tools` list is truncated to the first 10 if longer.
    """
    md = phase_output.metadata
    invoked = list(md.get("invoked_tools") or [])
    if len(invoked) > 10:
        invoked = invoked[:10]
    return {
        "tool_calls": int(md.get("tool_calls", 0) or 0),
        "findings": len(phase_output.aggregated_findings or []),
        "hypothesis_count": int(md.get("surviving_hypothesis_count", 0) or 0),
        "duration_ms": int(md.get("duration_ms", 0) or 0),
        "invoked_tools": invoked,
    }


def _run_gate(
    phase_output: PhaseOutput,
    phase: PhaseSpec,
    envelope: BudgetEnvelope,
) -> "GateResult":
    """Evaluate gate checks and return a GateResult dict.

    Invariant (top-level, checked before per-strategy checks):
        A phase with tool_calls == 0 AND findings == 0 cannot pass.
        This prevents a strategy author who forgot to declare gate checks
        from silently shipping a zero-work phase as "succeeded".

    Unknown check kinds are logged at ERROR and treated as **failed** —
    a misconfigured strategy with a phantom check kind would otherwise
    auto-pass every gate, producing the "succeeded with 0 work" no-op
    pattern. The audit at startup (audit_strategy_gates) is the
    primary line of defense; this is the runtime backstop.
    """
    brain_summary = _build_brain_summary(phase_output)

    # Top-level invariant: both tool_calls AND findings must be zero to trip.
    # EXCEPT: phases whose tactic declared enforcement.no_tool_calls_required=True
    # (e.g. extract_default / synthesize_default / ach_rank — pure analysis tactics).
    # These legitimately have 0 tool_calls by design; the invariant was meant for
    # the "wrong tactic catalog → silent no-op" pattern, not for analysis phases.
    # Per-strategy gate checks (min_primary_signals, min_signal_classes_covered, etc.)
    # are still applied below to catch real analysis failures.
    no_tools_phase = bool(phase_output.metadata.get("no_tool_calls_required"))
    if (
        brain_summary["tool_calls"] == 0
        and brain_summary["findings"] == 0
        and not no_tools_phase
    ):
        return {
            "passed": False,
            "failing_check_kind": "no_brain_work",
            "failing_check_detail": sanitize_check_detail(
                {"tool_calls": 0, "findings": 0}
            ),
            "brain_summary": brain_summary,
        }

    # Per-strategy checks — preserve fail-CLOSED behavior on unknown kinds.
    for check in phase.gate.checks:
        kind = check.kind
        fn = _GATE_CHECKS.get(kind)
        if fn is None:
            log.error(
                "GATE_CONFIG_ERROR: unknown gate check kind %r on phase %r — "
                "failing the gate. Add the kind to _GATE_CHECKS or remove it "
                "from the strategy catalog. (Was fail-OPEN before; flipped to "
                "fail-CLOSED because the no-op bug took ~36h to surface.)",
                kind, phase.id,
            )
            return {
                "passed": False,
                "failing_check_kind": f"unknown:{kind}",
                "failing_check_detail": sanitize_check_detail(
                    {"check": kind, "params": getattr(check, "params", {})}
                ),
                "brain_summary": brain_summary,
            }
        params = getattr(check, "params", {})
        ok = fn(phase_output, params, envelope)
        if not ok:
            return {
                "passed": False,
                "failing_check_kind": kind,
                "failing_check_detail": sanitize_check_detail(
                    {"check": kind, "params": params}
                ),
                "brain_summary": brain_summary,
            }

    return {
        "passed": True,
        "failing_check_kind": None,
        "failing_check_detail": {},
        "brain_summary": brain_summary,
    }


# ---------------------------------------------------------------------------
# Ranked candidate enrichment (UI-P3 backend)
# ---------------------------------------------------------------------------

# Source classes that count as "live" for the primary signal heuristic
_PRIMARY_LIVE_CLASSES = frozenset({"live_search", "primary_official", "live_official"})

# Phases whose findings count as disconfirm evidence.
# Legacy id red_team is kept for historical DB rows; allowlist 2026-05-23.
# The 2026-05-23 taxonomy rename means new rows use disconfirm.
_DISCONFIRM_PHASES = frozenset({"red_team", "disconfirm"})  # allowlist 2026-05-23: legacy phase id for historical research_trails rows

# Years within which a finding's date field is considered "recent"
_RECENCY_YEARS = 2


def _build_ach_signals_from_strategy(strategy_id: str) -> list[ACHSignal]:
    """Return ACHSignal list from strategy catalog ach_signals field if available.

    Falls back to DEFAULT_ACH_SIGNALS if the strategy has no ach_signals entry
    or the strategy_id is not loaded here (catalog loading happens in engine_v2).
    """
    return list(DEFAULT_ACH_SIGNALS)


def _enrich_ranked_candidates(
    raw_ranked: list[dict],
    all_phase_outputs: list["PhaseOutput"],
    strategy_id: str = "",
    ach_signals: list[ACHSignal] | None = None,
) -> tuple[list[dict], ACHMatrix | None]:
    """Enrich raw ranked_candidates with signal_scores (ACH-derived), evidence[], and slot_idx.

    P5: Replaces the heuristic MVP signal_scores with a full Heuer ACH matrix.
    signal_scores is still emitted for backward compat with UI-P3 RankedCandidate type.
    Derives signal_scores from ACH cells: consistent→match, inconsistent→mismatch,
    neutral/unknown→unknown.

    Args:
        raw_ranked:        List of raw candidate dicts from the last phase output.
                           Each must have at least {"name": str, "confidence": float}.
        all_phase_outputs: All PhaseOutput objects for this run, in execution order.
        strategy_id:       Strategy id (e.g. "media_identification") for medium check.
        ach_signals:       Optional list of ACHSignal overrides from strategy catalog.

    Returns:
        Tuple of (enriched_candidates, ach_matrix).
        enriched_candidates: List of enriched dicts matching the RankedCandidate type.
        ach_matrix: The full ACHMatrix (or None if no candidates).
    """
    if not raw_ranked:
        return [], None

    # Flatten all findings across all phases into one list, tagged with phase_id.
    all_findings: list[dict[str, Any]] = []
    for phase_output in all_phase_outputs:
        for finding in phase_output.aggregated_findings:
            tagged = dict(finding)
            # Prefer the stored phase_id field; fall back to the PhaseOutput id.
            if "phase_id" not in tagged:
                tagged["phase_id"] = phase_output.phase_id
            all_findings.append(tagged)

    # Build a name → lowest slot_idx map from hypothesis_slot field.
    name_to_slot: dict[str, int] = {}
    for finding in all_findings:
        name = finding.get("candidate_name", "")
        if not name:
            continue
        slot = finding.get("hypothesis_slot")
        if slot is None:
            continue
        try:
            slot_int = int(slot)
        except (TypeError, ValueError):
            continue
        if name not in name_to_slot or slot_int < name_to_slot[name]:
            name_to_slot[name] = slot_int

    # --- Build per-candidate finding maps ---
    hypothesis_names = [raw.get("name", "") for raw in raw_ranked if raw.get("name")]

    findings_by_candidate: dict[str, list[dict]] = {name: [] for name in hypothesis_names}
    disconfirm_findings_by_candidate: dict[str, list[dict]] = {name: [] for name in hypothesis_names}

    for f in all_findings:
        candidate = f.get("candidate_name", "")
        if candidate not in findings_by_candidate:
            continue
        if f.get("phase_id", "") in _DISCONFIRM_PHASES:
            disconfirm_findings_by_candidate[candidate].append(f)
        else:
            findings_by_candidate[candidate].append(f)

    # --- Compute ACH matrix ---
    signals = ach_signals if ach_signals else _build_ach_signals_from_strategy(strategy_id)
    matrix = compute_ach_matrix(
        hypothesis_names=hypothesis_names,
        findings_by_candidate=findings_by_candidate,
        disconfirm_findings_by_candidate=disconfirm_findings_by_candidate,
        signals=signals,
        phase_outputs=all_phase_outputs,
        strategy_id=strategy_id,
    )

    enriched: list[dict] = []
    for idx, raw in enumerate(raw_ranked):
        name = raw.get("name", "")
        confidence = raw.get("confidence", 0.0)

        # signal_scores derived from ACH cells (backward compat with UI-P3)
        signal_scores = ach_matrix_to_signal_scores(matrix, name)

        # --- evidence[] ---
        candidate_findings = findings_by_candidate.get(name, []) + disconfirm_findings_by_candidate.get(name, [])
        evidence: list[dict] = []
        for f in candidate_findings:
            snippet = f.get("evidence_snippet") or f.get("evidence_summary") or ""
            source_class = f.get("source_class", "training_knowledge")
            source_url = f.get("source_url")
            is_disconfirm = f.get("phase_id", "") in _DISCONFIRM_PHASES
            entry: dict[str, Any] = {
                "source_class": source_class,
                "snippet": snippet,
                "is_disconfirm": is_disconfirm,
            }
            if source_url:
                entry["source_url"] = source_url
            evidence.append(entry)

        # Sort: supporting evidence first, then disconfirm.
        evidence.sort(key=lambda e: (1 if e["is_disconfirm"] else 0))

        # --- slot_idx ---
        slot_idx = name_to_slot.get(name, idx)

        enriched.append({
            "name": name,
            "confidence": confidence,
            "signal_scores": signal_scores,
            "evidence": evidence,
            "slot_idx": slot_idx,
        })

    return enriched, matrix


# ---------------------------------------------------------------------------
# Strategist
# ---------------------------------------------------------------------------


class Strategist:
    """Phase DAG executor — the 'general' in the three-tier architecture.

    Responsibilities (MVP-M6 scope):
    - Topologically sort strategy phases.
    - Determine n_tacticians per phase from hypothesis_count_policy.
    - Spawn tacticians in parallel via asyncio.gather.
    - Aggregate outputs into PhaseOutput (stripping non-whitelisted keys).
    - Evaluate gates; terminate on failure (no replan in MVP).
    - Call wallet.consume() after each completed phase.

    Does NOT see: raw tool results, peer-tactician findings, candidate names
    mid-phase (only aggregated post-phase).
    """

    def __init__(
        self,
        strategy: Strategy,
        envelope: BudgetEnvelope,
        run_id: str,
        user_id: str,
        hold_id: str,
    ) -> None:
        self._strategy = strategy
        self._envelope = envelope
        self._run_id = run_id
        self._user_id = user_id
        self._hold_id = hold_id

    async def execute(
        self,
        query: str,
        classifier_output: dict,
        tactician_fn: Callable,
        phase_complete_cb: Callable | None = None,
        event_emit: Callable | None = None,
    ) -> RunResult:
        """Run the phase DAG and return a RunResult.

        Args:
            query:             The sanitized user query (entity signals only).
            classifier_output: Dict output from the query classifier.
            tactician_fn:      Async callable with signature
                               ``(phase, unit_of_work, slot_idx) -> dict``.
                               Injected for testability; M7's runtime is plugged
                               in at wiring time.  Tests use a fake implementation.
            phase_complete_cb: Optional async callable invoked after each phase's
                               gate has been evaluated, with signature
                               ``(phase, phase_output, gate_passed) -> None``.
                               Fires AFTER the gate check and wallet.consume but
                               BEFORE the next phase begins (or early return).
            event_emit:        Optional async callable for emitting is.phase_replan
                               events. When None, replan events are silently dropped.
        """
        phases_in_order = _topo_sort(self._strategy.phases)
        completed_phases: list[PhaseOutput] = []
        # Map phase_id → PhaseOutput for downstream unit_of_work construction
        phase_outputs_by_id: dict[str, PhaseOutput] = {}

        max_replans = DEPTH_TO_REPLAN_BUDGET.get(self._envelope.depth, 1)
        # tactics_catalog is loaded from the catalog registries for tactic swap.
        # Loaded lazily so tests that don't exercise swap_tactic pay no overhead.
        _tactics_catalog: dict | None = None

        def _get_tactics_catalog() -> dict:
            nonlocal _tactics_catalog
            if _tactics_catalog is None:
                try:
                    from pathlib import Path as _P
                    from app.pipeline.catalogs.loader import load_catalog
                    _base = _P(__file__).parent / "catalogs" / "registries" / "tactics"
                    _tactics_catalog = load_catalog("tactic", _base)
                except Exception as exc:
                    log.warning("strategist: could not load tactics catalog for swap: %s", exc)
                    _tactics_catalog = {}
            return _tactics_catalog

        for phase_idx, phase in enumerate(phases_in_order):
            replan_attempts = 0
            tactics_used_this_phase: list[str] = []
            # current_unit_of_work may be augmented with corrective_hint on replan
            current_unit_of_work: dict | None = None

            while True:
                unit_of_work = self._build_unit_of_work(
                    phase, query, classifier_output, phase_outputs_by_id
                )
                # Overlay corrective hint and tactic override from prior attempts
                if current_unit_of_work is not None:
                    if "corrective_hint" in current_unit_of_work:
                        unit_of_work["corrective_hint"] = current_unit_of_work["corrective_hint"]
                    if "_tactic_override" in current_unit_of_work:
                        unit_of_work["_tactic_override"] = current_unit_of_work["_tactic_override"]
                    if "user_directive" in current_unit_of_work:
                        unit_of_work["user_directive"] = current_unit_of_work["user_directive"]
                current_unit_of_work = unit_of_work

                # Drain any mid-run user instructions injected via POST /v3/runs/{run_id}/inject
                # and merge them into user_directive so the brain prompt receives them.
                from app.pipeline.runners import injection_queue as _injection_queue
                _directives = _injection_queue.drain(self._run_id)
                if _directives:
                    existing = unit_of_work.get("user_directive", "")
                    unit_of_work["user_directive"] = (
                        existing + "\n" + "\n".join(_directives)
                    ).strip()
                    # Also update current_unit_of_work so the directive survives replan
                    current_unit_of_work["user_directive"] = unit_of_work["user_directive"]

                n_tacticians = self._resolve_n_tacticians(
                    phase, phase_outputs_by_id
                )

                # P4: forbidden_per_slot was pre-computed in _build_unit_of_work.
                # Inject the per-slot slice into a copy of unit_of_work so each
                # tactician sees only its own forbidden list (no cross-slot leakage).
                forbidden_per_slot: list[list[str]] = unit_of_work.get("forbidden_per_slot", [])
                # Extend with empty lists if n_tacticians exceeds pre-computed length
                # (can happen when from_prior_phase grows beyond hypothesis_count_int).
                while len(forbidden_per_slot) < n_tacticians:
                    forbidden_per_slot.append([])

                # Spawn tacticians in parallel; visibility invariant enforced by
                # limiting the tactician_fn signature to (phase, unit_of_work, slot_idx).
                # Each slot receives a shallow copy with forbidden_candidates injected.
                def _uow_for_slot(slot_idx: int, _uow: dict = unit_of_work) -> dict:
                    slot_uow = dict(_uow)
                    slot_uow["forbidden_candidates"] = forbidden_per_slot[slot_idx]
                    return slot_uow

                try:
                    tactician_tasks = [
                        tactician_fn(phase, _uow_for_slot(slot_idx), slot_idx)
                        for slot_idx in range(n_tacticians)
                    ]
                    # Bounded by MAX_PARALLEL_TACTICIANS (default 3) so we
                    # don't OOM the container under high hypothesis counts.
                    # See gather_bounded() docstring + #113.
                    raw_outputs: list[dict] = await gather_bounded(tactician_tasks)
                except Exception as exc:
                    # Subprocess/runtime error counts as a consumed attempt.
                    log.exception(
                        "strategist: phase '%s' attempt %d raised: %s",
                        phase.id, replan_attempts, exc,
                    )
                    raw_outputs = []

                phase_output = self._aggregate(phase.id, raw_outputs)
                # Audit: record forbidden_per_slot in phase metadata for research_trails
                phase_output.metadata["forbidden_per_slot"] = forbidden_per_slot[:n_tacticians]
                # Audit: record replan attempt number for research_trails
                phase_output.metadata["replan_attempt"] = replan_attempts

                gate_result = _run_gate(phase_output, phase, self._envelope)
                log.info(
                    "strategist.gate_result",
                    extra={
                        "run_id": self._run_id,
                        "phase_id": phase.id,
                        "gate_passed": gate_result["passed"],
                        "failing_check_kind": gate_result["failing_check_kind"],
                        "tool_calls": gate_result["brain_summary"]["tool_calls"],
                        "findings": gate_result["brain_summary"]["findings"],
                        "duration_ms": gate_result["brain_summary"]["duration_ms"],
                        "replan_attempt": phase_output.metadata.get("replan_attempt", 0),
                    },
                )
                phase_output.gate_result = gate_result
                gate_passed = gate_result["passed"]

                if gate_passed:
                    # Consume RU for this phase
                    wallet.consume(
                        user_id=self._user_id,
                        run_id=self._run_id,
                        phase_n=phase_idx,
                        actual_ru=phase_output.metadata.get("actual_ru", 1),
                        idempotency_key=f"{self._run_id}:phase_{phase.id}:attempt_{replan_attempts}:consume",
                    )

                    completed_phases.append(phase_output)
                    phase_outputs_by_id[phase.id] = phase_output

                    if phase_complete_cb is not None:
                        try:
                            if inspect.iscoroutinefunction(phase_complete_cb):
                                await phase_complete_cb(phase, phase_output, True)
                            else:
                                phase_complete_cb(phase, phase_output, True)
                        except Exception as exc:  # pragma: no cover
                            log.warning("phase_complete_cb raised (non-fatal): %s", exc)
                    break  # next phase

                # Gate failed — consume RU for the failed attempt
                wallet.consume(
                    user_id=self._user_id,
                    run_id=self._run_id,
                    phase_n=phase_idx,
                    actual_ru=phase_output.metadata.get("actual_ru", 1),
                    idempotency_key=f"{self._run_id}:phase_{phase.id}:attempt_{replan_attempts}:consume",
                )

                on_fail = phase.gate.on_fail

                # ask_user escalates immediately — no replan regardless of depth
                if on_fail == "ask_user":
                    completed_phases.append(phase_output)
                    phase_outputs_by_id[phase.id] = phase_output
                    if phase_complete_cb is not None:
                        try:
                            if inspect.iscoroutinefunction(phase_complete_cb):
                                await phase_complete_cb(phase, phase_output, False)
                            else:
                                phase_complete_cb(phase, phase_output, False)
                        except Exception as exc:  # pragma: no cover
                            log.warning("phase_complete_cb raised (non-fatal): %s", exc)
                    gate_result = phase_output.gate_result or {
                        "passed": False,
                        "failing_check_kind": None,
                        "failing_check_detail": {},
                        "brain_summary": _build_brain_summary(phase_output),
                    }
                    payload: UserQuestionPayload = {
                        "summary": _build_user_question_summary(gate_result["failing_check_kind"], phase.id),
                        "detail": gate_result,
                        "run_id": self._run_id,
                        "phase_id": phase.id,
                    }
                    return RunResult(
                        run_id=self._run_id,
                        status="ask_user",
                        phases=completed_phases,
                        user_question=payload,
                    )

                if replan_attempts >= max_replans:
                    # Replan budget exhausted — honour original on_fail
                    completed_phases.append(phase_output)
                    phase_outputs_by_id[phase.id] = phase_output
                    if phase_complete_cb is not None:
                        try:
                            if inspect.iscoroutinefunction(phase_complete_cb):
                                await phase_complete_cb(phase, phase_output, False)
                            else:
                                phase_complete_cb(phase, phase_output, False)
                        except Exception as exc:  # pragma: no cover
                            log.warning("phase_complete_cb raised (non-fatal): %s", exc)

                    if on_fail == "terminate":
                        return RunResult(
                            run_id=self._run_id,
                            status="terminated",
                            phases=completed_phases,
                            terminate_reason=(
                                f"Gate failed on phase '{phase.id}': "
                                f"checks did not pass"
                            ),
                        )
                    # replan / swap_tactic budget exhausted
                    return RunResult(
                        run_id=self._run_id,
                        status="terminated",
                        phases=completed_phases,
                        terminate_reason=(
                            f"Replan budget exhausted on phase '{phase.id}' "
                            f"after {replan_attempts} attempt(s)"
                        ),
                    )

                # Decide replan strategy and prepare next attempt
                failing_check_kind = (phase_output.gate_result or {}).get("failing_check_kind") or "unknown"
                replan_strategy: str

                if on_fail == "replan":
                    hint = self._compute_corrective_hint(phase, phase_output, failing_check_kind)
                    current_unit_of_work["corrective_hint"] = hint
                    replan_strategy = "hint_added"

                elif on_fail == "swap_tactic":
                    tactics_catalog = _get_tactics_catalog()
                    current_tactic_id = current_unit_of_work.get("_tactic_override") or ""
                    if current_tactic_id:
                        tactics_used_this_phase.append(current_tactic_id)
                    alt = self._pick_alternative_tactic(
                        phase, tactics_used_this_phase, tactics_catalog
                    )
                    if alt is None:
                        completed_phases.append(phase_output)
                        phase_outputs_by_id[phase.id] = phase_output
                        if phase_complete_cb is not None:
                            try:
                                if inspect.iscoroutinefunction(phase_complete_cb):
                                    await phase_complete_cb(phase, phase_output, False)
                                else:
                                    phase_complete_cb(phase, phase_output, False)
                            except Exception as exc:  # pragma: no cover
                                log.warning("phase_complete_cb raised (non-fatal): %s", exc)
                        return RunResult(
                            run_id=self._run_id,
                            status="terminated",
                            phases=completed_phases,
                            terminate_reason="no_alt_tactic_available",
                        )
                    current_unit_of_work["_tactic_override"] = alt.id
                    tactics_used_this_phase.append(alt.id)
                    replan_strategy = "swap_tactic"

                else:
                    # on_fail == "terminate" — no replans possible
                    completed_phases.append(phase_output)
                    phase_outputs_by_id[phase.id] = phase_output
                    if phase_complete_cb is not None:
                        try:
                            if inspect.iscoroutinefunction(phase_complete_cb):
                                await phase_complete_cb(phase, phase_output, False)
                            else:
                                phase_complete_cb(phase, phase_output, False)
                        except Exception as exc:  # pragma: no cover
                            log.warning("phase_complete_cb raised (non-fatal): %s", exc)
                    return RunResult(
                        run_id=self._run_id,
                        status="terminated",
                        phases=completed_phases,
                        terminate_reason=(
                            f"Gate failed on phase '{phase.id}': "
                            f"checks did not pass"
                        ),
                    )

                replan_attempts += 1

                # Emit is.phase_replan event (auditable in research_trails)
                if event_emit is not None:
                    try:
                        replan_event = {
                            "type": "is.phase_replan",
                            "run_id": self._run_id,
                            "phase_id": phase.id,
                            "attempt": replan_attempts,
                            "max_attempts": max_replans,
                            "reason": failing_check_kind,
                            "strategy": replan_strategy,
                        }
                        if inspect.iscoroutinefunction(event_emit):
                            await event_emit(replan_event)
                        else:
                            event_emit(replan_event)
                    except Exception as exc:  # pragma: no cover
                        log.warning("strategist: event_emit for phase_replan failed: %s", exc)

                log.info(
                    "strategist: phase '%s' replan attempt %d/%d strategy=%s reason=%s",
                    phase.id, replan_attempts, max_replans, replan_strategy, failing_check_kind,
                )

        # All phases completed — ranked_candidates come from last phase, enriched.
        last = completed_phases[-1] if completed_phases else None
        raw_ranked = last.ranked_candidates if last else []

        # If synthesize is a pure-analysis tactic (no tool calls, no
        # produces), it won't populate ranked_candidates directly. Fall
        # back to deriving the candidate list from the GATHER phase's
        # distinct_candidate_names (those are the hypotheses that entered
        # disconfirm). _enrich_ranked_candidates then computes ACH scores
        # from the aggregated_findings across all phases.
        if not raw_ranked:
            for p in completed_phases:
                if p.phase_id == "gather" and p.distinct_candidate_names:
                    raw_ranked = [
                        {"name": name, "confidence": 0.5}
                        for name in p.distinct_candidate_names
                    ]
                    break

        # Resolve ach_signals from strategy catalog entry (additive field, default empty)
        ach_signals_dicts = getattr(self._strategy, "ach_signals", []) or []
        ach_signals: list[ACHSignal] | None = None
        if ach_signals_dicts:
            ach_signals = [
                ACHSignal(
                    id=s["id"],
                    label=s["label"],
                    weight=float(s["weight"]),
                    penalty_on_mismatch=float(s["penalty_on_mismatch"]),
                )
                for s in ach_signals_dicts
            ]

        ranked, ach_matrix = _enrich_ranked_candidates(
            raw_ranked=raw_ranked,
            all_phase_outputs=completed_phases,
            strategy_id=self._strategy.id,
            ach_signals=ach_signals,
        )

        return RunResult(
            run_id=self._run_id,
            status="completed",
            phases=completed_phases,
            ranked_candidates=ranked,
            ach_matrix=ach_matrix,
        )

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _build_unit_of_work(
        self,
        phase: PhaseSpec,
        query: str,
        classifier_output: dict,
        phase_outputs_by_id: dict[str, PhaseOutput],
    ) -> dict:
        """Build the unit_of_work dict for a phase.

        Only AGGREGATED findings from prior phases are included — never raw tool
        results (§7.1).  The unit_of_work_contract template is merged with
        resolved prior-phase aggregates.

        For phases with from_dial hypothesis_count_policy, forbidden_candidates
        is computed per-slot from classifier priors (P4 §11/§12).  The full
        forbidden_per_slot list is embedded so the fan-out loop can inject the
        correct slice per slot_idx.
        """
        uow: dict[str, Any] = dict(phase.unit_of_work_contract)
        uow["query"] = query
        uow["classifier_output"] = classifier_output

        prior_aggregates: dict[str, Any] = {}
        for dep_id in phase.depends_on:
            prior = phase_outputs_by_id.get(dep_id)
            if prior is not None:
                prior_aggregates[dep_id] = {
                    "aggregated_findings": prior.aggregated_findings,
                    "distinct_candidate_names": prior.distinct_candidate_names,
                    "metadata": prior.metadata,
                }

        if prior_aggregates:
            uow["prior_phase_aggregates"] = prior_aggregates

        # P4: pre-compute forbidden_per_slot so the fan-out loop can inject
        # the right slice per slot_idx.  Only computed once per phase; the
        # loop reads uow["forbidden_per_slot"][slot_idx].
        priors = {
            "rag_hits": classifier_output.get("rag_hits", []),
            "classifier_top_candidates": classifier_output.get("classifier_top_candidates", []),
        }
        hypothesis_count_int = _resolve_hypothesis_count(self._envelope.hypothesis_count)
        forbidden_per_slot = _compute_forbidden_per_slot(priors, hypothesis_count_int)
        uow["forbidden_per_slot"] = forbidden_per_slot

        return uow

    def _resolve_n_tacticians(
        self,
        phase: PhaseSpec,
        phase_outputs_by_id: dict[str, PhaseOutput],
    ) -> int:
        policy = phase.hypothesis_count_policy

        if policy == "from_dial":
            return _resolve_hypothesis_count(self._envelope.hypothesis_count)

        if policy.startswith("fixed:"):
            try:
                return int(policy.split(":", 1)[1])
            except (IndexError, ValueError):
                return 1

        if policy == "from_prior_phase":
            # Use count of distinct candidates surviving from immediate parent
            for dep_id in reversed(phase.depends_on):
                prior = phase_outputs_by_id.get(dep_id)
                if prior is not None:
                    count = len(prior.distinct_candidate_names)
                    return max(1, count)
            return 1

        log.warning("Unknown hypothesis_count_policy %r, defaulting to 1", policy)
        return 1

    def _aggregate(self, phase_id: str, raw_outputs: list[dict]) -> PhaseOutput:
        """Collapse tactician outputs into a PhaseOutput.

        Strips non-whitelisted keys so raw_tool_output never crosses phase
        boundaries (visibility invariant, §7.1).
        """
        aggregated: list[dict] = []
        distinct_names: list[str] = []
        combined_metadata: dict[str, Any] = {
            "num_tacticians": len(raw_outputs),
            "hypotheses_explored": 0,
            "primary_signals_count": 0,
            "disconfirm_count": 0,
            "surviving_hypothesis_count": 0,
            "actual_ru": 0,
            # True iff every tactician for this phase ran a tactic that declared
            # enforcement.no_tool_calls_required=True. The no_brain_work invariant
            # in _run_gate honors this — extract/synthesize phases shouldn't fail
            # the invariant just because they (by design) have 0 tool_calls.
            "no_tool_calls_required": True if raw_outputs else False,
        }
        ranked_candidates: list[dict] = []

        for slot_pos, output in enumerate(raw_outputs):
            if not isinstance(output, dict):
                continue

            # slot_idx from the tactician output; fall back to enumeration index.
            slot_idx: int = output.get("slot_idx", slot_pos)

            # Aggregate findings (whitelist enforced per finding)
            for finding in output.get("findings", []):
                if isinstance(finding, dict):
                    # Inject hypothesis_slot and phase_id before stripping so they
                    # survive the whitelist (both are whitelisted).
                    annotated = dict(finding)
                    if "hypothesis_slot" not in annotated:
                        annotated["hypothesis_slot"] = slot_idx
                    if "phase_id" not in annotated:
                        annotated["phase_id"] = phase_id
                    clean = _strip_finding(annotated)
                    aggregated.append(clean)
                    candidate = finding.get("candidate_name")
                    if candidate and candidate not in distinct_names:
                        distinct_names.append(candidate)

            # Merge metadata counters
            meta = output.get("metadata", {})
            # If ANY tactician ran a tools-using tactic, the phase is NOT
            # "no_tool_calls_required" overall. Default the per-tactician value
            # to False (a tactic without an enforcement dict, or one with no
            # no_tool_calls_required key, is assumed to expect tool calls).
            tactic_enforcement = meta.get("enforcement") or {}
            per_tactician_no_tools = bool(tactic_enforcement.get("no_tool_calls_required"))
            if not per_tactician_no_tools:
                combined_metadata["no_tool_calls_required"] = False
            combined_metadata["hypotheses_explored"] += meta.get(
                "hypotheses_explored", 0
            )
            combined_metadata["primary_signals_count"] += meta.get(
                "primary_signals_count", 0
            )
            combined_metadata["disconfirm_count"] += meta.get("disconfirm_count", 0)
            combined_metadata["surviving_hypothesis_count"] += meta.get(
                "surviving_hypothesis_count", 0
            )
            combined_metadata["actual_ru"] += meta.get("actual_ru", 1)

            # Ranked candidates come from the last phase (synthesize)
            if "ranked_candidates" in output:
                ranked_candidates.extend(output["ranked_candidates"])

        return PhaseOutput(
            phase_id=phase_id,
            aggregated_findings=aggregated,
            distinct_candidate_names=distinct_names,
            metadata=combined_metadata,
            ranked_candidates=ranked_candidates,
        )

    # -----------------------------------------------------------------------
    # P3 Replan helpers
    # -----------------------------------------------------------------------

    def _compute_corrective_hint(
        self,
        phase: PhaseSpec,
        phase_output: PhaseOutput,
        failing_check_kind: str,
    ) -> str:
        """Return a corrective hint string for the next replan attempt.

        The hint is inserted into unit_of_work["corrective_hint"] so that
        _build_scoped_prompt includes it verbatim before the briefing.
        """
        if failing_check_kind == "distinct_identity_count":
            required = _resolve_hypothesis_count(self._envelope.hypothesis_count)
            names = ", ".join(phase_output.distinct_candidate_names) or "(none)"
            n = len(phase_output.distinct_candidate_names)
            return (
                f"Previous attempt produced only {n} distinct identities ({names}). "
                f"Generate at least {required} alternatives with different identity names."
            )
        if failing_check_kind == "per_hypothesis_live_source":
            return (
                "Previous findings relied on prior_research only. "
                "Run live searches for each hypothesis with web_search/google_news/image_search."
            )
        if failing_check_kind == "disconfirm_logged_per_hypothesis":
            # Identify hypotheses missing disconfirm entries
            disconfirm_count = phase_output.metadata.get("disconfirm_count", 0)
            surviving = phase_output.metadata.get("surviving_hypothesis_count", 0)
            missing = max(0, surviving - disconfirm_count)
            names = ", ".join(phase_output.distinct_candidate_names) or "(unknown)"
            return (
                f"Need disconfirm search for: {names}. "
                f"({missing} hypothesis(es) missing a disconfirmation entry.)"
            )
        # Generic fallback
        return (
            f"Previous attempt failed gate '{failing_check_kind}'. "
            f"Retry with corrective focus."
        )

    def _pick_alternative_tactic(
        self,
        phase: PhaseSpec,
        tactics_used: list[str],
        tactics_catalog: dict,
    ):
        """Return the next compatible tactic not yet used in this phase, or None.

        Selection criteria:
        1. phase.id in tactic.phase_compatibility
        2. tactic.id not in tactics_used
        3. Prefer cost_class "cheap" first; then "moderate"; then "expensive"

        Returns the Tactic object (from catalog) or None if no alternative found.
        """
        from app.pipeline.catalogs.schemas import Tactic as _Tactic

        cost_order = {"cheap": 0, "moderate": 1, "expensive": 2}
        candidates = []

        for tactic_id, tactic in tactics_catalog.items():
            if tactic_id in tactics_used:
                continue
            # Support both Tactic schema objects and raw dicts (catalog may return either)
            if isinstance(tactic, dict):
                compat = tactic.get("phase_compatibility", [])
                cost = tactic.get("cost_class", "moderate")
                tactic_id_actual = tactic.get("id", tactic_id)
            else:
                compat = getattr(tactic, "phase_compatibility", [])
                cost = getattr(tactic, "cost_class", "moderate")
                tactic_id_actual = getattr(tactic, "id", tactic_id)

            if phase.id not in compat:
                continue
            if tactic_id_actual in tactics_used:
                continue

            candidates.append((cost_order.get(cost, 1), tactic))

        if not candidates:
            return None

        candidates.sort(key=lambda t: t[0])
        return candidates[0][1]
