"""Market research retrieval sub-strategy module."""

CATEGORY = "retrieval"
NAME = "market_research"
DISPLAY_NAME = "Market Research"
DESCRIPTION = (
    "Systematic collection of customer, market, and industry data to inform "
    "product and business decisions. Synthesizes primary signals (reviews, "
    "forums) with secondary data (reports, filings) into validated insights."
)
SELECTORS = [
    "customer_segment",
    "pain_point",
    "buying_behavior",
    "industry",
    "product_category",
    "geography",
    "trend",
]

STRATEGY = """
=== MARKET RESEARCH STRATEGY ===

This strategy guides systematic collection and synthesis of customer, market, and
industry intelligence. It integrates primary signals (reviews, forums, social media)
with secondary data (analyst reports, regulatory filings, industry publications) to
produce validated insights. Validate coverage using the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step market research process:

1. RESEARCH SCOPE DEFINITION — Define the research objective precisely:
   - What decision does this research inform?
   - Which customer segments or industries are in scope?
   - What geographic markets are relevant?
   - What time horizon is relevant (current state vs. trends vs. future)?
   Vague scope leads to unfocused data collection. Be explicit.

2. SECONDARY RESEARCH — Gather existing data from published sources:
   - Analyst reports: Gartner, IDC, Forrester, IBISWorld, Statista
   - Industry publications and trade associations
   - Academic research and government statistics
   - SEC filings for public company market descriptions and segment data
   - News coverage for current market dynamics

3. PRIMARY SIGNAL MINING — Extract unfiltered customer voice from:
   - Product review platforms (G2, Capterra, Trustpilot, App Store, Play Store)
   - Community forums (Reddit, Stack Overflow, niche industry forums)
   - Social media discussions (Twitter/X, LinkedIn posts and comments)
   - Job postings as a proxy for company investment priorities
   Categorize signals by: pain point, feature request, competitor comparison,
   use case description, and satisfaction/dissatisfaction indicators.

4. TREND IDENTIFICATION — Surface emerging patterns:
   - Rising search volume for related terms (Google Trends proxy via search results)
   - New entrant activity (Crunchbase funding in the category)
   - Regulatory developments affecting the market
   - Technology shifts enabling new solutions or disrupting incumbents
   Cross-validate trends across at least two independent signal sources.

5. INSIGHT SYNTHESIS — Convert raw data into actionable findings:
   - Segment findings by customer type, geography, and use case
   - Quantify where possible (% of reviewers mentioning a pain point)
   - Distinguish validated insights (multi-source) from hypotheses (single-source)
   - Identify gaps in available data for further primary research

--- PRIORITY SELECTORS (Market Research) ---

Ordered by insight generation power (highest first):

1. pain_point         — unmet needs and frustrations; highest value for product development
2. customer_segment   — who experiences the problem; enables targeted solutions
3. buying_behavior    — decision criteria, purchase triggers, and buying process
4. trend              — directional shifts in customer needs and market conditions
5. product_category   — space being analyzed; scopes secondary research
6. industry           — vertical context; connects to industry-specific dynamics
7. geography          — regional variations in customer needs and market maturity

--- KEY PIVOT PATTERNS ---

pain_point:
  - G2 / Capterra reviews: search competitor products in the category; read 3-star reviews
    for balanced pain point signals; tag recurring themes
  - Reddit: ddg_search "site:reddit.com [product category] problems OR frustrations OR alternatives"
  - Twitter/X: google_news "[category] [pain keyword]" for recent public complaints
  - LinkedIn posts from practitioners discussing challenges in the domain

customer_segment:
  - linkedin_profile company page for employee titles and self-described roles
  - Job postings for the target segment reveal their technology stack and priorities
  - Community membership (which Slack groups, Discord servers, forums does this segment use?)
  - web_search_fetch industry association membership pages for segment characterization

buying_behavior:
  - G2 buyer intent data and review filters (company size, industry vertical)
  - ddg_search "[product] pricing" and "[product] ROI" for purchase justification signals
  - Sales enablement content from vendors (case studies reveal decision process)
  - Community posts: "I'm evaluating [category]" or "switching from X to Y"

trend:
  - google_news "[industry] trends [year]" for analyst and media trend coverage
  - Crunchbase category funding velocity as innovation investment signal
  - Patent filings (USPTO) for R&D direction in the category
  - web_search_fetch industry association annual reports for trend sections

industry:
  - sec_edgar 10-K filings: competitors' "Business" and "Risk Factors" sections
    for industry description and dynamics
  - Trade association websites for market sizing and industry structure data
  - IBISWorld or Statista industry reports for quantitative benchmarks

--- COMPLETENESS CHECKLIST ---

Before closing a market research task, confirm coverage in each area:

1. Customer Needs      — pain points and unmet needs documented from primary signals;
                         quantified where possible
2. Market Size         — addressable market estimated with source citations
3. Customer Segments   — key segments identified with distinguishing characteristics
4. Competitive Supply  — how the market is currently served; key solution types mapped
5. Trends              — at least 3 directional trends identified with supporting signals
6. Data Gaps           — areas requiring primary research flagged with justification

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
