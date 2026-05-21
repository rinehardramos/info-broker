"""Strategy catalog entry: person.

ACH-shaped (signal_extraction → broaden → red_team → rank_verify) — same
backbone as media_identification but tuned for person investigation:
identity matching by name parts + role + employer + location + time.

Used when the user wants to investigate / disambiguate / profile a
specific human. The competing-hypothesis floor prevents collapse onto a
single training-data candidate, which is the typical failure mode for
common names (multiple "John Smith"s, etc).

Design ref: docs/intelligence/three-tier-brain-architecture.md §4.1, §8, §9
"""
from __future__ import annotations

STRATEGY = {
    "id": "person",
    "ach_signals": [
        # Primary identity — name parts, photo if attached. Heaviest weight
        # because name is the disambiguator-of-last-resort.
        {"id": "identity",   "label": "Name / identity match",     "weight": 0.35, "penalty_on_mismatch": 0.30},
        # Role + employer narrows common names; this is the secondary key.
        {"id": "role",       "label": "Role / employer match",     "weight": 0.25, "penalty_on_mismatch": 0.20},
        # Location adds geo grounding. Lower weight because people move.
        {"id": "location",   "label": "Location / jurisdiction",   "weight": 0.15, "penalty_on_mismatch": 0.15},
        # Time period: when the user thinks the person was active.
        {"id": "recency",    "label": "Active during time period", "weight": 0.10, "penalty_on_mismatch": 0.10},
        # Live source ensures we're not just recalling training data.
        {"id": "live_source", "label": "Has live source",          "weight": 0.15, "penalty_on_mismatch": 0.10},
    ],
    "applies_to": {
        "signals": [
            "investigate",
            "find_person",
            "who_is",
            "background_check",
            "research_person",
        ],
        "entity_types": ["person"],
    },
    "default_mode": "investigation",
    "budget_minimums": {
        # Anti-tunneling floor — common names need competing hypotheses or
        # the first training-data recall wins by default.
        "hypothesis_count": "competing",
    },
    "phases": [
        {
            "id": "signal_extraction",
            "depends_on": [],
            "unit_of_work_contract": {
                "inputs": ["query", "classifier_output"],
                "briefing": (
                    "Parse the query into a typed identity signal hierarchy. "
                    "PRIMARY: name parts (first, middle, last, nicknames). "
                    "SUPPORTING: role/title/employer, jurisdiction or location, "
                    "time period the user means. CONTEXT: industry, project, "
                    "or relationship context. Do not recall any specific person "
                    "yet — extraction only. Output a signal dict + PIR criteria "
                    "with weights matching ach_signals."
                ),
            },
            "hypothesis_count_policy": "fixed:1",
            "gate": {
                "checks": [
                    {"kind": "min_primary_signals", "params": {"min": 1}},
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
                    "Generate N distinct candidate persons matching the signal "
                    "hierarchy — different real individuals, not variations of "
                    "one. For common names this is the critical step: do NOT "
                    "collapse on the most-famous candidate from training data. "
                    "Each candidate must be backed by at least one live search "
                    "(LinkedIn, news, registry, etc) before the phase closes. "
                    "forbidden_candidates (priors) must not be proposed as the "
                    "primary hypothesis."
                ),
            },
            "hypothesis_count_policy": "from_dial",
            "gate": {
                "checks": [
                    {"kind": "distinct_identity_count", "params": {"min_from_dial": True}},
                    {"kind": "per_hypothesis_live_source", "params": {"min": 1}},
                ],
                "on_fail": "terminate",
            },
        },
        {
            "id": "red_team",
            "depends_on": ["broaden"],
            "unit_of_work_contract": {
                "inputs": ["surviving_hypotheses_from_broaden"],
                "briefing": (
                    "For each candidate person, run an active disconfirmation "
                    "search. Try to falsify identity (wrong employer at the "
                    "time, wrong jurisdiction, wrong age band, wrong role) "
                    "rather than confirm it. Log a [DISCONFIRM:H_n] entry per "
                    "candidate with the search used and what was found. Record "
                    "the ACH matrix row (✓/✗/?) per PIR signal."
                ),
            },
            "hypothesis_count_policy": "from_prior_phase",
            "gate": {
                "checks": [
                    {"kind": "disconfirm_logged_per_hypothesis", "params": {}},
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
                    "Score each candidate against PIR criteria with ACH "
                    "penalty weighting. Verify the identity (name + role + "
                    "employer) of the top candidate against ≥1 independent "
                    "live source before committing. Cap confidence at 40% if "
                    "identity is unverified. Return ranked result with full "
                    "alternatives_considered. Confidence < 0.4 → escalate to "
                    "user with the top 2-3 candidates rather than commit."
                ),
            },
            "hypothesis_count_policy": "fixed:1",
            "gate": {
                "checks": [
                    {"kind": "top_candidate_confidence", "params": {"min": 0.4}},
                ],
                "on_fail": "ask_user",
            },
        },
    ],
}
