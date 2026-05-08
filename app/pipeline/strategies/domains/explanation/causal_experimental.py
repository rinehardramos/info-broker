"""Causal experimental analysis explanation sub-strategy module."""

CATEGORY = "explanation"
NAME = "causal_experimental"
DISPLAY_NAME = "Causal & Experimental Analysis"
DESCRIPTION = (
    "Establishes causal relationships through experimental and quasi-experimental "
    "methods. Applies counterfactual reasoning, confound identification, and "
    "appropriate causal inference techniques to distinguish causation from correlation."
)
SELECTORS = [
    "causal_claim",
    "treatment",
    "outcome",
    "confound",
    "study_design",
    "effect_size",
    "external_validity",
]

STRATEGY = """
=== CAUSAL & EXPERIMENTAL ANALYSIS STRATEGY ===

This strategy establishes causal relationships by applying experimental and
quasi-experimental methods with rigorous counterfactual reasoning. The central
question is always: "What would have happened if the treatment had not occurred?"
Correlation is never sufficient for causal claims — confounds must be identified
and addressed. Validate coverage using the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step causal analysis process:

1. CAUSAL CLAIM ARTICULATION — State the causal claim precisely:
   - What is the treatment (cause)? Define it operationally.
   - What is the outcome (effect)? Define the measurement.
   - What is the target population and context for this causal claim?
   - What is the temporal sequence? (Treatment must precede outcome)
   - What is the counterfactual? (What would have happened without the treatment?)
   Vague causal claims cannot be tested. Make the claim falsifiable.

2. CONFOUND IDENTIFICATION — Map all alternative explanations:
   - A confound is a variable that causes both the treatment and the outcome,
     creating a spurious association
   - List all plausible confounds for the causal relationship
   - Common confound categories: selection bias, common cause, reverse causation,
     measurement error, time trends, spillover effects
   - For each confound: assess how strongly it could bias the observed association
   - Evaluate whether any observed association could be entirely explained by confounds

3. STUDY DESIGN ASSESSMENT — Evaluate the causal evidence quality:
   - Hierarchy of evidence (strongest to weakest causal inference):
     1. Randomized Controlled Trial (RCT): gold standard; randomization breaks confounds
     2. Regression Discontinuity Design (RDD): exploits threshold-based assignment
     3. Difference-in-Differences (DiD): uses before/after + treatment/control comparison
     4. Instrumental Variables (IV): uses an exogenous instrument to isolate causal variation
     5. Matching / Propensity Score: attempts to construct comparable groups
     6. Observational study with statistical controls: weakest; confounds may remain
   - For each study found: identify the design, assess confound control, and rate
     the causal inference strength

4. EFFECT SIZE & PRECISION — Quantify the causal effect:
   - Point estimate: what is the estimated causal effect size?
   - Confidence interval: how precise is the estimate?
   - Statistical significance: is the effect reliably non-zero?
   - Practical significance: is the effect size meaningful in the real-world context?
   - Heterogeneous treatment effects: does the effect vary across subgroups?

5. EXTERNAL VALIDITY ASSESSMENT — Determine how broadly the causal claim applies:
   - Population validity: does the study population match the target population?
   - Ecological validity: does the study context match the real-world context?
   - Temporal validity: does the effect persist over time?
   - Replication: has the causal claim been replicated in other contexts?
   - Mechanism: is there a plausible biological, psychological, or social mechanism
     that explains WHY the treatment causes the outcome?

--- PRIORITY SELECTORS (Causal & Experimental Analysis) ---

Ordered by analytical leverage (highest first):

1. causal_claim        — the precise causal assertion being evaluated
2. confound            — alternative explanations; must be ruled out for causal claims
3. study_design        — the method determining the strength of causal inference
4. treatment           — the intervention or exposure being studied
5. outcome             — the measured effect; defines what causation is being claimed for
6. effect_size         — the magnitude of the causal effect; determines practical relevance
7. external_validity   — scope of applicability; determines where the claim holds

--- KEY PIVOT PATTERNS ---

causal_claim + study_design:
  - Google Scholar: "[treatment] [outcome] randomized controlled trial" for RCT evidence
  - PubMed for medical and health causal claims
  - NBER Working Papers (nber.org/papers) for economic causal studies
  - ddg_search "[treatment] [outcome] causal evidence" OR "[treatment] causes [outcome]"

confound identification:
  - Directed Acyclic Graph (DAG) literature: ddg_search "[domain] DAG confounders"
  - Google Scholar "[treatment] [outcome] confounding factors"
  - Systematic review papers often include confound discussions in methods sections
  - Epidemiology textbooks for common confound patterns by study type

study_design (specific methods):
  - For RCT evidence: ClinicalTrials.gov (medical), AEA RCT Registry (economics)
  - For quasi-experimental: Google Scholar "regression discontinuity [domain]" or
    "difference-in-differences [domain]" or "instrumental variable [domain]"
  - Cochrane Reviews for systematic assessments of RCT evidence quality
  - Campbell Collaboration for social program causal evaluations

effect_size:
  - Systematic reviews and meta-analyses for pooled effect estimates
  - Cohen's conventions: d=0.2 small, 0.5 medium, 0.8 large (behavioral outcomes)
  - Number needed to treat (NNT) for clinical outcomes
  - Percentage change and relative risk for binary outcomes

external_validity:
  - Replication registries: ddg_search "[study] replication" for replication attempts
  - Heterogeneous treatment effect literature: does the effect vary by context?
  - ddg_search "[causal claim] meta-analysis" for cross-context synthesis

--- COMPLETENESS CHECKLIST ---

Before closing a causal analysis task, confirm coverage in each area:

1. Causal Claim        — treatment, outcome, and counterfactual stated precisely
2. Confound Map        — all plausible confounds identified and assessed
3. Evidence Quality    — study designs evaluated using causal inference hierarchy
4. Effect Size         — point estimate, confidence interval, and practical significance assessed
5. Replication Check   — existence of replications or meta-analyses documented
6. External Validity   — population, context, and temporal generalizability assessed

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
