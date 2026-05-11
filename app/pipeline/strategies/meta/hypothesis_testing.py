"""Hypothesis Testing meta-strategy module."""

NAME = "hypothesis_testing"
DISPLAY_NAME = "Hypothesis Testing"
DESCRIPTION = (
    "Structured analytic discipline applied to all investigations. Implements ACH, "
    "hypothesis laddering, key assumptions checking, elimination-first doctrine, "
    "red-cell adversarial thinking, and premortem review."
)
TRIGGER_SIGNALS = [
    "is it true", "verify", "confirm", "disprove", "evidence", "claim",
    "allegation", "accurate",
]
ENTITY_TYPES = ["all"]
ALWAYS_ON = True

STRATEGY_TEXT = """
=== HYPOTHESIS TESTING META-STRATEGY ===

Never collect toward a single hypothesis. Always maintain a competing set.
Evidence that cannot distinguish between hypotheses has zero diagnostic value.

--- ANALYSIS OF COMPETING HYPOTHESES — ACH (origin: Richards Heuer, CIA 1999) ---

Step 1: Generate >= 3 plausible hypotheses BEFORE collection begins.
  Always include: (a) a deception hypothesis, (b) a "no wrongdoing" hypothesis,
  and (c) the most obvious hypothesis. Do not prune until evidence forces it.

Step 2: For each piece of evidence, score against every hypothesis:
  C = Consistent (evidence is compatible with this hypothesis)
  I = Inconsistent (evidence refutes or contradicts this hypothesis)
  N = Not applicable / irrelevant

Step 3: Reject hypotheses with the most Inconsistent scores first.
  The LEAST DISCONFIRMED hypothesis wins — not the most confirmed.
  This is the ACH principle: confirmation bias is defeated by counting
  inconsistencies, not confirmations.

Step 4: Collect DIAGNOSTIC evidence — evidence that produces different scores
  across surviving hypotheses. Evidence that scores C against all survivors
  has zero discriminating power; deprioritize it.

--- HYPOTHESIS LADDER (always active) ---

Maintain an explicit ranked list of hypotheses throughout the investigation.
  - Every tool result triggers a hypothesis re-ranking.
  - Update confidence scores after each new evidence item.
  - Termination condition: leading hypothesis dominates by confidence margin
    >= 0.30 AND has >= 3 independent diagnostic evidence items.
  - If termination is not met, flag the investigation as UNRESOLVED and specify
    which diagnostic evidence would resolve it.

--- KEY ASSUMPTIONS CHECK (origin: CIA SATs Tradecraft Primer) ---

Before concluding, enumerate every assumption underlying the current analysis.
Rate each assumption on two axes:
  - Confidence in assumption: high / medium / low
  - Impact if assumption is wrong: high / medium / low

Priority matrix:
  high-impact + low-confidence  → must-collect priority before concluding
  high-impact + medium-confidence → collect if budget allows
  low-impact + any confidence   → document; accept residual risk

State every key assumption explicitly in the output. Unstated assumptions
that are wrong produce wrong conclusions with high apparent confidence.

--- ELIMINATION / EXCLUSION-FIRST (origin: LE doctrine / Sherlock Holmes) ---

Generate disqualifying tests before confirmatory search. Run cheap disqualifiers
before expensive collection. Test sequence:
  1. Was the entity operational in the claimed time window?
  2. Was it present in the claimed jurisdiction?
  3. Did it have the claimed capacity / scale?
  4. Are there verifiable records that should exist if the claim is true?

Eliminating 90% of the hypothesis space cheaply beats confirming 10%
expensively. If a cheap test disqualifies the leading hypothesis, STOP and
re-rank before spending further budget.

--- RED CELL / ADVERSARIAL THINKING (origin: CIA Red Cell) ---

Model the subject as an active adversary with a competent opsec posture. Ask:
  - What would they hide? Where is the highest-value concealment point?
  - Where would they fail at hiding it?

Prioritized opsec-failure collection points:
  - Early-career artifacts (pre-opsec discipline)
  - Family members' digital footprints (secondary exposure surface)
  - Low-signal jurisdictions (registrations in lightly monitored locales)
  - Archive snapshots (scrubbing is always incomplete; Wayback / archive.today)
  - Third-party data leaks (the subject did not control their counterparty's opsec)
  - Infrastructure they didn't harden (Shodan, certificate transparency, DNS)

--- CONTRADICTIONS AS PIVOTS ---

When two reliable sources disagree, that disagreement is the highest-value lead
in the investigation. Protocol:
  - Do not average contradictions away.
  - Do not default to the more recent source.
  - Spawn sub-investigations on BOTH contradictory claims.
  - The resolution of the contradiction is a diagnostic test for all
    surviving hypotheses.

--- PREMORTEM (origin: Gary Klein / CIA SATs) ---

Before delivering any conclusion: assume the analysis will be proven wrong in
6 months. Explain why. Protocol:
  - List the top 3 ways this analysis could be wrong.
  - For each: what evidence would reveal the error?
  - Generate a "lawyer's attack list" — what would the subject's counsel challenge?
  - Pre-strengthen or explicitly qualify each challenged point.
  - If a challenged point cannot be strengthened, label it UNCONFIRMED in output.
"""
