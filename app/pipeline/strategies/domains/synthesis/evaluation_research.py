"""Evaluation research synthesis sub-strategy module."""

CATEGORY = "synthesis"
NAME = "evaluation_research"
DISPLAY_NAME = "Evaluation Research"
DESCRIPTION = (
    "Assesses the effectiveness, efficiency, and impact of programs, policies, or "
    "interventions. Applies theory of change logic, outcome measurement, and "
    "comparison against counterfactuals to produce evidence-based evaluative judgments."
)
SELECTORS = [
    "program_name",
    "theory_of_change",
    "outcome_indicator",
    "comparison_group",
    "evaluation_question",
    "data_source",
    "evaluation_type",
]

STRATEGY = """
=== EVALUATION RESEARCH STRATEGY ===

This strategy guides systematic evaluation of programs, policies, and interventions.
It applies theory of change logic to articulate the intended causal pathway, selects
appropriate evaluation designs, and synthesizes evidence to answer specific evaluation
questions. Judgments are based on evidence, not opinion. Validate coverage using the
completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step evaluation research process:

1. EVALUATION FRAMING — Define what is being evaluated and why:
   - What program, policy, or intervention is being evaluated?
   - What are the evaluation questions? (effectiveness, efficiency, relevance, impact,
     sustainability — select the applicable evaluation criteria)
   - Who are the primary audiences for the evaluation findings?
   - What is the purpose? (accountability, learning, program improvement, scaling decision)
   - What is the scope? (geographic, temporal, population, level of analysis)

2. THEORY OF CHANGE (ToC) MAPPING — Articulate the intended causal pathway:
   - Inputs: resources invested (funding, staff, materials, time)
   - Activities: what the program does (services delivered, actions taken)
   - Outputs: direct products of activities (number trained, events held, products distributed)
   - Outcomes: changes in behavior, knowledge, or condition for target population
   - Impact: longer-term changes attributable to the program; beyond immediate outcomes
   - Assumptions: conditions required for each step of the ToC to hold
   - External factors: contextual conditions that affect the pathway
   The ToC is the evaluation's hypothesis — it specifies what to measure.

3. EVIDENCE COLLECTION — Gather data to assess ToC components:
   - Program documentation: reports, evaluations, monitoring data, theory articulations
   - Outcome data: administrative records, surveys, assessments, registries
   - Comparison data: pre-post, treatment-control, or matched comparison groups
   - Qualitative evidence: interviews, case studies, focus group reports
   - Context data: external factors that may have contributed to observed outcomes
   For each data source: assess reliability, validity, and potential bias.

4. CAUSAL ATTRIBUTION — Determine how much of the observed outcome is due to the program:
   - Counterfactual: what would have happened without the program?
   - Contribution analysis: even without perfect attribution, map how each ToC link
     is supported or contradicted by evidence
   - Plausible rival hypotheses: list alternative explanations for observed outcomes
   - Rate attribution confidence: strong / moderate / weak based on evidence quality

5. EVALUATIVE SYNTHESIS — Render evidence-based judgments on the evaluation questions:
   - For each evaluation question: what does the evidence say?
   - Apply the OECD-DAC evaluation criteria as applicable:
     Relevance, Coherence, Effectiveness, Efficiency, Impact, Sustainability
   - Distinguish between questions with strong evidence and those with gaps
   - Produce recommendations grounded in evidence; distinguish evidence-based from opinion

--- PRIORITY SELECTORS (Evaluation Research) ---

Ordered by evaluation leverage (highest first):

1. evaluation_question   — the specific question the evaluation must answer
2. theory_of_change      — the causal pathway; specifies what to measure
3. outcome_indicator     — how outcomes are measured; determines data needs
4. comparison_group      — counterfactual reference; required for attribution claims
5. program_name          — anchor for documentation, report, and data search
6. data_source           — evidence base; determines what claims can be supported
7. evaluation_type       — process, outcome, impact, or formative; shapes design

--- KEY PIVOT PATTERNS ---

program_name + evaluation_type:
  - ddg_search "[program name] evaluation report" OR "[program name] impact assessment"
  - International Development Evaluation Association (IDEAS) and 3ie databases
    for development program evaluations
  - Government accountability office (GAO, NAO, similar) reports for public program evaluations
  - Academic databases (Google Scholar) for peer-reviewed program evaluations
  - USAID Development Experience Clearinghouse (dec.usaid.gov) for international development evals

theory_of_change:
  - Existing ToC documentation: program's own theory articulations, logic models
  - Intervention design documents for intended mechanism articulation
  - ddg_search "[program type] theory of change" for sector-specific ToC models
  - 3ie Evidence Map for systematic evidence on ToC link validity

outcome_indicator:
  - Established indicator frameworks: IRIS+ (GIIN), SDG indicator list, WHO health indicators
  - Sector-specific frameworks: education (PISA, EGRA), health (DHS), nutrition (MUAC)
  - ddg_search "[sector] outcome indicators evaluation" for validated measurement approaches

comparison_group:
  - Randomized comparison: clinical or program RCT reports for gold-standard attribution
  - Administrative comparison: population registries, national surveys for comparison data
  - Propensity score matching: ddg_search "[program] comparison group methodology"
  - Time-series baselines for pre-post comparisons where control groups are unavailable

--- COMPLETENESS CHECKLIST ---

Before closing an evaluation research task, confirm coverage in each area:

1. Evaluation Questions  — specific evaluation questions stated; OECD-DAC criteria applied
2. Theory of Change      — ToC mapped with inputs, activities, outputs, outcomes, and assumptions
3. Evidence Collection   — data sources identified; reliability and validity assessed
4. Attribution Analysis  — counterfactual addressed; rival hypotheses considered
5. Evidence Synthesis    — evaluative judgments rendered per evaluation question
6. Recommendations       — evidence-grounded recommendations with clear evidence basis

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
