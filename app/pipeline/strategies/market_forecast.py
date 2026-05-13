"""Market forecast research strategy module."""

ENTITY_TYPE = "market_forecast"

STRATEGY = """
=== MARKET FORECAST STRATEGY ===

goal: Rigorous market sizing, growth projection, and competitive dynamics. TAM/SAM/SOM estimation required.
execution_model: market_define → tam_sam_som_estimate → growth_rate_analyze → competitive_dynamics → demand_model(driver-based)

PRIORITY SELECTORS: market_definition | tam_sam_som | growth_rate | demand_driver | competitor | risk_factor | customer_segment

pivots:
market_definition → NAICS/SIC_codes | analyst_firm_definitions(Gartner/IDC) | SEC_10-K_market_definitions
tam_sam_som → top-down(Statista/IBISWorld/Grand_View) | bottom-up(unit_price×addressable_units) | cross-validate(if_>2x_diff_investigate) | web_search("[market] market size [year]")
growth_rate → historical(World_Bank/IMF) | analyst_CAGR_projections | comparable_markets(adjacent_stages)
competitive_dynamics → Crunchbase(entry_threat) | SEC_EDGAR(revenue+share) | industry_association_reports
demand_driver → FRED/World_Bank_Open_Data | industry_reports(sensitivity_analysis) | demand_elasticity_papers

TAM = full revenue at 100% share | SAM = reachable with current model/geo | SOM = realistic near-term capture

principles: MARKET-DEFINITION-DISCIPLINE | TAM-SAM-SOM-RIGOR(all_3_tiers) | DRIVER-BASED-MODELING | SCENARIO-RANGE(bear/base/bull)

COMPLETENESS CHECKLIST: market_size(TAM+SAM+SOM_cross-validated) | growth_rate(historical+forward) | competitive_landscape(concentration+share+entry_threats) | demand_drivers(3+_quantified) | risk_factors(downside+bear_scenario)
"""
