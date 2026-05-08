"""Systems analysis explanation sub-strategy module."""

CATEGORY = "explanation"
NAME = "systems_analysis"
DISPLAY_NAME = "Systems Analysis"
DESCRIPTION = (
    "Investigates complex systems using system dynamics thinking: feedback loop "
    "mapping, Meadows' 12 leverage points, causal loop diagrams, and intervention "
    "design. Identifies high-leverage interventions, not surface-level symptom fixes."
)
SELECTORS = [
    "system_boundary",
    "feedback_loop",
    "leverage_point",
    "stock",
    "delay",
    "reference_behavior",
    "intervention",
]

STRATEGY = """
=== SYSTEMS ANALYSIS STRATEGY ===

This strategy guides investigation into complex systems using system dynamics thinking:
feedback loop mapping, Meadows' 12 leverage points, causal loop diagrams, and
intervention design. The goal is to identify high-leverage interventions, not
surface-level symptom fixes. Validate coverage using the completeness checklist
before concluding.

--- EXECUTION MODEL ---

A 5-step systems analysis process:

1. SYSTEM BOUNDARY DEFINITION — Define what is inside and outside the system:
   - Identify the primary actors, components, and processes included
   - Identify external forces (exogenous variables) that influence but are not
     part of the system
   - Define the spatial and temporal scope of analysis
   - Identify the reference behavior pattern: what behavior over time is the system
     exhibiting that motivates the analysis? (growth, oscillation, collapse, stagnation)
   Unclear system boundaries produce models that explain everything and predict nothing.

2. FEEDBACK LOOP MAPPING — Identify and categorize all significant feedback loops:
   - Reinforcing loops (R): self-amplifying dynamics that drive exponential growth
     or collapse (virtuous cycles and vicious cycles)
   - Balancing loops (B): goal-seeking dynamics that resist change and maintain
     equilibrium or create oscillation when delayed
   For each loop: name it, trace the causal chain (A → B → C → ... → A), identify
   the loop polarity, and assess its current dominance in the system behavior.
   Construct a Causal Loop Diagram (CLD) documenting all identified loops.

3. STOCK AND FLOW ANALYSIS — Identify the key stocks (accumulations) and flows
   (rates of change) in the system:
   - Stocks: quantities that accumulate over time (inventory, population, trust,
     debt, knowledge, CO2 concentration)
   - Inflows: rates that increase stocks
   - Outflows: rates that decrease stocks
   - Identify which stocks are creating inertia or delays in the system
   Stocks are where system memory lives; delays create oscillation and instability.

4. LEVERAGE POINT IDENTIFICATION — Apply Meadows' 12 leverage points (ordered from
   least to most powerful):
     12. Numbers (constants and parameters)
     11. Buffer sizes relative to flows
     10. Stock-and-flow structures
      9. Delays
      8. Balancing feedback loop strength
      7. Reinforcing feedback loop gain
      6. Information flows (who has access to what)
      5. Rules (incentives, constraints, punishments)
      4. Self-organization (system's ability to change its own structure)
      3. Goals (the purpose or function of the system)
      2. Paradigms (the mindset from which the system arises)
      1. Power to transcend paradigms
   For each candidate intervention, identify which leverage point level it operates at.
   Low-leverage interventions (12-10) produce limited effect; high-leverage ones (6-1)
   can fundamentally shift system behavior.

5. INTERVENTION DESIGN — Design interventions targeting the highest-leverage points
   accessible given constraints:
   - State the target leverage point and the expected mechanism of change
   - Identify potential unintended consequences (especially counterintuitive effects
     of strengthening balancing loops or weakening reinforcing loops)
   - Define indicators to monitor whether the intervention is producing the intended
     system behavior change
   - Flag side effects and second-order consequences in connected loops

--- PRIORITY SELECTORS (Systems Analysis) ---

Ordered by research leverage (highest priority first):

1. system_boundary    — the defined scope of the system under analysis
2. feedback_loop      — identified reinforcing and balancing loops and their interactions
3. leverage_point     — the Meadows leverage point level targeted by an intervention
4. stock              — key accumulations creating system inertia and memory
5. delay              — time lags causing oscillation, overshoot, or instability
6. reference_behavior — the historical or projected behavior pattern motivating analysis
7. intervention       — proposed action targeting a specific leverage point

--- KEY PIVOT PATTERNS ---

system_boundary:
  - Identify "problem owners" and stakeholders to establish relevant system scope
  - Search "[problem domain] systems thinking" OR "[problem domain] system dynamics"
  - Donella Meadows' "Thinking in Systems" and Sterman's "Business Dynamics" for
    canonical examples of similar system types

feedback_loop:
  - Search "[domain] feedback loop" OR "[domain] vicious cycle" OR "[domain] virtuous cycle"
  - Academic system dynamics literature (System Dynamics Review journal)
  - Causal loop diagram examples from Vensim, AnyLogic, and InsightMaker model libraries

leverage_point:
  - Meadows (1999) "Leverage Points: Places to Intervene in a System" — primary reference
  - Search "[domain] systemic intervention" OR "[domain] structural change" for examples
    of high-leverage interventions in the domain

stock:
  - Identify slow-moving quantities that resist rapid change (institutional inertia,
    physical infrastructure, belief systems, ecological stocks)
  - System dynamics models from similar domains (ISDC conference proceedings)

delay:
  - Identify supply chain lead times, information reporting lags, biological response
    times, and policy implementation delays in the system
  - Research "[domain] time delay" OR "[domain] lag" in operational management literature

--- INVESTIGATION PRINCIPLES ---

FEEDBACK LOOP PRIMACY
  System behavior emerges from feedback loop interactions, not from individual
  component properties. Do not explain system behavior by pointing to a single actor
  or component — trace the loop structure.

REINFORCING VS. BALANCING DISTINCTION
  Always classify each loop before analyzing its role. Reinforcing loops drive
  exponential dynamics; balancing loops drive equilibrium-seeking. Confusing them
  produces incorrect intervention predictions.

MEADOWS' 12 LEVERAGE POINTS
  Interventions at the parameter level (level 12) rarely produce lasting change.
  Seek interventions at the information flows, rules, goals, or paradigm levels
  (levels 6-1) for systemic impact. However, acknowledge that higher-leverage
  interventions face greater resistance.

CAUSAL LOOP DIAGRAMS
  Document the system structure visually before analyzing it. A CLD makes loop
  dominance, delays, and intervention targets explicit and prevents ambiguity in
  the analysis.

UNINTENDED CONSEQUENCES
  Every intervention in a complex system produces side effects. Before recommending
  any intervention, trace its effect through connected loops for at least two
  degrees of separation.

--- COMPLETENESS CHECKLIST ---

Before closing a systems analysis task, confirm coverage in each area:

1. System Boundary       — system scope, exogenous variables, and reference behavior
                           pattern documented; temporal and spatial scope defined
2. Feedback Loops        — all significant R and B loops identified and named;
                           causal loop diagram constructed; loop polarity verified
3. Leverage Points       — candidate interventions mapped to Meadows leverage point
                           levels; highest-accessible leverage point identified
4. Reference Behavior    — historical or modeled behavior pattern described;
                           key stocks and delays causing the pattern identified
5. Intervention Design   — at least 1 intervention per top leverage point designed;
                           mechanism stated; unintended consequences traced;
                           monitoring indicators defined

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
