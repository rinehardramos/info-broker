"""Academic researcher investigation strategy module."""

ENTITY_TYPE = "researcher"

STRATEGY = """
=== ACADEMIC RESEARCH STRATEGY ===

This strategy maps the scholarly identity and output of an academic researcher.
The goal is a complete publication record, institutional affiliations, research
network (co-authors, advisors, students), and citation impact. Social media and
breach lookups are out of scope unless the requester specifies otherwise.

--- EXECUTION MODEL ---

A 4-step citation-graph process:

1. SEED — Accept full_name, employer (university/institution), domain
   (institutional email domain), or ORCID / Google Scholar ID.

2. ANCHOR — Resolve the researcher's canonical identity on at least one
   academic index (Google Scholar, OpenAlex, Semantic Scholar). Disambiguate
   by institution and field when the name is common.

3. EXPAND — From the canonical profile, extract:
   - Full publication list (title, venue, year, DOI)
   - Co-author network (names, institutions)
   - Cited-by graph for highly-cited works (top 10 by citation count)

4. GAP-FILL — Review the COMPLETENESS CHECKLIST. For each unchecked domain,
   attempt at least one targeted lookup before closing.

--- PRIORITY SELECTORS (Researcher) ---

Ordered by disambiguation power (highest priority first):

1. full_name          — anchor; requires institution for disambiguation
2. employer           — university or research institution name
3. domain             — institutional email domain (e.g., mit.edu, ox.ac.uk)
4. orcid_id           — globally unique researcher identifier; highest precision
5. scholar_id         — Google Scholar profile ID
6. openalex_id        — OpenAlex author ID

--- KEY PIVOT PATTERNS ---

full_name → Google Scholar (via run_multi_search):
  - Query: site:scholar.google.com "full_name" "institution"
  - Extract: Scholar ID → publications → cited-by counts → co-authors

full_name → OpenAlex (via run_openalex_search):
  - Author search by name + institution filter
  - Extract: works list, concepts, institution affiliations, citation metrics

full_name → Semantic Scholar (via run_semantic_scholar):
  - Author search → paper list → influential citations → co-author graph
  - Extract: h-index, citation count, fields of study

orcid_id:
  - Direct ORCID API lookup → employment history, education, works list
  - Cross-reference with OpenAlex for citation counts

employer (institution):
  - Institutional faculty page scrape (run_multi_search: site:institution.edu "full_name")
  - Extract: lab affiliation, research group, office contact

publications (DOI):
  - CrossRef API (via run_multi_search) → full metadata, funding sources
  - Unpaywall lookup → open-access PDF availability

--- INVESTIGATION PRINCIPLES ---

DISAMBIGUATION FIRST
  Common names (e.g., "John Smith") must be disambiguated by institution and
  field before pivoting. A misidentified researcher poisons the entire record.

CITATION GRAPH DEPTH
  For highly-cited researchers, trace the cited-by graph one level deep to
  surface prominent works and their impact. Do not recurse further.

INSTITUTIONAL CORROBORATION
  Confirm affiliation via at least two sources: the academic index profile AND
  the institution's own faculty/staff directory or personal page.

CO-AUTHOR NETWORK
  List co-authors from the 10 most-cited works. Do not expand each co-author
  into a full researcher profile unless the requester authorizes it.

--- COMPLETENESS CHECKLIST ---

Before closing a researcher investigation, confirm at least one data point
per domain:

1. Identity          — full legal name, known name variants, ORCID (if public)
2. Publications      — complete or near-complete works list with venues and DOIs
3. Affiliations      — current institution + department; past institutions (career arc)
4. Research network  — top co-authors with institutions; advisor/advisee links (if findable)

Mark each domain as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
