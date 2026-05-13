"""Prediction research strategy module."""

ENTITY_TYPE = "prediction"

STRATEGY = """
=== PREDICTION RESEARCH STRATEGY ===

goal: Well-grounded scenarios supported by identified signals, quantified uncertainties, and actor assessments.
execution_model: signal_detect → trend_identify → driver_analyze → uncertainty_map → scenario_construct(2x2 matrix) → actor_assess

PRIORITY SELECTORS: signal | trend | driver | uncertainty | scenario | weak_signal | actor | constraint

pivots:
signal → corroborating_signals(multi-source) | cause/driver_search | quantification | historical_precedent
trend → projection(historical+inflection) | disruption_risk | cross_domain_check | contradictory_trends
uncertainty → scenario_matrix_axis | expert_opinion | historical_precedent(resolution) | sensitivity_analysis
weak_signal → amplification_conditions | early_adopter_communities | technology_readiness
actor → interest_mapping(gain/lose per scenario) | capability_assessment | coalition_analysis
constraint → physical_limits | regulatory_landscape | economic_viability

principles: MULTI-SOURCE-SIGNALS(≥2 independent) | TREND-VS-NOISE | MAP-UNCERTAINTIES | DIVERGENT-SCENARIOS(≥2) | IDENTIFY-KEY-ACTORS

COMPLETENESS CHECKLIST: signal_coverage(multi-source) | trend_identification(2+ directional) | driver_analysis(STEPES) | uncertainty_mapping(impact+confidence) | scenario_construction(2+ divergent) | actor_assessment
"""
