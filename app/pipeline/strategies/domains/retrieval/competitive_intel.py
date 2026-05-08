"""Competitive intelligence retrieval sub-strategy module."""

CATEGORY = "retrieval"
NAME = "competitive_intel"
DISPLAY_NAME = "Competitive Intelligence"
DESCRIPTION = (
    "Analyzes competitor landscape, market positioning, and strategic moves. "
    "Maps product offerings, pricing, go-to-market strategies, and organizational "
    "signals to build an actionable competitive picture."
)
SELECTORS = [
    "competitor",
    "market_position",
    "product_offering",
    "pricing_strategy",
    "market_share",
    "strategic_move",
    "key_personnel",
]

STRATEGY = """
=== COMPETITIVE INTELLIGENCE STRATEGY ===

This strategy maps the competitive landscape for a market or specific competitor.
It covers product offerings, pricing, positioning, financial signals, organizational
changes, and strategic intentions. Intelligence is synthesized into actionable
competitive insights. Validate coverage using the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step competitive intelligence process:

1. COMPETITOR IDENTIFICATION — Define the competitor set:
   - Direct competitors: same product category, same customer segment
   - Indirect competitors: different product but solves same customer problem
   - Emerging threats: startups with funding, adjacent players expanding scope
   Use web_search, Crunchbase, product comparison sites, and G2/Capterra for discovery.

2. PRODUCT & PRICING ANALYSIS — For each competitor, map:
   - Product features, differentiators, and known gaps
   - Pricing tiers, discount strategies, contract structures
   - Recent product updates, roadmap signals (job postings, patent filings, blog posts)
   - Customer reviews: G2, Capterra, Trustpilot, Reddit — extract pain points and praise

3. MARKET POSITION MAPPING — Determine each competitor's strategic position:
   - Customer segments targeted (enterprise, SMB, consumer, vertical)
   - Geographic focus and expansion trajectory
   - Partnerships, integrations, and channel strategy
   - Brand positioning and messaging themes

4. FINANCIAL & ORGANIZATIONAL SIGNALS — Gather intelligence on company health:
   - Funding rounds, investors, valuation signals (Crunchbase, SEC)
   - Revenue estimates and growth trajectory (public filings, analyst reports)
   - Headcount trends (LinkedIn employee count delta, job posting volume)
   - Executive hires, departures, and org restructuring signals

5. STRATEGIC INTENT SYNTHESIS — Interpret signals as strategic moves:
   - New product announcements → roadmap direction
   - Aggressive hiring in a function → area of investment
   - Customer case studies in a new vertical → market expansion
   - M&A activity → capability acquisition or defensive consolidation
   Distinguish confirmed facts from inferences; label inference confidence level.

--- PRIORITY SELECTORS (Competitive Intelligence) ---

Ordered by intelligence value (highest first):

1. competitor        — anchor company; all other selectors flow from this
2. product_offering  — core product features and differentiation
3. pricing_strategy  — pricing model, tiers, and discount behavior
4. market_share      — quantified position in the market
5. strategic_move    — recent actions signaling intent (funding, launches, M&A)
6. market_position   — customer segment focus and brand positioning
7. key_personnel     — leadership changes as leading indicators of strategic shifts

--- KEY PIVOT PATTERNS ---

competitor (company name):
  - ddg_search "[competitor] pricing" for pricing page and tier structure
  - google_news "[competitor]" last 6 months for press releases and news
  - web_search_fetch competitor website and /blog, /customers, /pricing pages
  - sec_edgar for public companies: 10-K, 10-Q for revenue and strategy sections
  - linkedin_profile company page for headcount, job postings, and recent posts

product_offering:
  - G2 / Capterra / Trustpilot reviews — feature mentions, complaints, comparisons
  - ddg_search "[competitor] vs [own product] OR [competitor] alternatives"
  - Patent filings (USPTO, Espacenet) for R&D direction signals
  - GitHub (public repos) for open-source product components and roadmap issues

pricing_strategy:
  - web_search_fetch competitor pricing page
  - ddg_search "[competitor] pricing 2024" for cached or historical pricing
  - Community discussions (Reddit, Hacker News) for actual pricing paid by users

strategic_move:
  - google_news "[competitor] acquisition" OR "[competitor] partnership" OR "[competitor] launch"
  - Crunchbase funding rounds and investor announcements
  - LinkedIn job postings for function-level investment signals
  - SEC filings (8-K) for material events: M&A, major contracts, executive changes

market_share:
  - Analyst reports (Gartner, IDC, Forrester) for market share data
  - SEC 10-K filings — management discussion often references competitive position
  - web_search "[market] market share [year]" for multiple analyst estimates

--- COMPLETENESS CHECKLIST ---

Before closing a competitive intelligence task, confirm coverage in each area:

1. Competitor Map      — direct and indirect competitors identified; emerging threats noted
2. Product Analysis    — features, differentiators, and gaps documented for each key competitor
3. Pricing             — pricing model and tier structure documented; discount signals noted
4. Market Position     — customer segments and geographic focus mapped per competitor
5. Financial Signals   — funding, revenue estimates, and headcount trends assessed
6. Strategic Intent    — recent strategic moves interpreted; forward-looking threats identified

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
