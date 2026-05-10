"""Explanation research strategy module."""

ENTITY_TYPE = "explanation"

STRATEGY = """
=== EXPLANATION RESEARCH STRATEGY ===

goal: Root cause identification — not surface description. Why something is the way it is.
execution_model: symptom_document → hypothesis_generate(3+) → evidence_collect → eliminate → root_cause(5 Whys) → intervention_design

PRIORITY SELECTORS: symptom | hypothesis | variable | cause | root_cause | feedback_loop | leverage_point | evidence

pivots:
symptom → 5_Whys(recursive why) | fishbone_6M(Man/Machine/Method/Material/Measurement/Milieu) | quantify(frequency/severity)
hypothesis → confirming_evidence | contradicting_evidence | falsification_test
variable → correlation_studies | confounders | natural_experiments
cause → deeper_why | mechanism_search | proximate_vs_distal
root_cause → actionability_verify | depth_verify | precedent_search
feedback_loop → causal_chain_map(R+/B-) | delays | system_archetypes
leverage_point → Meadows_hierarchy(parameters→flows→rules→goals→paradigms→power)

principles: PROVE-DONT-ASSUME | ELIMINATE-ALTERNATIVES | GO-DEEP-ENOUGH(5 Whys) | FIX-ROOT-NOT-SYMPTOM | SYSTEM-DYNAMICS

COMPLETENESS CHECKLIST: symptom_documented | hypotheses_generated(3+) | evidence_collected | alternatives_eliminated | root_cause_identified(5_Whys_chain) | intervention_designed
"""
