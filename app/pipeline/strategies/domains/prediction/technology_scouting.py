"""Technology scouting prediction sub-strategy module."""

CATEGORY = "prediction"
NAME = "technology_scouting"
DISPLAY_NAME = "Technology Scouting"
DESCRIPTION = (
    "Systematically identifies emerging technologies that could impact a business "
    "or industry. Maps technology readiness levels, key actors, and strategic "
    "windows to prioritize monitoring and engagement."
)
SELECTORS = [
    "technology_domain",
    "use_case",
    "trl_level",
    "research_institution",
    "startup",
    "patent_assignee",
    "time_to_market",
]

STRATEGY = """
=== TECHNOLOGY SCOUTING STRATEGY ===

This strategy systematically identifies and evaluates emerging technologies that
could create strategic opportunities or threats for an organization or industry.
It maps the technology landscape from basic research through commercialization,
assesses Technology Readiness Levels (TRL), and identifies key actors. Validate
coverage using the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step technology scouting process:

1. SCOUTING SCOPE DEFINITION — Establish search boundaries:
   - What business function or industry is being addressed?
   - What is the strategic objective? (innovation adoption, competitive monitoring,
     partnership scouting, IP strategy, investment identification)
   - What is the time horizon for relevance? (1-2 years, 3-5 years, 5-10 years)
   - Which technology domains are in scope? Which are explicitly out of scope?
   - What TRL range is relevant? (early-stage research vs. near-commercial)

2. TECHNOLOGY LANDSCAPE MAPPING — Build a structured view of the technology space:
   - Identify technology families: group related technologies by underlying principle
   - Assess TRL (Technology Readiness Level) for each technology:
     TRL 1-3: basic research; TRL 4-6: development and validation; TRL 7-9: deployment
   - Identify technology enablers: upstream technologies that unlock downstream applications
   - Note technology convergence: where two separate technology trends are combining
   - Use Gartner Hype Cycle framing to assess maturity and trough of disillusionment risk

3. ACTOR MAPPING — Identify who is developing each technology:
   - Academic research: universities, national labs, research centers
   - Startups: early-stage companies building commercial applications
   - Incumbents: established companies investing in the space
   - Government programs: national R&D programs, DARPA/ARPA equivalents, EU Horizon
   - Key individuals: principal investigators, technical founders, prolific inventors
   For each actor: assess funding level, publication/patent output, and commercial traction.

4. COMMERCIALIZATION SIGNAL ASSESSMENT — Gauge time-to-market:
   - Patent filing velocity: increasing filings = accelerating investment
   - Funding velocity: VC deal count and size in the category
   - Publication-to-patent ratio: high patent share = commercialization focus
   - Regulatory pathway: FDA, FCC, FAA clearance timelines for regulated applications
   - Pilot and deployment announcements: press releases, conference presentations

5. STRATEGIC WINDOW ANALYSIS — Identify timing and engagement options:
   - Adoption window: when will the technology be mature enough for deployment?
   - Competitive window: when will early movers gain durable advantages?
   - Engagement options: build, buy, partner, license, invest, monitor
   - Risk assessment: technology, regulatory, market adoption, and IP risks per technology
   Prioritize technologies by: strategic fit × readiness × competitive urgency.

--- PRIORITY SELECTORS (Technology Scouting) ---

Ordered by scouting leverage (highest first):

1. technology_domain   — anchor for all search and mapping activities
2. use_case            — practical application context; connects technology to business value
3. trl_level           — readiness filter; scopes monitoring vs. adoption vs. investment
4. startup             — commercial validation signal; indicates near-market maturity
5. research_institution — academic origin; identifies where next-generation work is happening
6. patent_assignee     — who owns the IP; signals who controls commercialization
7. time_to_market      — urgency filter for strategic prioritization

--- KEY PIVOT PATTERNS ---

technology_domain (landscape scan):
  - MIT Technology Review (technologyreview.com): "10 Breakthrough Technologies" lists
  - Gartner Hype Cycle reports by technology domain
  - google_news "[technology domain] breakthrough" OR "[technology] startup funding [year]"
  - arXiv, bioRxiv, Nature, Science for academic research signal
  - ddg_search "[technology domain] emerging companies [year]"

startup (commercialization signal):
  - Crunchbase: category search for funding rounds, investor participation, headcount
  - PitchBook (if accessible) for deal terms and valuation data
  - AngelList for seed-stage companies in the space
  - Y Combinator batch lists for recent cohorts in the technology area
  - ddg_search "[technology] startup [year] funding"

research_institution:
  - Google Scholar: "[technology domain]" filtered by institution for volume and impact
  - NIH Reporter (reporter.nih.gov) for NIH-funded research programs
  - ARPA programs (DARPA, ARPA-E, ARPA-H) for US government-funded cutting-edge R&D
  - EU CORDIS (cordis.europa.eu) for EU Horizon-funded research consortia
  - University tech transfer offices for licensed inventions

patent_assignee:
  - Google Patents assignee search for top filers in the technology domain
  - USPTO Patent Center for assignee-filtered search
  - ddg_search "[technology domain] patent portfolio [company]" for portfolio analyses
  - Patent landscape reports (WIPO, EPO) for filed comprehensive analyses

trl_level assessment:
  - DARPA program descriptions for TRL 4-6 defense research
  - NASA TRL definitions as reference for assessment calibration
  - Company white papers and investor decks for TRL claims (verify against evidence)
  - ddg_search "[technology] technology readiness" OR "[technology] commercial deployment"

--- COMPLETENESS CHECKLIST ---

Before closing a technology scouting task, confirm coverage in each area:

1. Technology Landscape  — technology families mapped; TRL assessed for each
2. Actor Map             — academic, startup, incumbent, and government actors identified
3. Patent Intelligence   — top patent assignees and filing velocity assessed
4. Funding Signals       — VC investment and government program funding assessed
5. Commercialization     — time-to-market estimated; regulatory pathway noted
6. Strategic Priorities  — technologies ranked by strategic fit, readiness, and urgency

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
