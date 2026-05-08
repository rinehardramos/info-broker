"""Market forecasting prediction sub-strategy module."""

CATEGORY = "prediction"
NAME = "market_forecasting"
DISPLAY_NAME = "Market Forecasting"
DESCRIPTION = (
    "Builds driver-based market forecasts with scenario ranges for a specific "
    "product or industry segment. Produces TAM/SAM/SOM estimates, growth projections, "
    "and bear/base/bull scenarios grounded in quantified demand drivers."
)
SELECTORS = [
    "market_definition",
    "tam_sam_som",
    "growth_driver",
    "forecast_horizon",
    "customer_segment",
    "risk_factor",
    "scenario",
]

STRATEGY = """
=== MARKET FORECASTING STRATEGY ===

This strategy builds rigorous market forecasts with explicit assumptions, driver-based
models, and scenario ranges. It avoids trend extrapolation in favor of causal modeling:
identify the drivers of demand, quantify their contribution, and model how they evolve
under different assumptions. Validate coverage using the completeness checklist
before concluding.

--- EXECUTION MODEL ---

A 6-step market forecasting process:

1. MARKET SCOPING — Define what is being forecast with precision:
   - Product/service definition: what is and is not in scope
   - Geographic scope: global, regional, or specific country/city
   - Customer segment scope: B2B, B2C, specific verticals or demographics
   - Forecast horizon: 1-year (operational), 3-year (strategic), 5-10 year (long-range)
   - Base year: the last period with reliable actuals for anchoring
   Imprecise market definitions produce unreliable forecasts.

2. BASELINE ESTABLISHMENT — Anchor the forecast in current actuals:
   - Locate current market size estimates from multiple analyst sources
   - Cross-validate top-down (analyst reports) vs. bottom-up (unit price × volume)
   - If estimates diverge by >50%, investigate the methodological differences
   - Identify the most reliable baseline estimate with documented rationale
   - Note data vintage: how current are the available estimates?

3. DRIVER IDENTIFICATION — Build a causal model of demand:
   - List 3-5 primary demand drivers (variables that, when they increase, market grows)
   - List 2-3 primary demand inhibitors (variables that reduce or cap growth)
   - For each driver/inhibitor: identify a proxy metric that can be monitored
   - Quantify historical elasticity: how much did market grow per unit change in driver?
   Drivers must be measurable, not vague (e.g., "digital adoption rate" is a driver;
   "growing digital awareness" is not).

4. SCENARIO CONSTRUCTION — Build three scenarios with distinct driver assumptions:
   - BEAR scenario: drivers underperform; inhibitors accelerate; conservative growth
   - BASE scenario: drivers perform in line with consensus; most likely outcome
   - BULL scenario: drivers outperform; inhibitors weaken; upside case
   For each scenario: state the specific driver assumptions that differentiate it.
   Point estimates are false precision — scenarios communicate genuine uncertainty.

5. FORECAST MODELING — Calculate market size for each scenario and forecast year:
   - Apply growth rates derived from driver assumptions to the baseline
   - Cross-check: do the resulting numbers make intuitive sense?
   - Segment the forecast by customer segment or geography where data supports it
   - Apply S-curve modeling where applicable (new technology adoption dynamics)

6. RISK & SENSITIVITY ANALYSIS — Identify what could make the forecast wrong:
   - Sensitivity analysis: which driver assumption has the largest impact on outcome?
   - Known unknowns: regulatory changes pending, technology shifts in progress
   - Tail risks: low-probability events that would dramatically change the forecast
   - Monitoring indicators: observable signals that suggest a scenario is emerging

--- PRIORITY SELECTORS (Market Forecasting) ---

Ordered by forecasting leverage (highest first):

1. market_definition   — precise scope; must be established before any sizing
2. tam_sam_som         — three-tier market sizing with documented assumptions
3. growth_driver       — quantifiable causal variables driving demand expansion
4. forecast_horizon    — time frame; determines driver and scenario modeling approach
5. scenario            — bear/base/bull framework with differentiated assumptions
6. customer_segment    — demand concentration and segment-specific growth rates
7. risk_factor         — downside risks and monitoring indicators

--- KEY PIVOT PATTERNS ---

market_definition + tam_sam_som:
  - Analyst reports: Statista, IBISWorld, Grand View Research, MarketsandMarkets
  - sec_edgar 10-K filings: public company "addressable market" disclosures
  - Trade association annual reports for industry-level market data
  - ddg_search "[market] market size [year] billion" for multiple analyst estimates

growth_driver:
  - World Bank Open Data, FRED, IMF WEO for macroeconomic driver data
  - Industry association reports for sector-specific adoption metrics
  - Google Trends (search volume proxy for adoption rates)
  - ddg_search "[driver variable] statistics [year]" for quantitative data
  - Government statistics agencies for demographic and economic indicators

customer_segment:
  - Analyst reports with segment breakdowns (enterprise vs. SMB, geography)
  - Company annual reports for disclosed segment revenue data
  - Industry surveys and primary research publications

risk_factor:
  - Regulatory pipeline: pending legislation that could affect market dynamics
  - Technology substitution: ddg_search "[market] disruption" OR "[market] threat [year]"
  - Macroeconomic risk: IMF, World Bank downside scenario publications
  - Competitive entry: Crunchbase funding velocity as new entrant proxy

scenario:
  - McKinsey, BCG, and Bain scenario publications in the industry for methodology benchmarks
  - IMF World Economic Outlook for economic scenario frameworks
  - IEA Energy Outlook for energy market scenario modeling as methodology example

--- COMPLETENESS CHECKLIST ---

Before closing a market forecasting task, confirm coverage in each area:

1. Market Definition    — precise scope with geographic, product, and customer segment bounds
2. Baseline Actuals     — current market size from multiple sources; best estimate selected
3. Driver Model         — 3-5 demand drivers with proxy metrics and historical elasticity
4. Scenario Set         — bear/base/bull scenarios with distinct driver assumptions
5. Forecast Numbers     — market size projections per scenario for each forecast year
6. Risk & Sensitivity   — key risks, sensitivity drivers, and monitoring indicators documented

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
