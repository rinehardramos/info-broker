"""Strategic assessment research strategy module."""

ENTITY_TYPE = "strategic_assessment"

STRATEGY = """
=== STRATEGIC ASSESSMENT STRATEGY ===

This strategy guides comprehensive strategic analysis using a multi-framework
cascade: PESTLE → Porter's Five Forces → SWOT → VRIO. Each framework builds on
the prior one, moving from macro-environment to industry to firm to resources.
Stakeholder perspectives must be incorporated. Validate coverage using the
completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step multi-framework strategic assessment:

1. PESTLE ANALYSIS — Map the macro-environmental forces shaping the strategic context:
   - Political: government stability, policy direction, regulatory posture, trade policy,
     political risk, geopolitical tensions affecting the domain
   - Economic: GDP growth, inflation, interest rates, exchange rates, unemployment,
     consumer spending trends, capital availability
   - Social: demographic shifts, consumer behavior changes, cultural trends, education
     levels, health trends, attitude toward the industry
   - Technological: emerging technologies, R&D investment trends, automation threats,
     digital transformation pace, IP and patent landscape
   - Legal: regulatory requirements, compliance obligations, intellectual property law,
     employment law, data privacy regulations, antitrust activity
   - Environmental: climate-related risks and opportunities, sustainability mandates,
     carbon regulations, resource scarcity, ESG investor pressure
   For each force: assess current state, direction of change (favorable/unfavorable),
   and time horizon (near-term vs. structural).

2. PORTER'S FIVE FORCES — Assess the structural attractiveness of the industry:
   - Threat of New Entrants: barriers to entry (capital, regulation, brand, network
     effects, switching costs), incumbent reactions to entry
   - Bargaining Power of Suppliers: concentration, switching costs, substitute inputs,
     importance of the industry to suppliers
   - Bargaining Power of Buyers: concentration, price sensitivity, switching costs,
     availability of substitutes, buyer information
   - Threat of Substitutes: availability of substitute products/services, relative
     price-performance of substitutes, buyer propensity to switch
   - Competitive Rivalry: number and size of competitors, industry growth rate,
     product differentiation, exit barriers, price war risk
   For each force: rate intensity (Low/Medium/High) and assess trend (strengthening/
   stable/weakening). Conclude with overall industry attractiveness.

3. SWOT ANALYSIS — Assess the entity's position within the PESTLE/Five Forces context:
   - Strengths: internal capabilities and resources that provide competitive advantage
   - Weaknesses: internal gaps, limitations, or disadvantages versus competitors
   - Opportunities: external conditions (from PESTLE/Five Forces) the entity can exploit
   - Threats: external conditions (from PESTLE/Five Forces) that could harm the entity
   Ensure SWOT is grounded in the macro and industry analysis above — not generated
   in isolation. Cross-reference: O and T should trace to PESTLE/Five Forces findings.

4. VRIO ANALYSIS — Assess which resources and capabilities are sources of sustainable
   competitive advantage:
   - Valuable: does the resource help exploit opportunities or neutralize threats?
   - Rare: do few or no competitors possess this resource or capability?
   - Inimitable: is it difficult to imitate (path dependency, causal ambiguity, social
     complexity)?
   - Organized: is the entity organized to capture the value from the resource?
   For each key resource/capability: rate V/R/I/O (yes/no), determine competitive
   implication (disadvantage / parity / temporary advantage / sustained advantage).

5. STAKEHOLDER PERSPECTIVES — Integrate the views of key stakeholders into the assessment:
   - Identify primary stakeholders (customers, investors, employees, regulators,
     suppliers, community)
   - For each: assess their strategic interests, level of influence, and alignment
     with the entity's strategic direction
   - Identify stakeholder conflicts that constrain strategic options
   - Map stakeholder power/interest grid to prioritize engagement

--- PRIORITY SELECTORS (Strategic Assessment) ---

Ordered by research leverage (highest priority first):

1. strategic_entity   — the organization, product, or initiative being assessed
2. industry_context   — the industry and competitive landscape (Five Forces focus)
3. macro_environment  — PESTLE forces shaping the external context
4. resource           — internal capabilities and assets subject to VRIO analysis
5. competitor         — specific competitors and their strategic positions
6. stakeholder        — key stakeholder groups and their interests
7. strategic_option   — candidate strategic moves being evaluated

--- KEY PIVOT PATTERNS ---

macro_environment (PESTLE):
  - World Bank, IMF data portals for economic indicators
  - OECD Policy Tracker, government websites for regulatory changes
  - Gartner, Forrester for technology trend signals
  - ESG rating agency reports (MSCI, Sustainalytics) for environmental/regulatory signals

industry_context (Five Forces):
  - IBISWorld, Statista, Mintel for industry structure reports
  - SEC 10-K filings: competition and risk sections for incumbent perspectives
  - Crunchbase for entry threat signals (funding velocity in the industry)
  - Porter (1979) "How Competitive Forces Shape Strategy" as methodological foundation

competitor (SWOT/VRIO):
  - Annual reports, investor presentations for stated strategic priorities
  - LinkedIn, Glassdoor for capability signals (hiring patterns, org structure)
  - Patent databases for R&D capability indicators
  - Customer reviews (G2, Capterra, Trustpilot) for perceived strengths/weaknesses

resource (VRIO):
  - Patent portfolio analysis for proprietary technology
  - Brand strength indices (Interbrand, Brand Finance) for brand assets
  - Supplier agreements, exclusive contracts for positional advantages
  - HR data, talent surveys for organizational capability assessment

stakeholder:
  - Investor relations materials, activist investor filings (13D/13G)
  - Regulatory comment letters and agency enforcement actions
  - Customer satisfaction surveys and NPS data
  - Employee engagement surveys and Glassdoor ratings

--- INVESTIGATION PRINCIPLES ---

FRAMEWORK CASCADE DISCIPLINE
  Do not begin SWOT before completing PESTLE and Five Forces. The O and T in SWOT
  must derive from the external analysis. SWOT generated in isolation is anecdotal.

VRIO RIGOR
  Most resources are valuable and rare. The real differentiator is inimitability.
  Investigate the causal mechanisms of inimitability (history, complexity, ambiguity)
  before claiming sustained competitive advantage.

STAKEHOLDER INTEGRATION
  Strategic options that ignore key stakeholder interests fail at implementation.
  Incorporate stakeholder analysis before finalizing strategic recommendations.

FIVE FORCES CALIBRATION
  Rate each force and its trend, not just its current state. A force rated Medium
  but strengthening is more strategically significant than one rated High but stable.

--- COMPLETENESS CHECKLIST ---

Before closing a strategic assessment task, confirm coverage in each area:

1. PESTLE Applied        — all 6 PESTLE dimensions analyzed; direction of change and
                           time horizon assessed for each material force
2. Five Forces Assessed  — all 5 forces rated (Low/Medium/High); trend direction
                           noted; overall industry attractiveness concluded
3. SWOT Completed        — S/W/T/O populated with evidence; O and T traced to
                           PESTLE/Five Forces findings; not generated in isolation
4. Stakeholder Views     — primary stakeholders identified; power/interest assessed;
                           conflicts constraining strategic options noted
5. Strategic Options     — at least 3 strategic options generated; each assessed
                           against VRIO for sustainability; recommendation stated

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
