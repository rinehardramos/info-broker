"""Patent landscape synthesis sub-strategy module."""

CATEGORY = "synthesis"
NAME = "patent_landscape"
DISPLAY_NAME = "Patent Landscape Analysis"
DESCRIPTION = (
    "Synthesizes the patent landscape for a technology domain to reveal ownership "
    "concentration, white space opportunities, filing trends, and freedom-to-operate "
    "risks. Produces a structured intelligence map across key dimensions."
)
SELECTORS = [
    "technology_domain",
    "ipc_class",
    "assignee",
    "filing_trend",
    "white_space",
    "key_patent",
    "freedom_to_operate",
]

STRATEGY = """
=== PATENT LANDSCAPE ANALYSIS STRATEGY ===

This strategy synthesizes the full patent landscape for a technology domain to
reveal ownership concentration, filing trends, white space opportunities, and
freedom-to-operate (FTO) risks. The output is a structured intelligence map
supporting R&D strategy, IP portfolio planning, and competitive positioning.
This output is for research purposes only and does not constitute legal advice.
Validate coverage using the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step patent landscape analysis process:

1. SCOPE DEFINITION — Establish the landscape boundaries:
   - Technology domain: define precisely using technical terminology
   - IPC/CPC classification codes: identify primary and secondary codes
   - Geographic scope: which patent offices to cover (US, EP, JP, CN, WO/PCT)
   - Temporal scope: date range for filing trend analysis (typically 10-20 years)
   - Exclusions: related technologies explicitly out of scope
   Document the search strategy so the landscape is reproducible.

2. DATA COLLECTION — Build the patent corpus:
   - Execute classification searches across USPTO, Espacenet, Google Patents, PatentScope
   - Execute keyword searches using the technology's technical vocabulary
   - Combine both: classification AND keyword to maximize recall
   - Deduplicate patent families (a patent family = one invention in multiple countries)
   - Target corpus size: typically 500-5,000 unique patent families for meaningful analysis
   Record: total patents retrieved, search query used, databases searched, date of search

3. ASSIGNEE ANALYSIS — Map ownership concentration and competitive positions:
   - Rank assignees by patent family count in the corpus
   - Identify: dominant players, challengers, academic/government players, NPEs/PAEs
   - Track assignee M&A: acquired IP portfolios (merger of assignee names over time)
   - Geographic distribution of ownership: which countries dominate the IP landscape?
   - Identify assignees with rapidly growing portfolios (acceleration signals)

4. TECHNOLOGY MAPPING — Understand what is patented and where gaps exist:
   - Subfield decomposition: segment patents into technology sub-areas using CPC codes
   - White space identification: which combinations of features have few or no patents?
   - Concentration mapping: which sub-areas are over-patented? (risk areas for FTO)
   - Claim scope analysis for the most-cited patents: broad vs. narrow claims
   - Dependency chains: which foundational patents does the technology build on?

5. TREND ANALYSIS & SYNTHESIS — Synthesize findings into strategic intelligence:
   - Filing velocity trend: is patenting activity growing, stable, or declining?
   - Geographic filing trend: which patent offices are receiving more filings?
     (signals where assignees expect commercial activity)
   - Technology evolution: which sub-areas were hot 10 years ago vs. now?
   - Expiry timeline: when do key blocking patents expire? (freedom-to-operate windows)
   - Summary intelligence map: white spaces, risk zones, dominant players per sub-area

--- PRIORITY SELECTORS (Patent Landscape Analysis) ---

Ordered by landscape intelligence value (highest first):

1. technology_domain   — the innovation space being mapped; defines corpus scope
2. ipc_class           — classification codes; enables systematic, terminology-independent search
3. assignee            — IP ownership; reveals competitive positions and concentration
4. white_space         — unpatented sub-areas; R&D opportunity zones
5. filing_trend        — directional signal for technology investment and competitive activity
6. key_patent          — foundational or blocking patents requiring detailed analysis
7. freedom_to_operate  — FTO risk zones; guides product development and launch decisions

--- KEY PIVOT PATTERNS ---

technology_domain + ipc_class:
  - Google Patents classification search: filter by IPC/CPC code + date range
  - Espacenet advanced search: CPC code + date range + assignee country
  - WIPO PatentScope for PCT applications: IPC code search with full-text options
  - USPTO Patent Center: classification search tool for US-only corpus

assignee analysis:
  - Google Patents: search "[technology keyword]" → filter by assignee → rank by count
  - ddg_search "[technology domain] patent portfolio [company]" for published analyses
  - Derwent Innovation (subscription) for assignee analytics and M&A tracking
  - Patent citation analysis: who cites whom reveals the influence hierarchy

white_space identification:
  - CPC subclass frequency distribution: low-count sub-areas are candidate white spaces
  - Combination analysis: which {feature A} + {feature B} combinations are unpatented?
  - ddg_search "[technology domain] patent gap" OR "[domain] freedom to operate"
  - Academic prior art may fill apparent gaps — NPL search before declaring white space

filing_trend:
  - Google Patents year filter: compare total filings per 2-year period
  - PatentScope statistics (patentscope.wipo.int/patentscope/en/statistics.jsf) for PCT trends
  - National patent office statistics publications for jurisdiction-level trends

key_patent:
  - High citation count: Google Patents "cited by" count for importance signal
  - Fundamental patents: early priority dates in the technology; broad independent claims
  - web_search_fetch key patent number for full text and independent claim scope
  - Patent history: prosecution history (file wrapper) for claim scope amendments

freedom_to_operate:
  - Identify patents with broad independent claims covering proposed product features
  - Expiry calculation: filing date + 20 years = expiry; check maintenance fee status
  - ddg_search "[patent number] FTO" OR "[patent number] freedom to operate analysis"
  - Note: definitive FTO opinion requires a qualified patent attorney

--- COMPLETENESS CHECKLIST ---

Before closing a patent landscape analysis, confirm coverage in each area:

1. Search Strategy     — IPC codes identified; keyword + classification search documented;
                         databases and date range recorded
2. Assignee Map        — top 15+ assignees ranked; ownership concentration assessed
3. Technology Map      — sub-areas identified; patent density per sub-area assessed
4. White Space         — low-density areas identified; NPL checked to confirm true gaps
5. Filing Trends       — temporal trend assessed; geographic filing shifts noted
6. FTO Risks           — high-priority blocking patents identified; expiry dates noted

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED

DISCLAIMER: This analysis is for informational purposes only and does not constitute
legal advice or a formal freedom-to-operate opinion. Consult a qualified patent attorney
for FTO determinations.
"""
