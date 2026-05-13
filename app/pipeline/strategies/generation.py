"""Generation research strategy module."""

ENTITY_TYPE = "generation"

STRATEGY = """
=== GENERATION RESEARCH STRATEGY ===

goal: Novel solutions grounded in SOTA scan, cross-domain transfer, feasibility assessment.
execution_model: problem_define → sota_scan → gap_identify → cross_domain_search → candidate_solutions → feasibility_check

PRIORITY SELECTORS: problem_statement | concept | technique | prior_art | researcher_lab | constraint | gap

pivots:
problem_statement → patent_search(USPTO/EPO) | web_search(surveys+reviews) | arXiv
concept → limitations_search | alternatives("X vs Y") | oss_implementations
technique → recent_improvements("improved X") | adjacent_variants | ablation_studies
prior_art → citation_graph(forward+backward) | implementation_repos
gap → TRIZ_contradiction_matrix | cross_domain(biology/physics/economics) | "unsolved problems in X"

principles: SOTA-FIRST | CROSS-DOMAIN(≥1 non-obvious round) | GAP-DRIVEN | FEASIBILITY-FILTER | NOVELTY-CHECK

COMPLETENESS CHECKLIST: state_of_art | gap_identification(3+ gaps) | solution_space(3+ candidates per gap) | feasibility_analysis | novelty_check | competitive_landscape
"""
