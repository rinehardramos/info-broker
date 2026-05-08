"""Product innovation generation sub-strategy module."""

CATEGORY = "generation"
NAME = "product_innovation"
DISPLAY_NAME = "Product Innovation"
DESCRIPTION = (
    "Generates novel product concepts by grounding ideation in user needs, SOTA "
    "scanning, and feasibility assessment. Follows the Design Thinking empathy "
    "phase before diverging into solution space."
)
SELECTORS = [
    "user_need",
    "target_persona",
    "problem_statement",
    "prior_art",
    "gap",
    "constraint",
    "competitor",
]

STRATEGY = """
=== PRODUCT INNOVATION STRATEGY ===

This strategy guides research toward generating novel product concepts by grounding
ideation in real user needs, thorough SOTA scanning, and disciplined feasibility
assessment. Follow the Design Thinking empathy phase before diverging into solution
space. Validate coverage using the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 6-step user-centered innovation process:

1. EMPATHY (Design Thinking) — Begin with the user. Collect user research, pain-point
   interviews, jobs-to-be-done (JTBD) analyses, and behavioral data. Document the
   target persona, their context, and the unmet need with specificity. Do not generate
   solutions until the user need is precisely understood.

2. PROBLEM DEFINITION — Translate empathy findings into a crisp problem statement:
   "How might we [enable persona] to [accomplish goal] despite [constraint]?"
   Decompose into sub-problems. Rank sub-problems by user impact.

3. STATE-OF-THE-ART SCAN — Search patents, product databases (ProductHunt, G2, Crunchbase),
   academic literature, and open-source for existing solutions. Document feature sets,
   user ratings, identified shortcomings, and market traction. Record what has been tried.

4. GAP-DRIVEN INNOVATION — Map SOTA findings against the ranked user needs. Identify:
   - Underserved needs with no adequate existing solution
   - Pain points that existing products handle poorly
   - Constraints (cost, accessibility, UX) that current solutions fail to meet
   Each gap is a candidate innovation target.

5. CROSS-DOMAIN TRANSFER — For each gap, search adjacent domains for analogous solutions.
   Apply TRIZ inventive principles to map cross-domain mechanisms back to the product
   problem. Example: logistics optimization principles applied to UX flow problems.

6. FEASIBILITY ASSESSMENT — Score each candidate product concept on:
   - Technical feasibility (can it be built with current technology?)
   - Market feasibility (will users pay? Is the market large enough?)
   - Operational feasibility (can it be manufactured, distributed, supported?)
   - Regulatory/ethical feasibility (compliance, privacy, safety)
   Rank by expected user value vs. total effort. Flag speculative concepts clearly.

--- PRIORITY SELECTORS (Product Innovation) ---

Ordered by research leverage (highest priority first):

1. user_need         — the core unmet need driving the innovation search
2. target_persona    — who experiences the problem; demographic and behavioral context
3. problem_statement — precise HMW framing derived from empathy research
4. prior_art         — existing products, patents, and academic work on the problem
5. gap               — identified insufficiency in current solutions
6. constraint        — hard limits (budget, regulation, physical, UX) bounding solutions
7. competitor        — existing market players whose weaknesses define the opportunity

--- KEY PIVOT PATTERNS ---

user_need:
  - search user forums, Reddit, App Store reviews for recurring complaints
  - JTBD interviews: "what are you trying to get done when you use X?"
  - market research reports (Gartner, Nielsen, Forrester) for unmet segment needs
  - web_search "pain points in [domain]" OR "users frustrated with [product category]"

target_persona:
  - demographic databases and survey platforms for behavioral segmentation
  - ethnographic study reports and usability research publications
  - community forums and social listening for authentic user voice

gap:
  - Product review platforms (G2, Capterra, Trustpilot) for recurring negative themes
  - Patent gap analysis: find problem areas with filing density but poor user ratings
  - Academic "limitations" and "future work" sections from HCI and design papers

prior_art:
  - USPTO, EPO, Google Patents — search by problem domain, not just solution
  - ProductHunt, BetaList for early-stage products addressing the problem
  - GitHub for open-source implementations and their issue trackers (real pain points)

competitor:
  - Crunchbase for funding signals and investor theses (market validation)
  - Web_search "[competitor] limitations" or "[competitor] vs [competitor]"
  - SWOT analysis of top 3 competitors to identify exploitable weaknesses

--- INVESTIGATION PRINCIPLES ---

EMPATHY BEFORE IDEATION
  Do not generate product concepts before completing the empathy phase. Solutions
  designed without validated user need fail at adoption regardless of technical quality.

CROSS-DOMAIN TRANSFER
  Product breakthroughs often import mechanisms from unrelated fields. Invest at least
  one search round in non-obvious analogous domains before generating concepts.

GAP-DRIVEN INNOVATION
  Every concept must trace to an identified gap or unmet user need. Solutions that merely
  replicate existing products are not innovations — they are copies.

FEASIBILITY FIRST
  A product that cannot be built, sold, or supported is not a product. Apply feasibility
  filters early to avoid investing in unviable concepts. Flag speculative ideas clearly.

--- COMPLETENESS CHECKLIST ---

Before closing a product innovation research task, confirm coverage in each area:

1. User Needs           — persona documented; JTBD and pain points validated with evidence
2. SOTA                 — existing products, patents, and academic work catalogued
3. Gap                  — at least 3 distinct, user-validated gaps identified and ranked
4. Solution Space       — at least 3 candidate product concepts generated per top gap
5. Feasibility          — each top concept assessed across technical, market, and operational dimensions
6. Competitive          — key market players identified; exploitable weaknesses documented
   Landscape

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
