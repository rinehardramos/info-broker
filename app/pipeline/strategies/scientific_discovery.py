"""Scientific discovery research strategy module."""

ENTITY_TYPE = "scientific_discovery"

STRATEGY = """
=== SCIENTIFIC DISCOVERY STRATEGY ===

goal: Identify knowledge gaps and formulate testable hypotheses grounded in thorough literature coverage. Falsifiability is required.
execution_model: literature_coverage → gap_identify → hypothesis_formulate(falsifiable) → experimental_design → prior_art_verify

PRIORITY SELECTORS: research_question | hypothesis | gap | prior_work | methodology | researcher_lab | dataset

pivots:
research_question → web_search("[domain] open questions") | review_articles(future_directions) | Nature/Science_Perspectives | preprints(arXiv/bioRxiv)
gap → systematic_review(GRADE_low_certainty) | contradictory_findings | null_results_repositories
hypothesis → falsifiability_check(disconfirmation_condition) | operationalize(measurable_variables) | effect_size_estimation
prior_work → citation_graph(Semantic_Scholar/OpenCitations) | systematic_search(PubMed/WoS/Scopus) | preprint_deduplication
methodology → "[method] validation studies" | instrument_comparison_papers | replication_studies

principles: EXHAUSTIVE-LITERATURE-FIRST | FALSIFIABILITY-CHECK(Popper) | HYPOTHESIS-SPECIFICITY | EXPERIMENTAL-DESIGN-RIGOR

COMPLETENESS CHECKLIST: literature_coverage(exhaustive+documented) | gap_identification(3+) | hypothesis_formulation(1+ falsifiable per gap) | experimental_design(design+sample+analysis) | prior_art_verified
"""
