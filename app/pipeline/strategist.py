"""Strategist runtime — phase DAG executor for the three-tier brain (§7.1, §8).

MVP-M6 (lite): executes phases in dependency order, spawns N parallel tacticians
per phase, evaluates gates, and terminates on gate fail.  No replan logic (deferred
to post-MVP P3 per §10.1).

Design ref: docs/intelligence/three-tier-brain-architecture.md §3, §7.1, §8, §9
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from app.pipeline.catalogs.budget import BudgetEnvelope
from app.pipeline.catalogs.schemas import PhaseSpec, Strategy
from app.pipeline import budget as wallet
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


@dataclass
class RunResult:
    run_id: str
    status: Literal["completed", "terminated", "ask_user"]
    phases: list[PhaseOutput] = field(default_factory=list)
    ranked_candidates: list[dict] = field(default_factory=list)
    terminate_reason: str | None = None
    user_question: str | None = None
    ach_matrix: ACHMatrix | None = None


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


# Dispatch map: check kind → gate function
_GATE_CHECKS: dict[
    str,
    Callable[[PhaseOutput, dict, BudgetEnvelope], bool],
] = {
    "min_primary_signals": _gate_min_primary_signals,
    "distinct_identity_count": _gate_distinct_identity_count,
    "per_hypothesis_live_source": _gate_per_hypothesis_live_source,
    "disconfirm_logged_per_hypothesis": _gate_disconfirm_logged_per_hypothesis,
    "top_candidate_confidence": _gate_top_candidate_confidence,
}


def _run_gate(
    phase_output: PhaseOutput,
    phase: PhaseSpec,
    envelope: BudgetEnvelope,
) -> bool:
    """Return True if all gate checks pass, False otherwise."""
    for check in phase.gate.checks:
        fn = _GATE_CHECKS.get(check.kind)
        if fn is None:
            log.warning("Unknown gate check kind %r — treating as pass", check.kind)
            continue
        if not fn(phase_output, check.params, envelope):
            return False
    return True


# ---------------------------------------------------------------------------
# Ranked candidate enrichment (UI-P3 backend)
# ---------------------------------------------------------------------------

# Source classes that count as "live" for the primary signal heuristic
_PRIMARY_LIVE_CLASSES = frozenset({"live_search", "primary_official"})

# Phases whose findings count as disconfirm evidence
_DISCONFIRM_PHASES = frozenset({"red_team", "disconfirm"})

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
        """
        phases_in_order = _topo_sort(self._strategy.phases)
        completed_phases: list[PhaseOutput] = []
        # Map phase_id → PhaseOutput for downstream unit_of_work construction
        phase_outputs_by_id: dict[str, PhaseOutput] = {}

        for phase_idx, phase in enumerate(phases_in_order):
            unit_of_work = self._build_unit_of_work(
                phase, query, classifier_output, phase_outputs_by_id
            )

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
            def _uow_for_slot(slot_idx: int) -> dict:
                slot_uow = dict(unit_of_work)
                slot_uow["forbidden_candidates"] = forbidden_per_slot[slot_idx]
                return slot_uow

            tactician_tasks = [
                tactician_fn(phase, _uow_for_slot(slot_idx), slot_idx)
                for slot_idx in range(n_tacticians)
            ]
            raw_outputs: list[dict] = await asyncio.gather(*tactician_tasks)

            phase_output = self._aggregate(phase.id, raw_outputs)
            # Audit: record forbidden_per_slot in phase metadata for research_trails
            phase_output.metadata["forbidden_per_slot"] = forbidden_per_slot[:n_tacticians]
            gate_passed = _run_gate(phase_output, phase, self._envelope)

            # Consume RU for this phase regardless of gate outcome
            wallet.consume(
                user_id=self._user_id,
                run_id=self._run_id,
                phase_n=phase_idx,
                actual_ru=phase_output.metadata.get("actual_ru", 1),
                idempotency_key=f"{self._run_id}:phase_{phase.id}:consume",
            )

            completed_phases.append(phase_output)
            phase_outputs_by_id[phase.id] = phase_output

            # Notify the engine layer that this phase has completed its gate check.
            # Fires AFTER gate eval, BEFORE next phase or early return.
            if phase_complete_cb is not None:
                try:
                    if inspect.iscoroutinefunction(phase_complete_cb):
                        await phase_complete_cb(phase, phase_output, gate_passed)
                    else:
                        phase_complete_cb(phase, phase_output, gate_passed)
                except Exception as exc:  # pragma: no cover
                    log.warning("phase_complete_cb raised (non-fatal): %s", exc)

            if not gate_passed:
                on_fail = phase.gate.on_fail

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

                if on_fail == "ask_user":
                    return RunResult(
                        run_id=self._run_id,
                        status="ask_user",
                        phases=completed_phases,
                        user_question=(
                            f"The '{phase.id}' phase could not extract sufficient "
                            f"signals from your query. Could you provide more detail?"
                        ),
                    )

                # "replan" and "swap_tactic" are deferred to post-MVP P3.
                # MVP terminates with a distinct reason so callers can detect it.
                return RunResult(
                    run_id=self._run_id,
                    status="terminated",
                    phases=completed_phases,
                    terminate_reason="replan_required_but_not_implemented",
                )

        # All phases completed — ranked_candidates come from last phase, enriched.
        last = completed_phases[-1] if completed_phases else None
        raw_ranked = last.ranked_candidates if last else []

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

            # Ranked candidates come from the last phase (rank_verify)
            if "ranked_candidates" in output:
                ranked_candidates.extend(output["ranked_candidates"])

        return PhaseOutput(
            phase_id=phase_id,
            aggregated_findings=aggregated,
            distinct_candidate_names=distinct_names,
            metadata=combined_metadata,
            ranked_candidates=ranked_candidates,
        )
