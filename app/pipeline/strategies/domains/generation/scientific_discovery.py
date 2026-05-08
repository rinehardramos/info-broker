"""Scientific discovery generation sub-strategy module."""

CATEGORY = "generation"
NAME = "scientific_discovery"
DISPLAY_NAME = "Scientific Discovery"
DESCRIPTION = (
    "Identifies knowledge gaps and formulates falsifiable hypotheses grounded in "
    "exhaustive literature coverage. Requires experimental design before research "
    "concludes. Falsifiability is a hard requirement."
)
SELECTORS = [
    "research_question",
    "hypothesis",
    "gap",
    "prior_work",
    "methodology",
    "researcher_lab",
    "dataset",
]

STRATEGY = """
=== SCIENTIFIC DISCOVERY STRATEGY ===

This strategy guides research toward identifying knowledge gaps and formulating
testable hypotheses grounded in thorough literature coverage. Falsifiability is
a hard requirement. Experimental design must be proposed before research concludes.
Validate coverage using the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step hypothesis-driven discovery process:

1. LITERATURE COVERAGE — Conduct an exhaustive search of primary literature (peer-reviewed
   journals, preprint servers, conference proceedings) and secondary sources (reviews,
   meta-analyses, textbooks). Map the current state of knowledge: what is established,
   what is contested, and what is unknown. Document search strategy (databases, keywords,
   date ranges, inclusion/exclusion criteria).

2. GAP IDENTIFICATION — Analyze literature coverage to identify knowledge gaps:
   - Unexplored combinations of variables or conditions
   - Contradictory findings that remain unresolved
   - Theoretical predictions without empirical validation
   - Methodological limitations that prevent definitive conclusions
   Rank gaps by scientific significance and tractability.

3. HYPOTHESIS FORMULATION — For each top-ranked gap, formulate a falsifiable hypothesis:
   - State the independent and dependent variables explicitly
   - Define the predicted direction and magnitude of effect
   - Specify the boundary conditions under which the hypothesis holds
   - Apply the falsifiability check: "What result would disprove this hypothesis?"
   A hypothesis that cannot be disproven is not scientific — revise or discard it.

4. EXPERIMENTAL DESIGN SUGGESTION — For each hypothesis, outline an experimental design:
   - Study design (RCT, observational, computational, in vitro, in vivo, etc.)
   - Sample/dataset requirements (size, selection criteria, controls)
   - Key measurements and instrumentation
   - Statistical analysis plan (test, power, significance threshold)
   - Controls for confounders and known biases
   - Ethical and safety considerations

5. PRIOR ART SEARCH — Before finalizing, verify the hypothesis has not already been tested:
   - Search for studies with overlapping independent/dependent variables
   - Check registered trials (ClinicalTrials.gov, OSF) for ongoing work
   - Review grey literature and conference abstracts for unpublished data
   - Document all near-miss findings and explain how the proposed hypothesis differs

--- PRIORITY SELECTORS (Scientific Discovery) ---

Ordered by research leverage (highest priority first):

1. research_question  — the core scientific question driving the investigation
2. hypothesis         — the falsifiable prediction to be tested
3. gap                — the specific knowledge gap the hypothesis addresses
4. prior_work         — directly relevant studies, meta-analyses, and reviews
5. methodology        — experimental or analytical approach under consideration
6. researcher_lab     — groups actively working on the problem area
7. dataset            — empirical data sources relevant to testing the hypothesis

--- KEY PIVOT PATTERNS ---

research_question:
  - web_search "[domain] open questions" OR "unsolved problems in [field]"
  - review article "future directions" and "limitations" sections
  - Nature, Science, Cell "Perspectives" and "Reviews" for field-level gap maps
  - preprint servers (arXiv, bioRxiv, medRxiv) for cutting-edge unsettled questions

gap:
  - systematic review "GRADE" low-certainty evidence flags → tractable gaps
  - contradictory findings between studies → replication and moderator hypotheses
  - "null results" repositories and registered reports for under-explored areas

hypothesis:
  - falsifiability check: state the disconfirmation condition explicitly
  - operationalization: map abstract constructs to measurable variables
  - effect size estimation from analogous studies to power the design

prior_work:
  - citation graph traversal (Semantic Scholar, Connected Papers, OpenCitations)
  - systematic search: PubMed, Web of Science, Scopus, Google Scholar
  - preprint deduplication: match preprints to published versions

methodology:
  - search "[method] validation studies" for known limitations and failure modes
  - instrument comparison papers for measurement validity and reliability
  - replication studies for robustness of the method in the target domain

--- INVESTIGATION PRINCIPLES ---

EXHAUSTIVE LITERATURE COVERAGE
  Do not formulate hypotheses before the literature is mapped. Proposing a hypothesis
  that has already been tested wastes resources and weakens the scientific contribution.

HYPOTHESIS FORMULATION
  Every hypothesis must be specific, measurable, and falsifiable. Vague conjectures
  ("X may affect Y") are not hypotheses — they are research questions. Operationalize
  before proceeding.

FALSIFIABILITY CHECK
  Apply Popper's criterion: if no conceivable observation could disprove the hypothesis,
  it is not scientific. Revise the hypothesis until a clear disconfirmation condition
  can be stated.

EXPERIMENTAL DESIGN RIGOR
  Propose designs that control for confounders, have adequate power, and use
  appropriate statistical methods. Under-powered studies produce unreliable results
  regardless of how well the hypothesis is framed.

--- COMPLETENESS CHECKLIST ---

Before closing a scientific discovery research task, confirm coverage in each area:

1. Literature Coverage     — exhaustive search conducted; databases, keywords, and
                             date range documented; major reviews and meta-analyses included
2. Gap Identification      — at least 3 knowledge gaps identified; ranked by significance
3. Hypothesis Formulation  — at least 1 falsifiable hypothesis per top gap; variables
                             and boundary conditions specified
4. Experimental Design     — study design, sample requirements, and analysis plan outlined
                             for each primary hypothesis
5. Prior Art               — hypothesis uniqueness verified; overlapping studies documented
                             and differentiated

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
