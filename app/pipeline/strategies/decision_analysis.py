"""Decision analysis research strategy module."""

ENTITY_TYPE = "decision_analysis"

STRATEGY = """
=== DECISION ANALYSIS STRATEGY ===

goal: Structured decision-making under uncertainty using multi-criteria decision matrix with weighted scoring. Clear recommendation required.
execution_model: option_enumerate → criteria_define(MECE) → weights_assign → evidence_map(per_option_per_criterion) → recommend

PRIORITY SELECTORS: decision_question | option | criterion | weight | evidence | constraint | sensitivity

option_categories: cost | quality/performance | risk | time | scalability | strategic_alignment | reversibility | compliance
Always include status_quo (do_nothing) as an option.

pivots:
option → web_search "[decision domain] options/alternatives" | industry_benchmarks | expert_interviews
criterion → regulatory_requirements(binary_pass/fail) | TCO(financial) | strategic_alignment | risk(probability+severity) | reversibility
weight → AHP_pairwise(Saaty_1980) | swing_weighting | stakeholder_elicitation | sensitivity_analysis(±20%_weight_shift)
evidence → RFP/RFQ_responses | financial_modeling(NPV/IRR/payback) | technical_benchmarks | reference_checks
sensitivity → one-at-a-time_weight_variation | scenario-based(optimistic/pessimistic) | threshold_analysis(rank_change_point)

scoring: weighted_score = Σ(criterion_weight × option_score) | document evidence_quality per cell (Strong/Moderate/Weak/Assumed)

principles: OPTION-COMPLETENESS-FIRST | CRITERIA-INDEPENDENCE | EVIDENCE-MAPPING-DISCIPLINE | WEIGHTS-ARE-ASSUMPTIONS | CLEAR-RECOMMENDATION-REQUIRED

COMPLETENESS CHECKLIST: options_enumerated(all_viable+status_quo) | criteria_defined(MECE+measurement) | evidence_per_option(quality_rated) | weights_assigned(rationale+sensitivity) | recommendation(top_option+rationale+trade-offs+re-evaluation_conditions)
"""
