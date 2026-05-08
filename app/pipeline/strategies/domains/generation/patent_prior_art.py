"""Patent prior art search generation sub-strategy module."""

CATEGORY = "generation"
NAME = "patent_prior_art"
DISPLAY_NAME = "Patent Prior Art Search"
DESCRIPTION = (
    "Systematic prior art search across patent databases and non-patent literature "
    "to assess novelty and non-obviousness of an invention. Produces an evidence-based "
    "patentability assessment with claim-level analysis."
)
SELECTORS = [
    "invention_concept",
    "claim_element",
    "ipc_class",
    "inventor",
    "assignee",
    "priority_date",
    "technical_field",
]

STRATEGY = """
=== PATENT PRIOR ART SEARCH STRATEGY ===

This strategy guides a systematic prior art search to assess the novelty and
non-obviousness of an invention. Coverage spans patent literature and non-patent
literature (NPL). The search produces an evidence-based patentability assessment
with claim-level prior art mapping. Validate coverage using the completeness
checklist before concluding.

--- EXECUTION MODEL ---

A 6-step patent prior art search process:

1. INVENTION DISCLOSURE ANALYSIS — Understand the invention before searching:
   - Identify the core inventive concept and technical problem being solved
   - Break the invention into discrete elements (claim elements)
   - Identify alternative technical terms and synonyms for each element
   - Note the priority date (prior art must predate this date)
   - Identify the relevant technical field(s) and International Patent Classification (IPC)

2. CLASSIFICATION SEARCH — Map the invention to patent classifications:
   - IPC (International Patent Classification): identify primary and secondary codes
   - CPC (Cooperative Patent Classification): more granular; used by USPTO and EPO
   - Search by classification alone to find art the inventor may not have described
     in the same terms
   - Use classification trees to identify adjacent technical areas

3. KEYWORD SEARCH — Construct comprehensive keyword search strings:
   - Combine independent claim elements with Boolean operators (AND, OR, NOT)
   - Include synonyms, technical variants, and layperson terms
   - Apply truncation and wildcard operators for morphological variants
   - Search in title, abstract, claims, and full description fields

4. PATENT DATABASE SEARCH — Execute searches across multiple patent offices:
   - Google Patents (patents.google.com): global coverage; natural language search
   - USPTO Patent Full-Text Database (patents.uspto.gov): US patents and applications
   - Espacenet (epo.org): European Patent Office; global coverage
   - WIPO PatentScope (patentscope.wipo.int): PCT applications; international coverage
   - J-PlatPat (j-platpat.inpit.go.jp): Japanese patents (machine translation available)
   For each relevant patent found, check its forward citations (later patents citing it)
   for updated art in the same space.

5. NON-PATENT LITERATURE (NPL) SEARCH — Prior art exists outside patent databases:
   - Scientific publications: Google Scholar, PubMed, arXiv, IEEE Xplore
   - Technical standards: ISO, IEEE, ANSI, IETF RFCs
   - Product manuals, datasheets, and commercial catalogs pre-priority date
   - Conference proceedings and theses
   - Internet Archive (archive.org) for web publications with a historical timestamp
   NPL is frequently overlooked and can invalidate a patent post-grant.

6. PATENTABILITY ASSESSMENT — Synthesize findings into a claim-level analysis:
   - Map each independent claim element to the closest prior art found
   - Identify any single reference disclosing all elements (novelty analysis)
   - Identify combinations of references that render the claim obvious (103 analysis)
   - Note claim elements for which no prior art was found (potential novelty basis)
   - Assess whether dependent claims offer patentable fallback positions

--- PRIORITY SELECTORS (Patent Prior Art Search) ---

Ordered by search leverage (highest first):

1. invention_concept  — the core idea; guides keyword and classification strategy
2. claim_element      — discrete technical elements; each must be searched
3. ipc_class          — classification code; finds art regardless of terminology
4. technical_field    — broadens search to adjacent technology areas
5. priority_date      — temporal cutoff; only art before this date is prior art
6. assignee           — competitor companies; find their related patent portfolios
7. inventor           — named inventors with prior work in the same space

--- KEY PIVOT PATTERNS ---

invention_concept + technical_field:
  - Google Patents natural language search for initial orientation and IPC suggestions
  - ddg_search "[invention concept] patent" for publicly discussed prior art
  - Espacenet "Advanced Search" with full-text keyword + IPC code combination
  - web_search_fetch Google Patents for the most relevant classification codes

claim_element:
  - Decompose each element into its functional and structural aspects
  - Search each element independently, then in combination with others
  - Find the "closest prior art" (single reference disclosing the most elements)
  - USPTO Patent Center for US application publication search (18-month publication lag)

ipc_class + priority_date:
  - Espacenet classification search filtered by date range before priority date
  - PatentScope classification search for PCT applications
  - USPC-to-CPC concordance for older US patents classified under legacy system

inventor + assignee:
  - Google Patents assignee and inventor search to map competitor patent portfolios
  - Derwent Innovation (subscription) for portfolio analytics
  - ddg_search "[company] patent portfolio [technical field]" for overview articles

technical_field (NPL):
  - Google Scholar "[invention concept]" filtered to before priority date
  - arXiv for physics, CS, and engineering preprints (note submission dates)
  - IEEE Xplore and ACM Digital Library for electrical and computing prior art

--- COMPLETENESS CHECKLIST ---

Before closing a patent prior art search, confirm coverage in each area:

1. Classification Search — IPC and CPC codes identified; classification-only search run
2. Keyword Search        — comprehensive keyword strings with synonyms and truncation
3. Patent Databases      — USPTO, Espacenet, Google Patents, and PatentScope all searched
4. Non-Patent Literature — Google Scholar, technical standards, and product literature searched
5. Claim Mapping         — each independent claim element mapped to closest prior art found
6. Patentability Summary — novelty and non-obviousness assessment documented with evidence

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
