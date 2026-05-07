"""Generation research strategy module."""

ENTITY_TYPE = "generation"

STRATEGY = """
=== GENERATION RESEARCH STRATEGY ===

This strategy defines how to conduct a thorough research process oriented toward
generating novel solutions, ideas, or approaches for a given problem. Follow the
execution model, honor the priority selector order, and validate coverage using
the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 6-step problem-to-solution process:

1. PROBLEM — Clearly define and document the problem statement. Decompose it into
   sub-problems. Identify constraints, requirements, and success criteria before
   any search begins.

2. SOTA SCAN — Conduct an exhaustive State-of-the-Art scan. Search academic
   literature, patents, industry reports, and open-source repositories for existing
   solutions. Document what has already been tried and what the current best
   approaches are.

3. GAP IDENTIFICATION — Analyze the SOTA results to identify gaps: unsolved
   sub-problems, underperforming solutions, unaddressed constraints, or limitations
   explicitly acknowledged in prior work. Each gap is a candidate innovation target.

4. CROSS-DOMAIN SEARCH — For each gap, search adjacent and unrelated domains for
   analogous problems that have been solved. Apply TRIZ principles (contradiction
   matrix, inventive principles) to map cross-domain solutions back to the target
   problem.

5. CANDIDATE SOLUTIONS — Generate a portfolio of candidate solutions by combining
   SOTA insights with cross-domain transfers and first-principles reasoning.
   Document each candidate with its mechanism, expected performance, and
   inheritance from prior work.

6. FEASIBILITY CHECK — For each candidate solution, assess technical feasibility,
   resource requirements, timeline, risk factors, and regulatory/ethical
   constraints. Rank candidates by expected impact vs. effort.

--- PRIORITY SELECTORS (Generation) ---

Ordered by research leverage (highest priority first):

1. problem_statement  — primary anchor; must be precise before any search begins
2. concept            — the core mechanism or idea being explored
3. technique          — specific method, algorithm, or process under investigation
4. prior_art          — existing patents, papers, or implementations to build upon
5. researcher_lab     — groups actively working in the problem space
6. constraint         — hard limits (cost, time, regulation) that bound the solution space
7. gap                — explicitly identified insufficiency in current approaches

--- KEY PIVOT PATTERNS ---

problem_statement:
  - web_search for surveys and review papers (keyword: "survey" OR "review" + domain)
  - patent database search (USPTO, EPO, Google Patents) for existing claims
  - web_search for benchmark datasets and challenge competitions
  - identify top-cited papers and trace their citation graphs

concept:
  - search for known limitations and failure modes of the concept
  - search for alternatives ("alternatives to X", "X vs Y comparison")
  - find open-source implementations to assess practical constraints
  - review_papers → extract experimental results and reported gaps

technique:
  - web_search for recent improvements ("improved X", "X 2.0", "beyond X")
  - search adjacent technique variations (ensemble, hybrid, multi-stage)
  - find ablation studies that reveal which components matter most

prior_art:
  - citation graph traversal (forward + backward citations)
  - identify authors → search their subsequent publications
  - find implementation repositories linked from papers
  - check conference proceedings for follow-up work

researcher_lab:
  - web_search lab homepage for current projects and preprints
  - follow author profiles on arXiv, Google Scholar, Semantic Scholar
  - identify collaborators who may work on complementary sub-problems

constraint:
  - search for "constrained X" or "efficient X" or "lightweight X"
  - look for hardware-aware or resource-limited variants of existing solutions
  - regulatory databases for compliance requirements in target domain

gap:
  - apply TRIZ inventive principles (40 principles, contradiction matrix)
  - cross-domain search: find analogous problem in biology, physics, economics
  - web_search "unsolved problems in X" or "open challenges in X"
  - identify the gap as a new sub-problem and restart the SOTA scan for it

--- INVESTIGATION PRINCIPLES ---

EXHAUSTIVE STATE-OF-ART SCAN
  Do not begin ideation until SOTA is documented. Unknown prior art leads to
  reinventing solved problems and missing key insights that bound the solution space.

CROSS-DOMAIN TRANSFER
  The best solutions often come from outside the target domain. Invest at least
  one search round in non-obvious analogous fields before generating candidates.
  Use TRIZ as a structured transfer mechanism.

GAP-DRIVEN INNOVATION
  Novelty lives in the gaps. Do not generate solutions that merely replicate
  existing work. Each candidate solution must trace to an identified gap or
  unmet constraint in the SOTA.

FEASIBILITY FIRST
  A brilliant solution that cannot be implemented is noise. Apply feasibility
  filters early to avoid investing in infeasible candidates. Flag speculative
  candidates clearly.

NOVELTY VERIFICATION
  Before finalizing a candidate, confirm it is not already described in prior
  art. A final patent and literature check is required for every top-ranked
  candidate.

--- COMPLETENESS CHECKLIST ---

Before closing a generation research task, confirm coverage in each area:

1. State of Art          — SOTA documented; top approaches and their performance recorded
2. Gap Identification    — at least 3 distinct gaps identified and ranked by importance
3. Solution Space        — at least 3 candidate solutions generated per top-ranked gap
   Exploration
4. Feasibility Analysis  — each top candidate assessed on effort, risk, and resource needs
5. Novelty Check         — top candidates verified against patents and literature
6. Competitive           — key players, labs, and products in the space identified
   Landscape

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
