"""Morphological analysis generation sub-strategy module."""

CATEGORY = "generation"
NAME = "morphological_analysis"
DISPLAY_NAME = "Morphological Analysis"
DESCRIPTION = (
    "Systematically explores the full solution space by decomposing a problem into "
    "independent dimensions and mapping all feasible value combinations. Produces "
    "a morphological chart with evaluated concept combinations."
)
SELECTORS = [
    "problem_statement",
    "design_dimension",
    "parameter_value",
    "constraint",
    "evaluation_criterion",
    "concept_combination",
    "feasibility_flag",
]

STRATEGY = """
=== MORPHOLOGICAL ANALYSIS STRATEGY ===

This strategy applies Fritz Zwicky's morphological analysis method to systematically
explore the full solution space for a complex problem. By decomposing the problem
into independent dimensions and mapping all feasible value combinations, it prevents
premature convergence on familiar solutions. The output is a morphological chart with
evaluated concept combinations. Validate coverage using the completeness checklist
before concluding.

--- EXECUTION MODEL ---

A 5-step morphological analysis process:

1. PROBLEM DECOMPOSITION — Break the problem into independent design dimensions:
   - Identify the key parameters that define a solution (not solution elements)
   - Each dimension must be truly independent — varying one should not force
     a change in another
   - Typical dimensions: energy source, material type, actuation mechanism,
     control method, form factor, manufacturing process, user interface mode
   - Aim for 4-8 dimensions; fewer loses coverage, more creates combinatorial explosion
   - Document the rationale for each dimension choice

2. VALUE ENUMERATION — For each dimension, list all feasible parameter values:
   - Include unconventional and emerging options, not just conventional ones
   - Avoid restricting values by current technology — include aspirational options
   - Each dimension typically has 3-8 values
   - Apply the "SCAMPER" lens to generate additional values:
     Substitute, Combine, Adapt, Modify/Magnify, Put to other uses, Eliminate, Reverse

3. MORPHOLOGICAL CHART CONSTRUCTION — Build the matrix:
   - Rows = design dimensions
   - Columns = parameter values for each dimension
   - This creates a full solution space: product of all value counts
   - A 5-dimension chart with 4 values each = 4^5 = 1,024 possible combinations
   - The chart makes the unexplored solution space visible

4. CONCEPT COMBINATION SELECTION — Select promising paths through the chart:
   - Random traversal: select one value per dimension randomly to break cognitive bias
   - Constraint-guided traversal: eliminate infeasible combinations
     (incompatible pairs, regulatory exclusions, physical impossibilities)
   - Criteria-guided traversal: select combinations that maximize weighted criteria
   - Generate 5-10 distinct concept combinations for evaluation
   - Label each combination with a concept name for reference

5. CONCEPT EVALUATION — Assess each selected combination against criteria:
   - Feasibility: is the combination physically/technically realizable?
   - Desirability: does it meet user needs?
   - Viability: can it be delivered within business constraints?
   - Novelty: has this combination been explored before?
   - Rank combinations; identify the top 3 for prototype development

--- PRIORITY SELECTORS (Morphological Analysis) ---

Ordered by process leverage (highest first):

1. problem_statement    — defines what the morphology is solving; must be precise
2. design_dimension     — independent axes of the solution space; the chart's skeleton
3. parameter_value      — the options along each dimension; defines solution breadth
4. constraint           — rules out infeasible combinations; reduces search space
5. evaluation_criterion — weighted criteria for concept ranking
6. concept_combination  — a selected path through the chart; an emergent solution concept
7. feasibility_flag     — incompatibility markers between specific parameter value pairs

--- KEY PIVOT PATTERNS ---

problem_statement:
  - Frame as: "How might we design a [system/product/process] that [achieves function]
    under [constraints]?"
  - Ensure the statement is technology-neutral (does not presuppose a solution approach)
  - ddg_search "[problem domain] design parameters" for established dimension frameworks

design_dimension (secondary research):
  - Google Scholar "[product category] design parameters" for academic design frameworks
  - Patent classification tree for the technology area (IPC subclasses = dimension proxies)
  - Engineering textbooks and handbooks for established design dimension frameworks
  - ddg_search "[product type] design choices" for practitioner decompositions

parameter_value (emerging options):
  - ddg_search "[dimension] emerging technologies [year]" for leading-edge options
  - Patent databases: recent filings in the relevant IPC class for novel mechanisms
  - Google Scholar "novel [dimension] approach" for research-stage alternatives
  - Startup databases (Crunchbase) for companies with non-conventional approaches

constraint:
  - Regulatory databases: ddg_search "[product category] regulations [jurisdiction]"
  - Physical constraints: materials handbooks for property limits
  - Cost constraints: unit economics analysis for manufacturability boundaries

evaluation_criterion:
  - Customer review mining for what users value most
  - Pugh matrix or weighted decision matrix for systematic scoring
  - KPIs from industry benchmarks for quantitative criteria definition

--- COMPLETENESS CHECKLIST ---

Before closing a morphological analysis task, confirm coverage in each area:

1. Decomposition        — 4-8 independent dimensions defined; rationale documented
2. Value Enumeration    — 3-8 values per dimension; unconventional options included
3. Morphological Chart  — complete chart constructed; solution space size noted
4. Infeasibility Pruning — incompatible combinations identified and excluded
5. Concept Combinations — at least 5 distinct combinations selected and named
6. Concept Evaluation   — all selected combinations evaluated against criteria; top 3 ranked

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
