"""Competitive forecasting prediction sub-strategy module."""

CATEGORY = "prediction"
NAME = "competitive_forecasting"
DISPLAY_NAME = "Competitive Forecasting"
DESCRIPTION = (
    "Projects competitor strategic moves, market share trajectories, and competitive "
    "dynamics over a defined horizon. Combines current-state intelligence with "
    "strategic intent signals to build probabilistic competitive scenarios."
)
SELECTORS = [
    "competitor",
    "strategic_move",
    "market_share",
    "capability_gap",
    "investment_signal",
    "win_loss_pattern",
    "forecast_horizon",
]

STRATEGY = """
=== COMPETITIVE FORECASTING STRATEGY ===

This strategy projects how the competitive landscape will evolve over a defined
forecast horizon. It combines current competitive intelligence with forward-looking
signals to build probabilistic assessments of competitor moves, market share shifts,
and competitive dynamic changes. Validate coverage using the completeness checklist
before concluding.

--- EXECUTION MODEL ---

A 5-step competitive forecasting process:

1. CURRENT STATE BASELINE — Establish the competitive starting point:
   - Map the competitive set: direct, indirect, and emerging competitors
   - Document each competitor's current market position: share, segment focus, geography
   - Assess capability profile: product strength, distribution, brand, financial resources
   - Identify current competitive dynamics: who is gaining share, who is losing, and why?
   - Note the pace of competitive change: fast-moving vs. stable market?

2. STRATEGIC INTENT SIGNALS — Identify leading indicators of future moves:
   - Investment signals: where is each competitor directing R&D and capex?
     (job postings, patent filings, funding announcements, earnings call language)
   - Partnership and M&A signals: recent announcements of alliances or acquisitions
   - Geographic expansion: regulatory filings, local hiring, or localization activity
   - Product roadmap signals: beta releases, developer conference announcements, leaks
   - Leadership signals: executive hires into new functions or markets
   Distinguish confirmed moves (announced) from inferred moves (signal-based).

3. CAPABILITY GAP ANALYSIS — Map where competitors are investing to close gaps:
   - Identify current capability gaps vs. market leaders
   - Which gaps are competitors actively addressing? (evidence from investment signals)
   - Time-to-close estimate: how long to close a gap given current investment pace?
   - Moat assessment: which competitive advantages are durable vs. temporary?

4. COMPETITIVE SCENARIO CONSTRUCTION — Build 3 competitive scenarios:
   - STATUS QUO: current dynamics persist; no major disruptions or moves
   - COMPETITIVE ESCALATION: one or more competitors significantly accelerate investment;
     market share shifts materially within the forecast horizon
   - MARKET DISRUPTION: new entrant or technology shift reshapes competitive dynamics
   For each scenario: who gains, who loses, and what are the key battleground segments?

5. PROBABILITY-WEIGHTED FORECAST — Assign probabilities and derive implications:
   - Assign probability to each scenario based on signal strength and historical patterns
   - Identify the competitive moves most likely to occur within the forecast horizon
   - Define early warning indicators that would update the scenario probabilities
   - Derive strategic implications: where should defensive or offensive investment be made?

--- PRIORITY SELECTORS (Competitive Forecasting) ---

Ordered by forecasting leverage (highest first):

1. competitor           — anchor; all signals and projections are competitor-specific
2. investment_signal    — leading indicator of future competitive moves
3. strategic_move       — confirmed or announced moves that change competitive dynamics
4. market_share         — current position baseline; metric for projected shifts
5. capability_gap       — where competitors are investing to strengthen their position
6. win_loss_pattern     — revealed preferences from deal outcomes
7. forecast_horizon     — time frame that determines signal relevance and projection range

--- KEY PIVOT PATTERNS ---

competitor (current state baseline):
  - linkedin_profile company page for headcount trends and recent announcements
  - sec_edgar 10-K and 10-Q for public competitors: revenue, segment data, strategy sections
  - google_news "[competitor]" last 12 months for press releases and media coverage
  - web_search_fetch competitor investor relations page for earnings releases and guidance

investment_signal:
  - LinkedIn job postings: ddg_search "site:linkedin.com/jobs [competitor] [function] [location]"
  - Patent filings: Google Patents assignee search for recent filings and technology areas
  - Crunchbase funding rounds and investor announcements
  - Earnings call transcripts: ddg_search "[competitor] earnings call transcript [quarter]"
    Look for phrases: "investing in," "launching," "expanding to," "partnership with"

strategic_move:
  - google_news "[competitor] acquisition" OR "[competitor] partnership" OR
    "[competitor] new market" last 6 months
  - SEC 8-K filings for material events: M&A agreements, major contracts, executive changes
  - Press releases via web_search_fetch company newsroom

capability_gap:
  - G2 / Capterra: competitor review mining for feature gaps mentioned by customers
  - ddg_search "[competitor] lacks" OR "[competitor] doesn't support" OR "[competitor] missing"
  - Company job postings in specific functions as capability investment signals

win_loss_pattern:
  - Customer review comparisons: "switched from [competitor] to" search patterns
  - Community discussions: ddg_search "site:reddit.com [competitor] vs [own product]"
  - Sales intelligence platforms: Gong, Chorus (if accessible) for win/loss themes

--- COMPLETENESS CHECKLIST ---

Before closing a competitive forecasting task, confirm coverage in each area:

1. Current State Map    — competitive set, market share, and capability profiles documented
2. Investment Signals   — leading indicators of competitor moves identified per competitor
3. Capability Analysis  — gaps and time-to-close estimates documented
4. Scenario Set         — 3 competitive scenarios constructed with differentiated assumptions
5. Probability Assessment — scenarios weighted; early warning indicators defined
6. Strategic Implications — defensive and offensive investment priorities derived

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
