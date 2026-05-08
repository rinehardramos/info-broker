"""Legal research retrieval sub-strategy module."""

CATEGORY = "retrieval"
NAME = "legal_research"
DISPLAY_NAME = "Legal Research"
DESCRIPTION = (
    "Locates and synthesizes applicable statutes, case law, regulations, and legal "
    "commentary for a given legal question. Jurisdiction is always identified first. "
    "Does not constitute legal advice — for research and reference purposes only."
)
SELECTORS = [
    "legal_question",
    "jurisdiction",
    "statute",
    "case_citation",
    "regulation",
    "legal_concept",
    "party_name",
]

STRATEGY = """
=== LEGAL RESEARCH STRATEGY ===

This strategy guides the location and synthesis of applicable law for a given
legal question. Jurisdiction must be established before any research begins.
Sources are prioritized by legal authority: primary sources (statutes, regulations,
case law) over secondary sources (commentaries, treatises). This output is for
research and reference only and does not constitute legal advice.
Validate coverage using the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step legal research process:

1. JURISDICTION IDENTIFICATION — Determine the applicable legal system(s):
   - Federal vs. state/provincial vs. local jurisdiction
   - International or cross-border considerations
   - Regulatory jurisdiction (which agency governs)
   - Choice-of-law issues for multi-jurisdiction matters
   All subsequent research is scoped to the identified jurisdiction(s).

2. ISSUE SPOTTING — Break the legal question into discrete legal issues:
   - Identify the cause of action or legal theory
   - Spot procedural vs. substantive issues
   - Identify affirmative defenses or countervailing doctrines
   - Note threshold questions (standing, jurisdiction, statute of limitations)

3. PRIMARY LAW RESEARCH — Locate controlling legal authority:
   - Statutes: identify the governing statute(s) and read the relevant sections
   - Regulations: identify implementing regulations and agency guidance
   - Case law: find controlling precedent (highest court in jurisdiction)
   - Administrative decisions: relevant agency rulings and interpretations
   For each primary source, note: effective date, amendment history, and
   current validity (has it been repealed, overruled, or superseded?).

4. SECONDARY SOURCE SYNTHESIS — Use secondary sources for context and analysis:
   - Law review articles for doctrinal analysis and academic commentary
   - Treatises and practice guides for practitioner-oriented interpretation
   - Legal news (Law360, Above the Law, Bloomberg Law) for recent developments
   - Bar association ethics opinions for professional responsibility questions

5. CURRENCY CHECK — Verify all sources are current:
   - Check statute codification for amendments post the version located
   - Verify cases have not been overruled (Shepardize / KeyCite equivalent)
   - Check for pending legislation or regulations that may affect the analysis
   - Review recent case law for any shifts in judicial interpretation

--- PRIORITY SELECTORS (Legal Research) ---

Ordered by research leverage (highest first):

1. legal_question  — the specific legal issue driving the research
2. jurisdiction    — determines which law applies; must be established first
3. statute         — controlling legislative text; highest authority after Constitution
4. regulation      — administrative regulations implementing statutes
5. case_citation   — judicial interpretations; establishes precedent
6. legal_concept   — doctrinal framework guiding issue analysis
7. party_name      — for litigation research: find cases involving specific parties

--- KEY PIVOT PATTERNS ---

legal_question + jurisdiction:
  - ddg_search "[legal issue] law [jurisdiction]" for initial orientation
  - web_search_fetch official government websites: statutes.capitol.texas.gov,
    law.cornell.edu/uscode, ecfr.gov (US federal), EUR-Lex (EU), legislation.gov.uk (UK)
  - SEC filings and regulatory agency websites for financial regulatory questions
  - google_news "[legal issue] [jurisdiction] ruling" for recent case developments

statute:
  - web_search_fetch official codification (e.g., law.cornell.edu/uscode for US)
  - document_search for full statutory text including definitions section
  - ddg_search "[statute name] amendment [year]" for recent changes
  - Agency interpretation guidance: ddg_search "[statute] [agency] guidance OR FAQ"

case_citation:
  - Google Scholar (scholar.google.com) for free case law access
  - CourtListener (courtlistener.com) for US federal and state court opinions
  - web_search_fetch case name + court for official slip opinion
  - ddg_search "[case name] [citation] analysis" for academic commentary on the case

regulation:
  - ecfr.gov for US Code of Federal Regulations
  - Federal Register (federalregister.gov) for regulatory history and preambles
  - Agency websites for interpretive guidance, no-action letters, and FAQ documents
  - ddg_search "[agency] [regulatory topic] enforcement action" for agency priorities

party_name:
  - PACER (pacer.gov) for US federal court docket search
  - CourtListener for free docket access where available
  - ddg_search "[party name] lawsuit OR litigation OR judgment"
  - sec_edgar for SEC enforcement actions against named parties

--- COMPLETENESS CHECKLIST ---

Before closing a legal research task, confirm coverage in each area:

1. Jurisdiction       — controlling jurisdiction(s) identified; choice-of-law noted
2. Primary Law        — governing statute(s) and regulation(s) located and read
3. Case Law           — controlling precedent identified; circuit/appellate split noted if any
4. Currency           — all sources verified as current; amendments and overrulings checked
5. Secondary Sources  — treatise or law review commentary located for context
6. Gaps Flagged       — unsettled areas of law identified; pending legislative changes noted

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED

DISCLAIMER: This research output is for informational purposes only and does not
constitute legal advice. Consult a licensed attorney for legal guidance.
"""
