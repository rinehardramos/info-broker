"""Strategy catalog entry for media_identification.

This is the structured Phase DAG version of the strategy.
The prose version at app/pipeline/strategies/media_identification.py
remains intact and is used by the tactician as a briefing reference.

Design ref: docs/intelligence/three-tier-brain-architecture.md §4.1, §8, §9
"""
from __future__ import annotations

STRATEGY = {
    "id": "media_identification",
    "ach_signals": [
        {"id": "primary", "label": "Primary subject match", "weight": 0.40, "penalty_on_mismatch": 0.30},
        {"id": "supporting", "label": "Supporting detail match", "weight": 0.25, "penalty_on_mismatch": 0.15},
        {"id": "medium", "label": "Medium type match", "weight": 0.15, "penalty_on_mismatch": 0.25},
        {"id": "recency", "label": "Recency match", "weight": 0.10, "penalty_on_mismatch": 0.10},
        {"id": "live_source", "label": "Has live source", "weight": 0.10, "penalty_on_mismatch": 0.05},
    ],
    "applies_to": {
        "signals": [
            "description_signals_only",
            "no_named_subject",
            "identification_intent",
        ],
        "entity_types": ["celebrity", "media", "advertisement"],
    },
    "default_mode": "investigation",
    "budget_minimums": {
        # Hard floor: competing (3-4 hypotheses) is the ACH baseline per §5.2.3.
        # Structural fix for #89 — prevents single-hypothesis tunneling.
        "hypothesis_count": "competing",
    },
    "phases": [
        {
            "id": "signal_extraction",
            "depends_on": [],
            "unit_of_work_contract": {
                "inputs": ["query", "classifier_output"],
                "briefing": (
                    "Parse the raw query into a typed signal hierarchy: PRIMARY (grammatical subject), "
                    "SUPPORTING (defining detail), and CONTEXT (franchise/IP/platform). "
                    "Do not recall or name any candidate yet — signal extraction only. "
                    "Classify the intended medium (show, film, advertisement) from any PreFlight "
                    "clarifications. Output a signal dict and a PIR criteria block with weights."
                ),
            },
            "hypothesis_count_policy": "fixed:1",
            "gate": {
                "checks": [
                    {
                        "kind": "min_primary_signals",
                        "params": {"min": 1},
                    }
                ],
                "on_fail": "ask_user",
            },
        },
        {
            "id": "broaden",
            "depends_on": ["signal_extraction"],
            "unit_of_work_contract": {
                "inputs": [
                    "signals",
                    "prior_research_summary",
                    "forbidden_candidates",
                ],
                "briefing": (
                    "Generate N competing hypotheses from signals only — no training-data candidate recall, "
                    "no RAG anchoring. Each hypothesis must name a DISTINCT identity (different person/entity). "
                    "If prior_research names a candidate, it seeds H_PRIOR as one slot among N, NOT the answer. "
                    "Execute at least one live search per hypothesis before the phase closes. "
                    "Forbidden_candidates (from strategist priors) must not be proposed as a primary hypothesis."
                ),
            },
            "hypothesis_count_policy": "from_dial",
            "gate": {
                "checks": [
                    {
                        "kind": "distinct_identity_count",
                        "params": {"min_from_dial": True},
                    },
                    {
                        "kind": "per_hypothesis_live_source",
                        "params": {"min": 1},
                    },
                ],
                # MVP: terminate on gate fail — replan deferred to post-MVP (§10.1 replan/recurse cut)
                "on_fail": "terminate",
            },
        },
        {
            "id": "red_team",
            "depends_on": ["broaden"],
            "unit_of_work_contract": {
                "inputs": ["surviving_hypotheses_from_broaden"],
                "briefing": (
                    "For each surviving hypothesis, run at least one active disconfirmation search — "
                    "seek evidence that falsifies the hypothesis, not confirms it. "
                    "Log a [DISCONFIRM:H_n] entry with the search used, what was found, and the score impact. "
                    "Record the ACH matrix row for this hypothesis (✓/✗/? per PIR signal). "
                    "Do not advance without a disconfirm entry per hypothesis."
                ),
            },
            "hypothesis_count_policy": "from_prior_phase",
            "gate": {
                "checks": [
                    {
                        "kind": "disconfirm_logged_per_hypothesis",
                        "params": {},
                    }
                ],
                "on_fail": "terminate",
            },
        },
        {
            "id": "rank_verify",
            "depends_on": ["red_team"],
            "unit_of_work_contract": {
                "inputs": [
                    "ach_inputs_from_red_team",
                    "pir_criteria_from_signal_extraction",
                ],
                "briefing": (
                    "Score each hypothesis against PIR criteria using ACH penalty weighting. "
                    "Verify PRIMARY and SUPPORTING signals for the top candidate; cap confidence at 40% if "
                    "PRIMARY is unverified. Return a ranked result with all considered candidates in "
                    "alternatives_considered. If top candidate confidence < 0.4, escalate to user for "
                    "disambiguation rather than committing to a low-confidence answer."
                ),
            },
            "hypothesis_count_policy": "fixed:1",
            "gate": {
                "checks": [
                    {
                        "kind": "top_candidate_confidence",
                        "params": {"min": 0.4},
                    }
                ],
                "on_fail": "ask_user",
            },
        },
    ],
}
