"""Systems thinking explanation sub-strategy module."""

CATEGORY = "explanation"
NAME = "systems_thinking"
DISPLAY_NAME = "Systems Thinking"
DESCRIPTION = (
    "Analyzes complex problems by mapping system structure: stocks, flows, feedback "
    "loops, and time delays. Identifies leverage points and unintended consequences "
    "of interventions in complex adaptive systems."
)
SELECTORS = [
    "system_boundary",
    "stock",
    "flow",
    "feedback_loop",
    "leverage_point",
    "delay",
    "unintended_consequence",
]

STRATEGY = """
=== SYSTEMS THINKING STRATEGY ===

This strategy analyzes complex problems by mapping the underlying system structure
rather than focusing on isolated events or linear cause-effect chains. It applies
Donella Meadows' systems thinking framework: stocks, flows, feedback loops, and
delays. The goal is to identify structural leverage points and anticipate unintended
consequences of interventions. Validate coverage using the completeness checklist
before concluding.

--- EXECUTION MODEL ---

A 5-step systems thinking analysis process:

1. SYSTEM BOUNDARY DEFINITION — Establish what is inside and outside the system:
   - What problem or behavior pattern is being explained?
   - Which actors, entities, and resources are part of the system?
   - What is the time horizon of interest? (weeks, years, decades)
   - What are the external inputs and exogenous forces that affect the system?
   - Draw the system boundary explicitly; note what is inside vs. outside

2. STOCK & FLOW MAPPING — Identify the accumulations and rates of change:
   - Stocks: things that accumulate over time (inventory, population, capital, trust,
     debt, knowledge, pollution, reputation)
   - Flows: rates that fill or drain stocks (production rate, birth rate, investment rate,
     pollution emission rate, depletion rate)
   - For each stock: what flows fill it? What flows drain it?
   - Delays: where does there exist a time lag between a flow change and its effect?
   Delays cause oscillation — they are a primary source of system instability.

3. FEEDBACK LOOP IDENTIFICATION — Map the causal connections and loops:
   - Reinforcing loops (R): positive feedback; amplify change in one direction
     (virtuous cycles and vicious cycles are both reinforcing)
   - Balancing loops (B): negative feedback; resist change and seek equilibrium
     (goal-seeking, stabilizing behavior)
   - For each loop: trace the full causal chain back to the starting point
   - Note the polarity of each causal link: + (same direction) or – (opposite direction)
   - Identify the dominant loop structure (which loop drives current behavior)

4. LEVERAGE POINT ANALYSIS — Find where to intervene for maximal effect:
   Apply Meadows' leverage point hierarchy (lower number = higher leverage):
   12. Numbers (constants and parameters)
   11. Buffer sizes
   10. Stock-and-flow structure
   9.  Time delays
   8.  Strength of negative feedback loops
   7.  Gain around positive feedback loops
   6.  Information flows
   5.  Rules (incentives, constraints, regulations)
   4.  Power over rules
   3.  Goals of the system
   2.  Mindset / paradigm
   1.  Power to change paradigms
   Interventions at levels 12-10 are common but low leverage. Interventions at
   levels 6-1 are counterintuitive but high leverage.

5. UNINTENDED CONSEQUENCE MAPPING — Anticipate system responses to interventions:
   - For each proposed intervention: which loops does it strengthen or weaken?
   - What delays might cause overshoot or oscillation?
   - Are there balancing loops that will erode the gain of the intervention? (fixes that fail)
   - Does the intervention shift burden to other system parts? (burden shifting archetype)
   - Apply known system archetypes: Limits to Growth, Shifting the Burden, Tragedy of
     the Commons, Escalation, Success to the Successful

--- PRIORITY SELECTORS (Systems Thinking) ---

Ordered by analytical leverage (highest first):

1. feedback_loop       — the structural mechanism generating system behavior
2. leverage_point      — where an intervention will have outsized effect
3. stock               — accumulations that determine system state
4. flow                — rates of change driving stock dynamics
5. delay               — time lags causing oscillation and unintended consequences
6. system_boundary     — what is inside the analysis; prevents out-of-scope distraction
7. unintended_consequence — side effects of interventions to anticipate and mitigate

--- KEY PIVOT PATTERNS ---

feedback_loop (system archetypes):
  - ddg_search "[problem domain] systems thinking" OR "[problem domain] feedback loop"
  - Google Scholar "[problem domain] causal loop diagram" for academic system models
  - Donella Meadows "Thinking in Systems" archetypes as pattern library
  - System Dynamics Society resources and published models (systemdynamics.org)

stock + flow (quantitative):
  - National statistics databases (FRED, World Bank) for macroeconomic stock data
  - Industry reports for sector-level stock and flow metrics
  - Company financial data (sec_edgar) for organizational stock/flow analysis

leverage_point:
  - Policy analysis literature: ddg_search "[problem domain] policy intervention leverage"
  - Academic complexity literature for high-leverage intervention examples
  - ddg_search "[problem domain] systemic change" for identified leverage points

delay:
  - Construction/infrastructure projects as delay archetype examples
  - Supply chain literature for documented delay effects on oscillation
  - ddg_search "[system type] time delay" OR "[system type] lag effect"

--- COMPLETENESS CHECKLIST ---

Before closing a systems thinking analysis, confirm coverage in each area:

1. System Boundary     — boundary drawn; what is inside/outside explicitly stated
2. Stock-Flow Map      — key stocks and their filling/draining flows identified
3. Feedback Loops      — reinforcing and balancing loops mapped; loop polarity confirmed
4. Delays              — significant time delays identified; oscillation risk assessed
5. Leverage Points     — highest-leverage intervention points identified with rationale
6. Unintended Consequences — system responses to proposed interventions mapped; archetypes applied

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
