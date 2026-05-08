"""VC deal evaluation prediction sub-strategy module."""

CATEGORY = "prediction"
NAME = "vc_deal_evaluation"
DISPLAY_NAME = "VC Deal Evaluation"
DESCRIPTION = (
    "Due diligence research for venture capital investment decisions. Covers "
    "market sizing, competitive landscape, team background, product-market fit "
    "signals, and comparable exit analysis to inform investment thesis."
)
SELECTORS = [
    "company_name",
    "founder",
    "market",
    "product",
    "revenue_stage",
    "competitor",
    "comparable_exit",
]

STRATEGY = """
=== VC DEAL EVALUATION STRATEGY ===

This strategy guides research for venture capital investment due diligence.
It systematically assesses market opportunity, competitive dynamics, team quality,
product-market fit signals, and comparable exit data to inform an investment thesis.
All findings should be corroborated with multiple sources. Validate coverage using
the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 6-step VC deal evaluation process:

1. MARKET OPPORTUNITY — Validate the market size and timing thesis:
   - TAM/SAM/SOM analysis: is this a large enough market to support a venture outcome?
   - Market timing: why is this the right time? What has changed to make this possible?
   - Market structure: fragmented (greenfield opportunity) or consolidated (displacement)?
   - Regulatory tailwinds/headwinds: is the regulatory environment favorable?
   - Customer willingness to pay: evidence of validated demand at the proposed price point

2. COMPETITIVE LANDSCAPE — Map competitive threats and positioning:
   - Direct competitors: funded startups, incumbent solutions, DIY alternatives
   - Competitive moat: network effects, switching costs, proprietary data, regulatory,
     scale economies, brand — which if any does this company have?
   - Incumbent response risk: how quickly can a large player replicate this?
   - International comparables: has this model worked in another geography?

3. TEAM DUE DILIGENCE — Assess founder quality and team composition:
   - Domain expertise: has the team operated in this space before?
   - Execution track record: prior company building, scaling, or technical accomplishments
   - Founder-market fit: is this team uniquely positioned to win this market?
   - Reference signals: what do others in the industry say about these founders?
   - Team completeness: are critical functions covered (technical, commercial, operational)?

4. PRODUCT & TRACTION — Evaluate product quality and market fit signals:
   - Product differentiation: what is genuinely unique? Is it defensible?
   - Traction metrics: revenue growth rate, retention/churn, NPS, referral rates
   - Customer quality: logo quality, concentration risk, expansion revenue signals
   - Product-market fit indicators: organic growth, high retention, customer desperation signal
   - Technology risk: is the core technology proven or still a research bet?

5. FINANCIAL & UNIT ECONOMICS — Assess business model viability:
   - Current and projected ARR / revenue trajectory
   - CAC and LTV: is the unit economics model sound?
   - Burn rate and runway: how long before the next raise is needed?
   - Path to profitability or next milestone: what does the capital achieve?
   - Capitalization: cap table cleanliness, prior round terms, option pool size

6. COMPARABLE EXIT ANALYSIS — Size the return potential:
   - Public comparables: revenue multiples of public companies in the same category
   - M&A comparables: recent acquisition multiples (revenue, ARR, strategic premium)
   - IPO comparables: recent IPOs in adjacent spaces for implied valuation multiples
   - Return modeling: at current trajectory, what return multiple is achievable at 5-7 years?
   - Ownership math: target ownership × exit valuation = required outcome size

--- PRIORITY SELECTORS (VC Deal Evaluation) ---

Ordered by diligence leverage (highest first):

1. market              — market size and dynamics; is there a venture-scale opportunity?
2. company_name        — anchor for all research; company website, filings, news
3. founder             — team quality; often the strongest predictor of outcome
4. product             — product differentiation and technical moat assessment
5. revenue_stage       — traction signal; anchors financial and unit economics analysis
6. competitor          — competitive landscape and defensibility of positioning
7. comparable_exit     — return potential calibration against precedent transactions

--- KEY PIVOT PATTERNS ---

market:
  - Analyst reports (Gartner, IDC, Forrester) for market sizing benchmarks
  - sec_edgar 10-K filings of public comparables for market description and sizing
  - Crunchbase category page for total funding deployed in the market (demand signal)
  - google_news "[market] growth" OR "[market] venture funding" for current dynamics

company_name:
  - web_search_fetch company website for product, positioning, and team information
  - Crunchbase company profile for funding history, investors, and headcount
  - ddg_search "[company name] revenue" OR "[company name] ARR" for financial signals
  - google_news "[company name]" last 12 months for press coverage and announcements

founder:
  - linkedin_profile for employment history, education, and prior startup experience
  - ddg_search "[founder name] [prior company]" for prior startup outcomes
  - google_news "[founder name]" for press coverage and speaking engagements
  - Patent search (Google Patents) for technical founders' prior IP work

competitor:
  - Crunchbase competitor profiles for funding parity and investor quality
  - G2 / Capterra for product review comparisons and positioning
  - sec_edgar for public competitor revenue and market descriptions
  - ddg_search "[competitor] vs [company]" for analyst and user comparisons

comparable_exit:
  - Crunchbase M&A tab for recent acquisitions in the category with deal terms
  - sec_edgar for public acquisition filings (8-K, proxy) with disclosed deal values
  - PitchBook (if accessible) for transaction comparables
  - google_news "[category] acquisition [year]" for recent deal coverage

--- COMPLETENESS CHECKLIST ---

Before closing a VC deal evaluation task, confirm coverage in each area:

1. Market Opportunity   — TAM/SAM sized; timing thesis and market structure documented
2. Competitive Moat     — differentiation and defensibility assessed; incumbent risk noted
3. Team Assessment      — founder track record and domain expertise documented
4. Traction Signals     — PMF indicators, growth rate, and retention assessed
5. Unit Economics       — CAC/LTV, burn rate, and next-milestone capital allocation reviewed
6. Return Potential     — comparable exits and return multiple modeling documented

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
