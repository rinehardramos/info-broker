"""Fact checking retrieval sub-strategy module."""

CATEGORY = "retrieval"
NAME = "fact_checking"
DISPLAY_NAME = "Fact Checking"
DESCRIPTION = (
    "Verifies specific claims against authoritative primary sources. "
    "Every claim is evaluated against a multi-source corroboration standard "
    "with explicit confidence ratings and source reliability grades."
)
SELECTORS = [
    "claim",
    "source",
    "date_of_claim",
    "claimant",
    "context",
    "evidence_for",
    "evidence_against",
]

STRATEGY = """
=== FACT CHECKING STRATEGY ===

This strategy verifies specific factual claims against authoritative primary sources.
Every claim receives a verdict supported by corroborated evidence and explicit source
reliability ratings. The goal is truth-seeking, not confirmation. Contradictory
evidence is actively sought and documented. Validate coverage using the completeness
checklist before concluding.

--- EXECUTION MODEL ---

A 5-step fact-checking process:

1. CLAIM ISOLATION — Extract the specific claim to be verified:
   - State the claim as a falsifiable assertion (who, what, when, where)
   - Identify the claimant and the original source/context of the claim
   - Note the date the claim was made (claims may have been true at one time)
   - Disambiguate compound claims — verify each atomic assertion separately

2. PRIMARY SOURCE HUNT — Seek the authoritative source that would definitively
   confirm or refute the claim:
   - Government databases, official statistics, regulatory filings
   - Peer-reviewed publications for scientific/medical claims
   - Official statements, transcripts, and court records
   - For historical claims: archives, contemporaneous records, academic histories
   Do NOT rely on secondary reporting until primary sources are exhausted.

3. CORROBORATION — Find at least two independent sources that either:
   a. Both confirm the claim (verdict: TRUE / LIKELY TRUE)
   b. Both contradict it (verdict: FALSE / LIKELY FALSE)
   c. Conflict with each other (verdict: DISPUTED — document both sides)
   Single-source verification is insufficient for any material claim.

4. COUNTER-EVIDENCE SEARCH — Actively seek evidence that contradicts the claim:
   - ddg_search "[claim] false" OR "[claim] debunked" OR "[claim] misleading"
   - Check known fact-checking outlets (Snopes, PolitiFact, FactCheck.org,
     AFP Fact Check, Reuters Fact Check) for prior verdicts
   - Identify what a credible rebuttal would look like; search for it

5. VERDICT & CONFIDENCE RATING — Render a verdict with explicit confidence:
   - TRUE: confirmed by multiple authoritative independent sources
   - LIKELY TRUE: strong primary evidence; minor gaps or soft corroboration
   - UNVERIFIABLE: insufficient public evidence to confirm or deny
   - DISPUTED: credible sources reach conflicting conclusions
   - LIKELY FALSE: primary sources contradict; limited supporting evidence
   - FALSE: definitively contradicted by authoritative primary sources
   - MISLEADING: technically accurate but stripped of essential context

--- PRIORITY SELECTORS (Fact Checking) ---

Ordered by verification leverage (highest first):

1. claim           — the atomic assertion being verified
2. evidence_for    — sources and data supporting the claim
3. evidence_against — sources and data contradicting the claim
4. source          — original source of the claim (affects credibility baseline)
5. date_of_claim   — temporal context; facts change over time
6. claimant        — who made the claim; relevant to motive and expertise
7. context         — surrounding narrative that may affect interpretation

--- KEY PIVOT PATTERNS ---

claim (numeric/statistical):
  - Primary statistical sources: government databases (Census, BLS, CDC, Eurostat),
    international bodies (World Bank, WHO, IMF, UN), academic datasets
  - ddg_search "[statistic] [source agency]" to find the authoritative number
  - web_search_fetch source URL cited in the claim; read the actual document
  - Check if the cited statistic has been updated or superseded

claim (historical fact):
  - Academic databases (JSTOR, Google Scholar) for peer-reviewed historical accounts
  - National archives and primary document repositories
  - Encyclopedia references (Encyclopedia Britannica, academic subject encyclopedias)
  - ddg_search "[historical claim] historian" for scholarly consensus

claim (scientific/medical):
  - PubMed / Google Scholar for peer-reviewed research
  - Systematic reviews and meta-analyses (highest evidence level)
  - Regulatory body positions: FDA, CDC, WHO, EMA for medical claims
  - Science journalism: fact_checker outlets and science communication sites

claim (current events):
  - google_news "[claim keywords]" for news coverage from multiple outlets
  - Official statements and transcripts via web_search_fetch
  - Newswire services (AP, Reuters) for factual reporting baseline
  - Check dates carefully — recent events may lack complete documentation

source reliability check:
  - ddg_search "[source publication] bias" OR "[source] credibility rating"
  - MediaBiasFactCheck or similar for publication reliability history
  - Author background check for claimed expertise

--- COMPLETENESS CHECKLIST ---

Before closing a fact-checking task, confirm coverage in each area:

1. Claim Definition    — claim stated as a falsifiable assertion; compound claims separated
2. Primary Sources     — authoritative primary sources consulted before secondary sources
3. Corroboration       — at least two independent sources assessed per claim
4. Counter-Evidence    — active search for contradicting evidence completed; result documented
5. Verdict             — explicit verdict rendered with confidence level
6. Source Ratings      — reliability grade applied to each source used

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
