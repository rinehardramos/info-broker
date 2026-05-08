"""Grounded theory explanation sub-strategy module."""

CATEGORY = "explanation"
NAME = "grounded_theory"
DISPLAY_NAME = "Grounded Theory Analysis"
DESCRIPTION = (
    "Builds explanatory theories from empirical data using iterative coding, "
    "constant comparison, and theoretical saturation. Produces a substantive "
    "theory grounded in evidence rather than imposed from prior frameworks."
)
SELECTORS = [
    "data_source",
    "open_code",
    "axial_code",
    "selective_code",
    "category",
    "core_concept",
    "theoretical_saturation",
]

STRATEGY = """
=== GROUNDED THEORY ANALYSIS STRATEGY ===

This strategy builds explanatory theories from empirical data using the grounded
theory method developed by Glaser and Strauss. It moves from raw data through
iterative coding stages to a substantive theory. The theory is grounded in the
data — not imposed from prior frameworks. Theoretical saturation determines when
data collection ends. Validate coverage using the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step grounded theory process:

1. DATA COLLECTION & OPEN CODING — Gather data and label concepts without preconceptions:
   - Identify and collect relevant data sources: interview transcripts, forum posts,
     social media content, documents, observations, news articles
   - Open coding: read data line-by-line; assign short labels (codes) to each meaningful
     unit of data — a phrase, sentence, or paragraph
   - Do not force data into predetermined categories; let codes emerge from the data
   - Ask constant questions of the data: "What is happening here?" "What category does
     this represent?"
   - Generate as many codes as the data suggests; be inclusive at this stage

2. FOCUSED CODING — Consolidate open codes into higher-level categories:
   - Review all open codes; identify the most frequent and conceptually significant
   - Merge similar codes; collapse codes that represent the same concept
   - Focused codes become category candidates — more abstract than open codes
   - Apply the constant comparison method: compare each new piece of data to all
     existing categories; does it fit, or does it require a new category?
   - Memo writing: document your reasoning for each category consolidation decision

3. AXIAL CODING — Identify relationships between categories:
   - For each category: what are its conditions? (when/how does it occur?)
   - What are its consequences? (what results from it?)
   - What strategies do actors employ in relation to this category?
   - What contextual factors shape it?
   - Build a "paradigm model" for each core category:
     [conditions] → [phenomenon/category] → [context] → [strategies] → [consequences]

4. SELECTIVE CODING — Identify the core category:
   - The core category is the central concept that integrates all other categories
   - It must: appear frequently, be relevant to most other categories, have clear
     explanatory power for the main problem the data describes
   - Write a "storyline": a narrative that relates all categories to the core category
   - Verify that all categories fit the storyline; modify the theory where they don't

5. THEORETICAL SATURATION CHECK — Determine when the theory is complete:
   - Theoretical saturation: additional data no longer produces new categories or
     requires modifications to existing categories
   - Return to data collection if major categories remain poorly developed
   - Seek "negative cases" (data that seems to contradict the theory) — these refine
     the theory's scope conditions, not invalidate it
   - The theory is complete when it explains the main phenomena with density and variation

--- PRIORITY SELECTORS (Grounded Theory Analysis) ---

Ordered by analytical leverage (highest first):

1. core_concept             — the central integrating category; the theory in essence
2. category                 — higher-level groupings that become the theory's building blocks
3. axial_code               — category relationships; the theory's structural connectors
4. open_code                — raw conceptual labels from initial data reading
5. data_source              — the empirical material the theory is grounded in
6. selective_code           — the refined codes connecting all categories to the core
7. theoretical_saturation   — the endpoint criterion; signals theory completeness

--- KEY PIVOT PATTERNS ---

data_source (qualitative data mining):
  - Forum and community discussions: ddg_search "site:reddit.com [phenomenon]" for naturalistic data
  - Product reviews (G2, Trustpilot, App Store): reveal user conceptualizations of their experience
  - Twitter/X threads: google_news "[phenomenon] discussion" for real-time discourse
  - LinkedIn comments on industry articles: professional community's interpretive frames
  - Publicly available interview transcripts, oral histories, and testimonials

open_code (initial concept labeling):
  - Read each data unit as "What is this an instance of?"
  - Apply gerund-form labels (e.g., "managing expectations" rather than "expectations")
  - Use in-vivo codes where possible: the exact words used by participants
  - document_search for text corpora where systematic labeling can be applied

category (constant comparison):
  - Sort open codes by frequency — high-frequency codes signal important categories
  - Group codes asking: "What shared property do these codes have?"
  - ddg_search "[emerging category] qualitative research" for prior theoretical work
    in the same domain to check alignment or divergence

core_concept (integration):
  - The storyline test: write one paragraph integrating all categories around this concept
  - If the paragraph feels forced, the core concept may need revision
  - Check: does this core concept appear across multiple data sources?

--- COMPLETENESS CHECKLIST ---

Before closing a grounded theory analysis, confirm coverage in each area:

1. Data Coverage       — multiple data sources representing diverse perspectives collected
2. Open Coding         — all data units coded; in-vivo codes preserved
3. Focused Coding      — open codes consolidated into categories; constant comparison applied
4. Axial Coding        — category relationships mapped; paradigm models documented
5. Core Category       — single core category identified; storyline written
6. Theoretical Saturation — new data no longer modifies major categories; negative cases examined

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
