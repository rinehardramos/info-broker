"""Market forecast prediction sub-strategy module."""

CATEGORY = "prediction"
NAME = "market_forecast"
DISPLAY_NAME = "Market Forecast"
DESCRIPTION = (
    "Rigorous market sizing, growth projection, and competitive dynamics analysis. "
    "TAM/SAM/SOM estimation is a required deliverable. Demand modeling identifies "
    "drivers rather than merely extrapolating historical trends."
)
SELECTORS = [
    "market_definition",
    "tam_sam_som",
    "growth_rate",
    "demand_driver",
    "competitor",
    "risk_factor",
    "customer_segment",
]

STRATEGY = """
=== MARKET FORECAST STRATEGY ===

This strategy guides research toward rigorous market sizing, growth projection, and
competitive dynamics analysis. TAM/SAM/SOM estimation is a required deliverable.
Demand modeling must identify drivers, not merely extrapolate historical trends.
Validate coverage using the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step market forecasting process:

1. MARKET DEFINITION — Define the market boundaries precisely before sizing:
   - Product/service scope: what is and is not included in the market definition
   - Geographic scope: global, regional, country-level, or hyperlocal
   - Customer segment scope: B2B, B2C, enterprise, SMB, consumer demographics
   - Timeframe: base year, forecast horizon (1, 3, 5, 10 years)
   Vague market definitions produce unreliable estimates. Be explicit.

2. TAM/SAM/SOM ESTIMATION — Size the market at three levels:
   - TAM (Total Addressable Market): the full revenue opportunity if 100% share
     is captured. Estimate using top-down (analyst reports) and bottom-up
     (unit economics × addressable population) methods. Cross-validate both.
   - SAM (Serviceable Addressable Market): the portion of TAM reachable with
     current business model, distribution, and geographies.
   - SOM (Serviceable Obtainable Market): realistic near-term capture given
     competitive position, sales capacity, and go-to-market constraints.
   Document assumptions for every estimate. Flag uncertainty ranges.

3. GROWTH RATE ANALYSIS — Estimate the market CAGR and its drivers:
   - Historical growth rate from multiple sources (triangulate)
   - Forward-looking growth drivers: population growth, income trends,
     regulatory changes, technology enablement, substitute displacement
   - Growth inhibitors: saturation, regulation, competitive substitution
   - Analyst consensus range and variance for the forecast horizon

4. COMPETITIVE DYNAMICS — Map the competitive landscape shaping market evolution:
   - Market concentration (HHI index or top-3/top-5 share)
   - Competitive intensity (Porter's Five Forces applied to market)
   - Entry threats: VC-backed startups, geographic expansion by incumbents
   - Substitution risk: technologies or business models displacing the market
   - Key player growth trajectories (revenue, share, M&A activity)

5. DEMAND MODELING — Build a driver-based demand model:
   - Identify 3-5 key demand drivers (e.g., internet penetration, disposable income,
     regulatory mandate, technology cost decline)
   - Quantify the sensitivity of demand to each driver
   - Model scenarios: base, bull, bear — with distinct driver assumptions per scenario
   - Validate model against historical data before forecasting forward

--- PRIORITY SELECTORS (Market Forecast) ---

Ordered by research leverage (highest priority first):

1. market_definition  — precise scope boundaries enabling consistent sizing
2. tam_sam_som        — the three-tier market size estimate with documented assumptions
3. growth_rate        — historical CAGR and forward projection with driver basis
4. demand_driver      — quantifiable factors driving demand expansion or contraction
5. competitor         — key players, their share, and competitive dynamics
6. risk_factor        — macroeconomic, regulatory, or competitive risks to the forecast
7. customer_segment   — demographic or firmographic breakdown of demand concentration

--- KEY PIVOT PATTERNS ---

market_definition:
  - NAICS/SIC code lookup for standard industry classification and reporting
  - Analyst firm definitions (Gartner, IDC, Forrester) for technology markets
  - Regulatory filings and SEC 10-K market definitions for public company comparables

tam_sam_som:
  - Top-down: Statista, IBISWorld, Grand View Research, MarketsandMarkets for TAM
  - Bottom-up: unit price × total addressable units (from census or industry data)
  - Cross-validate: if top-down and bottom-up differ by >2×, investigate the gap
  - web_search "[market] market size [year]" for multiple analyst estimates

growth_rate:
  - Historical: World Bank, IMF, industry associations for macro growth proxies
  - Forward: analyst firm reports (CAGR projections with methodology notes)
  - Comparable markets: adjacent markets at earlier adoption stages as proxies

competitive_dynamics:
  - Crunchbase for startup funding velocity as entry threat signal
  - SEC filings (EDGAR) for public company revenue and market share data
  - Industry association reports for market concentration statistics
  - web_search "market share [market] [year]" for multiple competitive analyses

demand_driver:
  - Econometric databases (FRED, World Bank Open Data) for macro drivers
  - Industry reports with sensitivity analysis sections
  - Academic papers on demand elasticity for the product category

--- INVESTIGATION PRINCIPLES ---

MARKET DEFINITION DISCIPLINE
  Do not size a market without explicit boundaries. "AI market" is not a definition.
  "Enterprise AI software for FICO score improvement in US retail banks" is.

TAM/SAM/SOM RIGOR
  Always produce all three tiers. TAM without SOM is strategic fantasy. SOM without
  TAM loses context. Document every assumption — they are the forecast's foundation.

DRIVER-BASED MODELING
  Trend extrapolation is not forecasting. Build a demand model grounded in drivers
  that can be monitored and updated as conditions change.

SCENARIO RANGE
  Point estimates are false precision. Every forecast must include a bear/base/bull
  scenario range to communicate uncertainty honestly.

--- COMPLETENESS CHECKLIST ---

Before closing a market forecast research task, confirm coverage in each area:

1. Market Size          — TAM, SAM, SOM estimated with documented assumptions;
                          top-down and bottom-up methods cross-validated
2. Growth Rate          — historical CAGR documented; forward CAGR projected with
                          multiple analyst sources triangulated
3. Competitive          — market concentration measured; top players' share and
   Landscape              growth trajectory documented; entry/substitution threats assessed
4. Demand Drivers       — at least 3 quantifiable demand drivers identified;
                          sensitivity of demand to each driver assessed
5. Risk Factors         — key downside risks enumerated; bear scenario defined;
                          monitoring indicators for risk materialization identified

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
