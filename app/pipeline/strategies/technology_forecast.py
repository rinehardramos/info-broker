"""Technology forecast research strategy module."""

ENTITY_TYPE = "technology_forecast"

STRATEGY = """
=== TECHNOLOGY FORECAST STRATEGY ===

goal: Rigorous technology forecasting using S-curve analysis, weak signal detection, and scenario construction. Output: Technology Radar ring per technology.
execution_model: signal_collect → s_curve_position → scenario_construct(3-4) → key_uncertainties → radar_output(Adopt/Trial/Assess/Hold)

PRIORITY SELECTORS: technology | s_curve_position | weak_signal | scenario | driver | competitor_tech | adoption_metric

pivots:
technology → web_search("[tech] adoption rate") | Gartner_Hype_Cycle | McKinsey_Tech_Trends | IEEE_Spectrum
weak_signal → patent_citation_network | arXiv_daily | startup_accelerator_cohorts(YC/a16z) | DARPA_BAA
s_curve_position → publication_count_by_year(Semantic_Scholar) | patent_filing_trend(5-10yr) | cost_trajectory | analyst_consensus
scenario → 2x2_matrix(2_key_uncertainties) | historical_analogy | Delphi_survey

s_curve_phases: Emerging(TRL 1-3,no_dominant_design) | Growth(TRL 4-6,competing_standards) | Maturity(TRL 7-9,dominant_design) | Decline(displaced)

principles: SIGNAL-COVERAGE-BREADTH(patents+pubs+investment+adoption) | S-CURVE-DISCIPLINE | WEAK-SIGNAL-DETECTION | RADAR-OUTPUT-REQUIRED

COMPLETENESS CHECKLIST: signal_coverage(all_4_classes) | s_curve_position(quantified) | key_uncertainties(3-5_ranked) | scenarios(baseline+accelerated+disrupted) | radar_ring_assigned
"""
