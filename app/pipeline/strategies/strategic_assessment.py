"""Strategic assessment research strategy module."""

ENTITY_TYPE = "strategic_assessment"

STRATEGY = """
=== STRATEGIC ASSESSMENT STRATEGY ===

goal: Comprehensive strategic analysis using multi-framework cascade: PESTLE → Porter's Five Forces → SWOT → VRIO. Stakeholder perspectives required.
execution_model: pestle_analyze → five_forces_assess → swot_complete → vrio_assess → stakeholder_integrate

PRIORITY SELECTORS: strategic_entity | industry_context | macro_environment | resource | competitor | stakeholder | strategic_option

PESTLE dimensions: Political | Economic | Social | Technological | Legal | Environmental → assess current_state + direction_of_change + time_horizon

Five Forces: new_entrants | supplier_power | buyer_power | substitutes | competitive_rivalry → rate each Low/Medium/High + trend(strengthening/stable/weakening)

SWOT: Strengths(internal_advantages) | Weaknesses(internal_gaps) | Opportunities(external_from_PESTLE/5F) | Threats(external_from_PESTLE/5F)
Note: O and T must trace to PESTLE/Five_Forces — not generated in isolation.

VRIO: Valuable | Rare | Inimitable(path_dependency/causal_ambiguity/social_complexity) | Organized → competitive_implication per resource

pivots:
macro_environment → World_Bank/IMF | OECD_Policy_Tracker | Gartner/Forrester | ESG_agencies(MSCI/Sustainalytics)
industry_context → IBISWorld/Statista | SEC_10-K(competition+risk) | Crunchbase(entry_signals) | Porter(1979)
competitor → annual_reports | LinkedIn/Glassdoor(hiring_patterns) | patent_databases | G2/Capterra(perceived_strengths)
resource → patent_portfolio | Interbrand/Brand_Finance | supplier_agreements | HR_capability_surveys

principles: FRAMEWORK-CASCADE-DISCIPLINE | VRIO-RIGOR(inimitability_is_key) | STAKEHOLDER-INTEGRATION | FIVE-FORCES-CALIBRATION(rate+trend)

COMPLETENESS CHECKLIST: PESTLE(all_6_dimensions+direction) | five_forces(all_5_rated+trend) | SWOT(traced_to_external_analysis) | stakeholder_views(power/interest+conflicts) | strategic_options(3+_assessed_via_VRIO)
"""
