"""Systematic review research strategy module."""

ENTITY_TYPE = "systematic_review"

STRATEGY = """
=== SYSTEMATIC REVIEW STRATEGY ===

goal: Rigorous systematic review following PRISMA-like protocol: exhaustive search, transparent deduplication, GRADE quality grading, meta-synthesis.
execution_model: protocol_define(PICO/PECO) → exhaustive_search → screening_deduplication → data_extraction(RoB) → quality_grade(GRADE) → meta_synthesis

PICO: Population | Intervention/Exposure | Comparator | Outcome

PRIORITY SELECTORS: research_question | eligibility | search_strategy | study | quality_grade | claim | gap

pivots:
research_question → PICO_framework | PROSPERO_registry | Cochrane_Library(existing_reviews)
search_strategy → MeSH_terms(NLM_browser) | Emtree(Embase) | CINAHL_headings | search_filter_validation
quality_grade → Cochrane_Handbook(RoB2) | GRADE_handbook(gradeworkinggroup.org) | Eppi-Centre(qualitative)
claim → forest_plot_pooled_estimate | sensitivity_analysis | subgroup_analysis
gap → "future_research" sections | funnel_plot_asymmetry | GRADE_"Very_Low"_ratings

GRADE certainty: High(RCT_base) | Moderate | Low | Very_Low — downgrade: risk_of_bias/inconsistency/indirectness/imprecision/pub_bias

principles: PRISMA-PROTOCOL-FIRST | EXHAUSTIVE-SEARCH(all_DBs+grey) | DEDUPLICATION-SYSTEMATIC | GRADE-EVERY-OUTCOME | CONFLICT-RESOLUTION

COMPLETENESS CHECKLIST: search_exhaustive(DBs+grey+strings+counts) | deduplication(PRISMA_flow) | quality_grading(GRADE+RoB_per_study) | claim_mapping(studies+GRADE) | conflict_resolution | gap_identification
"""
