"""Strategist runtime — phase DAG executor for the three-tier brain (§7.1, §8).

MVP-M6 (lite): executes phases in dependency order, spawns N parallel tacticians
per phase, evaluates gates, and terminates on gate fail.  No replan logic (deferred
to post-MVP P3 per §10.1).

Design ref: docs/intelligence/three-tier-brain-architecture.md §3, §7.1, §8, §9
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from app.pipeline.catalogs.budget import BudgetEnvelope
from app.pipeline.catalogs.schemas import PhaseSpec, Strategy
from app.pipeline import budget as wallet

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
        "confidence",
        "evidence_summary",
        "hypothesis_slot",
        "technique_id",
        "signals_matched",
        "disconfirm_logged",
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
    ) -> RunResult:
        """Run the phase DAG and return a RunResult.

        Args:
            query:             The sanitized user query (entity signals only).
            classifier_output: Dict output from the query classifier.
            tactician_fn:      Async callable with signature
                               ``(phase, unit_of_work, slot_idx) -> dict``.
                               Injected for testability; M7's runtime is plugged
                               in at wiring time.  Tests use a fake implementation.
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

            # Spawn tacticians in parallel; visibility invariant enforced by
            # limiting the tactician_fn signature to (phase, unit_of_work, slot_idx)
            tactician_tasks = [
                tactician_fn(phase, unit_of_work, slot_idx)
                for slot_idx in range(n_tacticians)
            ]
            raw_outputs: list[dict] = await asyncio.gather(*tactician_tasks)

            phase_output = self._aggregate(phase.id, raw_outputs)
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

        # All phases completed — ranked_candidates come from last phase
        last = completed_phases[-1] if completed_phases else None
        ranked = last.ranked_candidates if last else []

        return RunResult(
            run_id=self._run_id,
            status="completed",
            phases=completed_phases,
            ranked_candidates=ranked,
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

        for output in raw_outputs:
            if not isinstance(output, dict):
                continue

            # Aggregate findings (whitelist enforced per finding)
            for finding in output.get("findings", []):
                if isinstance(finding, dict):
                    clean = _strip_finding(finding)
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
