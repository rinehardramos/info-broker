"""Biomimicry generation sub-strategy module."""

CATEGORY = "generation"
NAME = "biomimicry"
DISPLAY_NAME = "Biomimicry Research"
DESCRIPTION = (
    "Finds biological strategies that have evolved to solve the same functional "
    "challenge as the engineering problem at hand. Translates natural principles "
    "into actionable design concepts via function-to-biology mapping."
)
SELECTORS = [
    "design_challenge",
    "biological_function",
    "organism",
    "natural_strategy",
    "design_principle",
    "performance_metric",
    "habitat",
]

STRATEGY = """
=== BIOMIMICRY RESEARCH STRATEGY ===

This strategy identifies biological strategies from nature that can inspire solutions
to engineering, design, or organizational challenges. It moves from a functional
challenge to nature's evolved solutions, then translates biological principles into
design concepts. The core method is function-to-biology mapping: define what the
solution must DO, then find organisms that do it. Validate coverage using the
completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step biomimicry research process:

1. CHALLENGE ABSTRACTION — Translate the design challenge into functional terms:
   - Avoid solution-specific language; describe the function, not the mechanism
   - Examples: "resist compression under cyclic load" not "design a stronger column"
   - "transfer heat efficiently across a gradient" not "build a better heat exchanger"
   - "filter particles from a fluid stream" not "design a water purifier"
   - Identify the performance metrics that matter (strength-to-weight, efficiency %)
   - List constraints: material properties, scale, energy budget, operating environment

2. BIOLOGICAL FUNCTION SEARCH — Find organisms that have evolved to perform this function:
   - AskNature (asknature.org): Biomimicry Institute's curated function-to-biology database
   - Web of Science / PubMed: search "[function verb] [organism class]" in biology literature
   - Encyclopedia of Life (eol.org) for species-level biological function descriptions
   - ddg_search "how does [organism] [function verb]" for layperson and popular science coverage
   - Prioritize organisms that perform the function under similar constraints to the design
   - Look for extreme cases: organisms that perform the function at record levels

3. STRATEGY EXTRACTION — Document the biological mechanism in detail:
   - What is the physical, chemical, or behavioral mechanism?
   - At what scale does it operate (nano, micro, macro)?
   - What materials or structures are involved?
   - What is the performance level achieved?
   - Are there secondary effects or tradeoffs?
   - How does the strategy vary across species (convergent evolution reveals robust principles)?

4. PRINCIPLE ABSTRACTION — Distill the biological mechanism into a design principle:
   - Strip away the biology-specific details; retain the underlying physical principle
   - State the principle at a level of abstraction that enables translation
   - Example: Lotus leaf → "hierarchical surface roughness at micro and nano scales
     creates superhydrophobicity via minimized contact area and air entrapment"
   - Convergent evolution test: if multiple unrelated organisms use the same strategy,
     the principle is likely robust and general

5. DESIGN CONCEPT TRANSLATION — Map the biological principle to the engineering domain:
   - Identify material, structural, or process analogs in the design domain
   - Propose at least two distinct design concepts inspired by the principle
   - For each concept: describe the mechanism, expected benefit, and feasibility
   - Flag where biological materials or scales cannot be replicated and propose workarounds
   - Identify existing biomimetic applications as proof-of-concept references

--- PRIORITY SELECTORS (Biomimicry Research) ---

Ordered by research leverage (highest first):

1. design_challenge    — the problem to solve; drives all biological function searching
2. biological_function — the functional analog in biological terms; key search term
3. natural_strategy    — the specific biological mechanism discovered
4. design_principle    — abstracted principle enabling engineering translation
5. organism            — the biological model; enables deep-dive on the mechanism
6. habitat             — environmental constraints; surfaces organisms adapted to similar conditions
7. performance_metric  — quantitative target; enables selection of best biological analog

--- KEY PIVOT PATTERNS ---

design_challenge (function-to-biology):
  - AskNature (asknature.org): browse by function (Attach, Filter, Move, Protect, Sense, etc.)
  - ddg_search "biomimicry [function] examples" for compiled lists
  - Google Scholar: "[function] biological analogy" OR "[function] inspired design"
  - web_search_fetch Biomimicry Institute and Biomimetics journal articles

biological_function + organism:
  - PubMed: "[organism] [function] mechanism" for detailed biological studies
  - Encyclopedia of Life (eol.org) for species ecology and functional biology
  - ddg_search "[organism] [function] how does it work" for accessible explanations
  - Wikipedia species articles: look for "physiology," "adaptations," and "behavior" sections

natural_strategy (convergent evolution check):
  - Google Scholar: "[principle] convergent evolution" to test generality
  - ddg_search "[function] evolved [number] times independently" for robustness signal
  - Compare mechanism in vertebrates vs. invertebrates vs. plants vs. microbes

design_principle (translation):
  - Google Scholar: "[principle] engineering application" OR "[principle] materials science"
  - Patent databases (Google Patents): "[biological structure] inspired" for prior applications
  - Nature Materials and Bioinspiration & Biomimetics journals for translated designs
  - ddg_search "[organism]-inspired [design domain]" for existing commercialized examples

--- COMPLETENESS CHECKLIST ---

Before closing a biomimicry research task, confirm coverage in each area:

1. Function Abstraction  — design challenge stated as a pure function; constraints listed
2. Biological Models     — at least 3 organisms performing the function identified
3. Mechanism Detail      — biological mechanism documented at mechanistic level for each model
4. Principle Abstraction — underlying design principle extracted; stated without biology jargon
5. Convergence Check     — checked whether multiple unrelated organisms use the same strategy
6. Design Concepts       — at least 2 design concepts proposed with feasibility notes

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
