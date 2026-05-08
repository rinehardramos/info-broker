"""Decision analysis synthesis sub-strategy module."""

CATEGORY = "synthesis"
NAME = "decision_analysis"
DISPLAY_NAME = "Decision Analysis"
DESCRIPTION = (
    "Structured decision-making under uncertainty using a multi-criteria decision "
    "matrix with weighted scoring. All options are enumerated before evaluation. "
    "Produces a clear recommendation with sensitivity analysis."
)
SELECTORS = [
    "decision_question",
    "option",
    "criterion",
    "weight",
    "evidence",
    "constraint",
    "sensitivity",
]

STRATEGY = """
=== DECISION ANALYSIS STRATEGY ===

This strategy guides structured decision-making under uncertainty using a
multi-criteria decision matrix with weighted scoring. All options must be enumerated
before evaluation begins. Evidence must be mapped per criterion per option.
A clear recommendation with stated reasoning is required. Validate coverage using
the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step decision analysis process:

1. OPTION ENUMERATION — Identify all candidate options before evaluation:
   - List every viable option, including the status quo (do nothing) option
   - Apply a brief feasibility filter to eliminate options that violate hard constraints
     (budget, timeline, regulatory, technical)
   - Document why any option was eliminated before the scoring phase
   - Aim for completeness: missing a viable option produces a biased decision
   Do not pre-select a "preferred" option before completing enumeration.

2. CRITERIA DEFINITION — Define the evaluation criteria that matter for this decision:
   - For each criterion: name it, define what "good" and "bad" performance looks like,
     and specify how it will be measured (quantitative metric or qualitative rating scale)
   - Ensure criteria are:
     * Relevant: directly related to the decision's goals
     * Mutually exclusive: not double-counting the same underlying factor
     * Collectively exhaustive: covering all material aspects of the decision
   - Include both positive criteria (maximize) and risk criteria (minimize)
   - Typical criterion categories: cost, quality/performance, risk, time, scalability,
     strategic alignment, reversibility, compliance

3. WEIGHTS ASSIGNMENT — Assign relative importance weights to each criterion:
   - Use structured weighting methods: direct ratio assignment, AHP (Analytic Hierarchy
     Process) pairwise comparisons, or swing weighting
   - Weights must sum to 1.0 (or 100%)
   - Document the rationale for each weight — weight assignments are decision assumptions
     and should be transparent and challengeable
   - Run a sensitivity analysis: identify which options change rank when weights shift
     by ±20%. Flag decisions that are sensitive to weight assumptions.

4. EVIDENCE MAPPING PER OPTION — For each option × criterion cell, gather evidence:
   - Quantitative evidence: cost estimates, performance benchmarks, timeline data
   - Qualitative evidence: expert assessments, case studies, analogous decisions
   - Uncertainty ranges: where evidence is incomplete, document the uncertainty range
   - Score each option on each criterion (e.g., 1-5 scale) based on the evidence
   - Calculate weighted score: sum of (criterion weight × option score) across all criteria
   - Document evidence quality (Strong / Moderate / Weak / Assumed) per cell

5. RECOMMENDATION — Synthesize the analysis into a decision recommendation:
   - Present the decision matrix with weighted scores
   - Identify the top-scoring option(s)
   - State the recommendation and its primary rationale
   - Address the key trade-offs explicitly: what does the recommended option sacrifice
     compared to alternatives?
   - Flag conditions under which the recommendation would change (key sensitivities)
   - If no option dominates on weighted score, use dominance analysis: eliminate any
     option that is outperformed on all criteria by another option

--- PRIORITY SELECTORS (Decision Analysis) ---

Ordered by research leverage (highest priority first):

1. decision_question  — the specific decision to be made, with stated objective
2. option             — each viable alternative under consideration
3. criterion          — the evaluation dimension with measurement definition
4. weight             — the relative importance of each criterion
5. evidence           — data and analysis supporting option scoring on each criterion
6. constraint         — hard requirements that bound the feasible option set
7. sensitivity        — weight or assumption changes that alter the recommendation

--- KEY PIVOT PATTERNS ---

option:
  - web_search "[decision domain] options" OR "[decision domain] alternatives" for
    option discovery in unfamiliar domains
  - Industry benchmarks and case studies for options used in comparable decisions
  - Expert interviews and stakeholder input for options not yet in consideration
  - Ensure status quo (current state) is always included as an option

criterion:
  - Regulatory and compliance requirements as mandatory criteria (binary pass/fail)
  - Financial: TCO (Total Cost of Ownership) including indirect and switching costs
  - Strategic: alignment with organizational goals and long-term direction
  - Risk: probability and severity of adverse outcomes per option
  - Time: implementation timeline and speed to value
  - Reversibility: cost and feasibility of reversing the decision if it fails

weight:
  - AHP pairwise comparison (Saaty 1980) for structured weight elicitation
  - Swing weighting: "which criterion matters most if it swings from worst to best?"
  - Stakeholder weight elicitation: collect weights from multiple decision-makers
    and analyze for consensus or divergence

evidence (per cell):
  - RFP/RFQ responses and vendor proposals for procurement decisions
  - Financial modeling (NPV, IRR, payback period) for investment decisions
  - Technical benchmarks and pilot results for technology selection decisions
  - Reference checks and case studies for vendor/partner selection

sensitivity:
  - One-at-a-time weight sensitivity: vary each weight ±20%, observe rank changes
  - Scenario-based sensitivity: apply different evidence assumptions (optimistic/pessimistic)
  - Threshold analysis: find the weight value at which the top option changes

--- INVESTIGATION PRINCIPLES ---

OPTION COMPLETENESS FIRST
  Do not begin scoring without a complete option list. A brilliant scoring methodology
  applied to an incomplete option set is still a flawed analysis. The best option
  might not be in the matrix.

CRITERIA INDEPENDENCE
  Double-counting correlated criteria inflates their combined weight. Cost and ROI
  are correlated — include one, not both. Test for correlations between criteria
  before finalizing the framework.

EVIDENCE MAPPING DISCIPLINE
  Every cell in the decision matrix requires evidence. Scoring without evidence is
  speculation, not analysis. Document evidence quality per cell — a matrix built on
  weak evidence produces a weak recommendation.

WEIGHTS ARE ASSUMPTIONS
  Weights encode the decision-maker's values and priorities. Document them explicitly
  and subject them to sensitivity analysis. A recommendation that only holds under
  one set of weights is fragile.

CLEAR RECOMMENDATION REQUIRED
  Analytical frameworks exist to support decisions, not replace them. The output must
  include a clear recommendation, the rationale, the key trade-offs accepted, and
  the conditions under which the recommendation would change.

--- COMPLETENESS CHECKLIST ---

Before closing a decision analysis task, confirm coverage in each area:

1. Options Enumerated   — all viable options identified including status quo;
                          eliminated options documented with reasons
2. Criteria Defined     — each criterion named, defined, and measurement method specified;
                          MECE check applied; constraint criteria separated
3. Evidence Per Option  — each option×criterion cell has documented evidence;
                          evidence quality rated; uncertainty ranges noted where applicable
4. Weights Assigned     — weights documented with rationale; sum to 1.0;
                          sensitivity analysis run; high-sensitivity dimensions flagged
5. Recommendation       — top option identified with weighted score; rationale stated;
                          key trade-offs acknowledged; conditions for re-evaluation defined

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
