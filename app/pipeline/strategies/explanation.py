"""Explanation research strategy module."""

ENTITY_TYPE = "explanation"

STRATEGY = """
=== EXPLANATION RESEARCH STRATEGY ===

This strategy defines how to conduct a rigorous investigation into why something
happened or why something is the way it is. The goal is root cause identification,
not surface-level description. Follow the execution model, honor the priority
selector order, and validate coverage using the completeness checklist before
concluding.

--- EXECUTION MODEL ---

A 6-step symptom-to-intervention process:

1. SYMPTOM DOCUMENTATION — Precisely document what is observed. Distinguish
   symptoms (observable effects) from causes (underlying mechanisms). Record
   when, where, how often, and under what conditions the symptom appears.
   Quantify where possible.

2. HYPOTHESIS GENERATION — Generate at least 3 competing hypotheses that could
   explain the observed symptom. Include both obvious and non-obvious candidates.
   Avoid anchoring on the first plausible explanation.

3. EVIDENCE COLLECTION — For each hypothesis, gather supporting and contradicting
   evidence from multiple independent sources. Prioritize empirical evidence
   (data, experiments, measurements) over anecdotal or theoretical arguments.

4. ELIMINATION — Systematically rule out hypotheses that are contradicted by
   evidence. Document why each eliminated hypothesis failed. The surviving
   hypothesis must explain all observed symptoms without contradiction.

5. ROOT CAUSE — Identify the deepest causal factor that, if addressed, would
   prevent the symptom from recurring. Apply the "5 Whys" technique recursively
   until you reach a cause that is actionable and not a symptom of something
   deeper. Consider system dynamics, feedback loops, and structural factors.

6. INTERVENTION DESIGN — Design interventions that address the root cause, not
   the symptoms. Distinguish short-term mitigations from long-term fixes.
   Anticipate second-order effects and unintended consequences of each
   intervention.

--- PRIORITY SELECTORS (Explanation) ---

Ordered by causal leverage (highest priority first):

1. symptom         — the observable effect; starting point; must be precisely defined
2. hypothesis      — candidate explanation to be tested against evidence
3. variable        — measurable factor that may correlate with or cause the symptom
4. cause           — confirmed contributing factor (not yet root)
5. root_cause      — deepest actionable cause; the target of this investigation
6. feedback_loop   — self-reinforcing cycle that perpetuates or amplifies the symptom
7. leverage_point  — place in the system where intervention has disproportionate effect
8. evidence        — data, documents, measurements, or testimony bearing on a hypothesis

--- KEY PIVOT PATTERNS ---

symptom:
  - apply 5 Whys: ask "why does this symptom occur?" recursively until root found
  - apply fishbone (Ishikawa) diagram using 6M categories:
    [Man, Machine, Method, Material, Measurement, Mother Nature / Environment]
  - search for documented instances of the same symptom in literature or case studies
  - quantify symptom: measure frequency, severity, affected population

hypothesis:
  - search for evidence that supports the hypothesis (confirming studies, data)
  - search for evidence that contradicts or limits the hypothesis
  - generate at least one alternative hypothesis for each candidate
  - design a test or natural experiment that would falsify the hypothesis

variable:
  - search for correlation studies linking the variable to the symptom
  - check for confounding variables that co-vary with the suspected cause
  - look for natural experiments (policy changes, events) that isolate the variable

cause:
  - apply deeper "why" recursively: each cause becomes a new symptom to explain
  - search for mechanisms: how does this cause produce the observed symptom?
  - distinguish proximate cause (immediate trigger) from distal cause (structural factor)
  - check if removing the cause would reliably eliminate the symptom

root_cause:
  - verify it is actionable: can an intervention address this cause?
  - verify it is deep enough: is this cause itself a symptom of something deeper?
  - search for precedent: has this root cause been confirmed in similar systems?

feedback_loop:
  - map the causal chain: identify reinforcing (+) and balancing (-) loops
  - find the loop's entry point and delay factors
  - search for system archetypes that match the observed loop structure

leverage_point:
  - apply Donella Meadows' leverage point hierarchy (parameters → flows → rules
    → goals → paradigms → power to change paradigms)
  - identify high-leverage interventions that affect the structure, not just symptoms

evidence:
  - assess source quality: primary > secondary > tertiary
  - check for replication: has this evidence been reproduced independently?
  - identify conflicts: when two sources disagree, investigate the source of conflict

--- INVESTIGATION PRINCIPLES ---

PROVE DON'T ASSUME
  No cause is accepted without evidence. Intuitive explanations must be treated
  as hypotheses until confirmed by data. The burden of proof is on the hypothesis.

ELIMINATE ALTERNATIVES
  The correct explanation is the one that survives elimination. Do not close an
  investigation until all plausible alternatives have been tested and eliminated
  or accepted. A surviving hypothesis that hasn't been challenged is not confirmed.

GO DEEP ENOUGH
  Surface causes are symptoms of deeper causes. Apply "5 Whys" until you reach
  a cause that is structural, not incidental. If removing the identified cause
  would only temporarily suppress the symptom, go deeper.

FIX ROOT NOT SYMPTOM
  Interventions that suppress symptoms without addressing root causes create
  recurrence, resistance, and often worsen the underlying condition over time.
  Always design interventions at or near the root cause.

CONSIDER SYSTEM DYNAMICS
  Most real-world phenomena involve feedback loops, delays, and nonlinear
  responses. A cause-and-effect framing that ignores system structure will miss
  reinforcing dynamics that sustain the symptom.

--- COMPLETENESS CHECKLIST ---

Before closing an explanation research task, confirm coverage in each area:

1. Symptom Documented        — symptom precisely defined, quantified, and scoped
2. Hypotheses Generated      — at least 3 competing hypotheses produced and recorded
   (3+)
3. Evidence Collected        — supporting and contradicting evidence gathered per
                               hypothesis from independent sources
4. Alternatives Eliminated   — each non-surviving hypothesis ruled out with documented
                               reasoning
5. Root Cause Identified     — deepest actionable cause confirmed; 5 Whys chain
                               documented
6. Intervention Designed     — at least one root-cause intervention proposed with
                               anticipated second-order effects noted

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
