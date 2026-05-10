"""Synthesis research strategy module."""

ENTITY_TYPE = "synthesis"

STRATEGY = """
=== SYNTHESIS RESEARCH STRATEGY ===

goal: Integrated, balanced conclusion reflecting the full evidentiary landscape — no cherry-picking.
execution_model: systematic_search → quality_assess → claim_extract → evidence_map → conflict_resolve → multi_framework_analysis → gap_identify

PRIORITY SELECTORS: study | framework | criterion | claim | evidence | perspective | option

pivots:
study → citation_graph(forward+backward) | method_extraction | result_extraction(effect_sizes/CIs) | quality_grading(GRADE/CONSORT) | replication_search
claim → supporting_evidence | contradicting_evidence | expert_assessment | scope_check
framework → apply_to_data | limitations_search | cross_framework_synthesis(convergence=higher_confidence)
perspective → community_identification | strongest_articulation | strongest_critique | empirical_testability
option → evidence_base | trade_off_analysis | implementation_evidence | stakeholder_impacts

principles: SYSTEMATIC-NOT-CHERRY-PICKED | GRADE-EVERY-SOURCE | RESOLVE-CONFLICTS | MULTI-FRAMEWORK(≥2) | IDENTIFY-GAPS

COMPLETENESS CHECKLIST: literature_coverage(systematic) | quality_assessment(all sources graded) | claim_mapping(convergence+conflict) | conflict_resolution(investigated) | multi_framework_analysis(2+ frameworks) | gap_identification
"""
