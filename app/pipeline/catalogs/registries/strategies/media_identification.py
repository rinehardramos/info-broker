"""Strategy catalog entry: media_identification — identify an unnamed media subject via ACH.

ACH-shaped — 4-phase backbone identical to person/due_diligence, with
ACH signal weights tuned for media-identity work (primary subject, medium
type, recency, live-source confirmation).

Phases follow the unified taxonomy:
  extract     — parse the query into typed signal hierarchy (PRIMARY/SUPPORTING/CONTEXT)
  gather      — multi-hypothesis live search (preferred: hypothesis_first_search)
  disconfirm  — Heuer ACH refutation pass (preferred: disconfirm_default)
  synthesize  — ACH matrix ranking (preferred: ach_rank)

Migrated from the legacy 4-phase ACH backbone (signal_extraction →
broaden → red_team → rank_verify) per spec 2026-05-23.

Used when the user provides a description-only query with no named subject
and wants to identify the specific show, film, advertisement, celebrity, or
other media entity being described. The competing-hypothesis floor prevents
collapse onto a single training-data candidate.

Design ref: docs/intelligence/three-tier-brain-architecture.md §4.1, §8, §9
"""
from __future__ import annotations

from app.pipeline.catalogs.builders.research_skeleton import build_research_strategy


STRATEGY = build_research_strategy(
    id="media_identification",
    default_mode="investigation",
    hypothesis_count="competing",
    applies_to={
        "signals": [
            "description_signals_only",
            "no_named_subject",
            "identification_intent",
        ],
        "entity_types": ["celebrity", "media", "advertisement"],
    },
    ach_signals=[
        {"id": "primary",     "label": "Primary subject match",  "weight": 0.40, "penalty_on_mismatch": 0.30},
        {"id": "supporting",  "label": "Supporting detail match", "weight": 0.25, "penalty_on_mismatch": 0.15},
        {"id": "medium",      "label": "Medium type match",       "weight": 0.15, "penalty_on_mismatch": 0.25},
        {"id": "recency",     "label": "Recency match",           "weight": 0.10, "penalty_on_mismatch": 0.10},
        {"id": "live_source", "label": "Has live source",         "weight": 0.10, "penalty_on_mismatch": 0.05},
    ],
    extract={
        "briefing": (
            "Parse the raw query into a typed signal hierarchy: PRIMARY (grammatical subject), "
            "SUPPORTING (defining detail), and CONTEXT (franchise/IP/platform). "
            "Do not recall or name any candidate yet — signal extraction only. "
            "Classify the intended medium (show, film, advertisement) from any PreFlight "
            "clarifications. Output a signal dict and a PIR criteria block with weights."
        ),
        "gate_checks": [
            {
                "kind": "min_primary_signals",
                "params": {"min": 1},
            }
        ],
        "on_fail": "ask_user",
    },
    gather={
        "preferred_tactic_id": "hypothesis_first_search",
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
        "hypothesis_count_policy": "from_dial",
        "gate_checks": [
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
    disconfirm={
        "inputs": ["surviving_hypotheses_from_gather"],
        "briefing": (
            "For each surviving hypothesis, run at least one active disconfirmation search — "
            "seek evidence that falsifies the hypothesis, not confirms it. "
            "Log a [DISCONFIRM:H_n] entry with the search used, what was found, and the score impact. "
            "Record the ACH matrix row for this hypothesis (✓/✗/? per PIR signal). "
            "Do not advance without a disconfirm entry per hypothesis."
        ),
        "hypothesis_count_policy": "from_prior_phase",
        "gate_checks": [
            {
                "kind": "disconfirm_logged_per_hypothesis",
                "params": {},
            }
        ],
        "on_fail": "terminate",
    },
    synthesize={
        "preferred_tactic_id": "ach_rank",
        "inputs": [
            "ach_inputs_from_disconfirm",
            "pir_criteria_from_extract",
        ],
        "briefing": (
            "Score each hypothesis against PIR criteria using ACH penalty weighting. "
            "Verify PRIMARY and SUPPORTING signals for the top candidate; cap confidence at 40% if "
            "PRIMARY is unverified. Return a ranked result with all considered candidates in "
            "alternatives_considered. If top candidate confidence < 0.4, escalate to user for "
            "disambiguation rather than committing to a low-confidence answer."
        ),
        "gate_checks": [
            {
                "kind": "top_candidate_confidence",
                "params": {"min": 0.4},
            }
        ],
        "on_fail": "ask_user",
    },
)
