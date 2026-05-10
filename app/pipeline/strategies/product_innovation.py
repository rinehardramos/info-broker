"""Product innovation research strategy module."""

ENTITY_TYPE = "product_innovation"

STRATEGY = """
=== PRODUCT INNOVATION STRATEGY ===

goal: Novel product concepts grounded in real user needs, SOTA scan, and disciplined feasibility assessment.
execution_model: empathy → problem_define → sota_scan → gap_identify → cross_domain_transfer → feasibility_assess

PRIORITY SELECTORS: user_need | target_persona | problem_statement | prior_art | gap | constraint | competitor

pivots:
user_need → forums/Reddit/App_Store_reviews | JTBD_interviews | market_reports(Gartner/Nielsen) | web_search("pain points in [domain]")
target_persona → demographic_databases | ethnographic_studies | community_forums
gap → product_reviews(G2/Capterra/Trustpilot) | patent_gap_analysis | HCI_paper_limitations
prior_art → USPTO/EPO/Google_Patents | ProductHunt/BetaList | GitHub_issue_trackers
competitor → Crunchbase(funding+investor_thesis) | web_search("[competitor] limitations") | SWOT_top3

principles: EMPATHY-BEFORE-IDEATION | CROSS-DOMAIN-TRANSFER | GAP-DRIVEN | FEASIBILITY-FIRST

COMPLETENESS CHECKLIST: user_needs(persona+JTBD+evidence) | sota(products+patents+academic) | gap(3+ validated) | solution_space(3+ per gap) | feasibility(technical+market+operational) | competitive_landscape
"""
