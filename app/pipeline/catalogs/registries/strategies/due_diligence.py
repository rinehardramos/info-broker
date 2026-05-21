"""Strategy catalog entry: due_diligence.

ACH-shaped (signal_extraction → broaden → red_team → rank_verify) — same
backbone as person, with the ACH signal weights re-balanced for KYC/AML
work. Identity matching is still primary, but adverse-media / watchlist /
sanctions signals carry equal weight: a confident identity match means
nothing if the entity is on a sanctions list and we missed it.

Used for: KYC checks, AML screens, sanctions/PEP screening, vendor
risk assessment, journalist background checks.

Design ref: docs/intelligence/three-tier-brain-architecture.md §4.1, §8, §9
"""
from __future__ import annotations

STRATEGY = {
    "id": "due_diligence",
    "ach_signals": [
        # Identity is still primary — wrong-entity findings invalidate every
        # downstream risk signal.
        {"id": "identity",    "label": "Entity identity match",       "weight": 0.30, "penalty_on_mismatch": 0.35},
        # Watchlist / sanctions hit — high-stakes signal. Penalty for FALSE
        # positives is intentionally high because actioning a wrong hit is
        # costly and embarrassing.
        {"id": "watchlist",   "label": "Watchlist / sanctions hit",   "weight": 0.25, "penalty_on_mismatch": 0.30},
        # Adverse media — public reporting of misconduct, litigation, etc.
        {"id": "adverse_media", "label": "Adverse media coverage",    "weight": 0.20, "penalty_on_mismatch": 0.15},
        # Jurisdiction match — relevant for sanctions and regulatory regime.
        {"id": "jurisdiction", "label": "Jurisdiction / domicile",    "weight": 0.10, "penalty_on_mismatch": 0.10},
        # Recency of any flag — a 2010 sanction may be expired; a 2024 one is live.
        {"id": "recency",      "label": "Recency of findings",        "weight": 0.10, "penalty_on_mismatch": 0.05},
        # Live source — every flag must be backed by a current primary source.
        {"id": "live_source",  "label": "Has live primary source",    "weight": 0.05, "penalty_on_mismatch": 0.05},
    ],
    "applies_to": {
        "signals": [
            "due_diligence",
            "kyc",
            "aml",
            "compliance_check",
            "background_check",
            "risk_assessment",
            "sanctions",
            "pep_screen",
            "know_your_customer",
        ],
        "entity_types": ["person", "company"],
    },
    "default_mode": "investigation",
    "budget_minimums": {
        # Anti-tunneling floor — false positives are costly so the gate
        # must consider competing identities before committing to one.
        "hypothesis_count": "competing",
    },
    "phases": [
        {
            "id": "signal_extraction",
            "depends_on": [],
            "unit_of_work_contract": {
                "inputs": ["query", "classifier_output"],
                "briefing": (
                    "Parse the due-diligence brief into a typed signal "
                    "hierarchy. PRIMARY: target entity (legal name, registry "
                    "id, domicile if known). SUPPORTING: jurisdiction(s) to "
                    "screen against, risk categories of interest (sanctions, "
                    "PEP, adverse media, litigation, regulatory), and the "
                    "compliance regime driving the check. Do not screen yet "
                    "— extraction only. Output a screening spec + PIR "
                    "criteria with weights matching ach_signals."
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
                    "Generate N distinct candidate identities for the target "
                    "entity — different legal entities or individuals matching "
                    "the name + jurisdiction signals. For each, also pull at "
                    "least one screen against a live source: official "
                    "sanctions list (OFAC, EU, UK HMT, UN), PEP database, "
                    "adverse-media search. Treat partial-name matches as "
                    "DISTINCT candidates, not noise — overmatching is safer "
                    "than missing the right one."
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
                    "For each candidate identity, run two parallel "
                    "disconfirmation searches: (1) identity falsification "
                    "(wrong jurisdiction, wrong registry, name collision) "
                    "and (2) risk-signal falsification (the adverse hit was "
                    "about a different entity, sanction expired, allegation "
                    "retracted). Log a [DISCONFIRM:H_n] entry per candidate "
                    "covering BOTH dimensions. Record the ACH matrix row "
                    "(✓/✗/?) per PIR signal."
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
                    "penalty weighting. Verify the top candidate's identity "
                    "AND every risk flag against a live primary source "
                    "before committing. Cap confidence at 40% if any "
                    "non-trivial PIR signal is unverified. Return a ranked "
                    "result that surfaces ALL candidates with ANY risk flag "
                    "in alternatives_considered — under-reporting a "
                    "watchlist hit is a worse outcome than over-reporting. "
                    "Confidence < 0.4 → escalate to user with the candidate "
                    "set rather than commit to a clear / not-clear answer."
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
