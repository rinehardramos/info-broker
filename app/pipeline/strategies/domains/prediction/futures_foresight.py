"""Futures foresight prediction sub-strategy module."""

CATEGORY = "prediction"
NAME = "futures_foresight"
DISPLAY_NAME = "Futures & Foresight"
DESCRIPTION = (
    "Structured exploration of plausible long-range futures using STEEP scanning, "
    "trend analysis, and scenario planning. Produces scenario narratives, early "
    "warning signals, and strategic implications for decision-makers."
)
SELECTORS = [
    "focal_question",
    "trend",
    "weak_signal",
    "driving_force",
    "scenario",
    "time_horizon",
    "wildcard",
]

STRATEGY = """
=== FUTURES & FORESIGHT STRATEGY ===

This strategy guides structured exploration of plausible long-range futures for
strategic planning and organizational resilience. It uses STEEP environmental
scanning, trend analysis, scenario planning, and wild card identification.
The output is not a prediction — it is a set of plausible scenario narratives
with strategic implications. Validate coverage using the completeness checklist
before concluding.

--- EXECUTION MODEL ---

A 5-step futures foresight process:

1. FOCAL QUESTION DEFINITION — Establish what the foresight is for:
   - What decision or strategy does this foresight inform?
   - What is the time horizon? (3 years, 10 years, 30 years)
   - What is the geographic and domain scope?
   - Who are the primary decision-makers who will use the scenarios?
   A clear focal question prevents the research from becoming encyclopedic.

2. STEEP ENVIRONMENTAL SCANNING — Systematically scan for signals of change:
   - Social: demographic shifts, cultural values, behavioral changes, inequality trends
   - Technological: emerging technologies, R&D investment patterns, tech adoption curves
   - Economic: growth patterns, trade flows, financial system changes, labor dynamics
   - Environmental: climate trajectories, resource constraints, biodiversity, energy transition
   - Political: governance changes, geopolitical shifts, regulatory trends, social movements
   For each signal: classify as trend (established), emerging trend (forming), or
   weak signal (early-stage). Distinguish noise from genuine signals.

3. DRIVING FORCE IDENTIFICATION — Select the 2-3 most critical uncertain forces:
   - Identify forces that are: high impact AND high uncertainty
   - Forces with high impact but low uncertainty are predetermined elements
     (include in all scenarios as constants)
   - Forces with low impact can be background context
   - The 2×2 scenario matrix is built on the two most critical uncertain driving forces
   Justify why each selected force is both highly impactful and genuinely uncertain.

4. SCENARIO CONSTRUCTION — Build 4 plausible, distinct, and challenging scenarios:
   - Use the 2×2 matrix: each quadrant = one scenario
   - Each scenario must be internally consistent (no contradictions)
   - Each must be plausible (not fantasy, but possible under stated conditions)
   - Each must be challenging (avoid the "business-as-usual" trap)
   - Name each scenario with a memorable label that captures its essence
   - Write a 1-2 paragraph narrative for each scenario from the future looking back

5. IMPLICATIONS & EARLY WARNINGS — Extract actionable intelligence:
   - For each scenario: what are the strategic implications for the focal question?
   - Identify no-regrets moves (beneficial in all scenarios)
   - Identify hedging moves (beneficial in some scenarios; low cost in others)
   - Define early warning indicators (EMIs): observable signals today that suggest
     a particular scenario is emerging
   - Identify wild cards: high-impact, low-probability events that would disrupt all scenarios

--- PRIORITY SELECTORS (Futures & Foresight) ---

Ordered by foresight leverage (highest first):

1. focal_question    — the strategic question driving the foresight; anchors scope
2. driving_force     — the two critical uncertain forces forming the scenario axes
3. trend             — established directional forces that shape all scenarios
4. scenario          — the plausible future narrative built from driving force combinations
5. weak_signal       — early-stage indicators of potential discontinuity
6. time_horizon      — temporal frame determining relevant trends and uncertainties
7. wildcard          — high-impact, low-probability disruptions that reshape scenarios

--- KEY PIVOT PATTERNS ---

trend (STEEP scanning):
  - Social: Pew Research, World Values Survey, Eurobarometer, Gallup for social trends
  - Technological: MIT Technology Review, Nature, Science for emerging tech signals
    google_news "[technology] emerging trend [year]" for recent coverage
  - Economic: World Bank, IMF World Economic Outlook, FRED for macroeconomic data
  - Environmental: IPCC reports, IEA World Energy Outlook, UNEP for environmental trends
  - Political: Freedom House, Varieties of Democracy (V-Dem), Economist Intelligence Unit

weak_signal:
  - ddg_search "[domain] fringe movements" OR "[domain] emerging practices" OR
    "[domain] early adopters" for signals ahead of mainstream awareness
  - Niche community forums (subreddits, Discord, specialized forums) for practitioner signals
  - Patent filing velocity in adjacent technologies as innovation precursor
  - Startup funding in novel categories as commercialization signal

driving_force (uncertainty assessment):
  - Expert forecast disagreement = high uncertainty indicator
  - ddg_search "[force] forecast disagreement" OR "[force] uncertain future" for debate signals
  - Scenario planning literature (Shell scenarios, RAND futures studies) for framing

wildcard:
  - Global Challenges Foundation Global Catastrophic Risks report
  - World Economic Forum Global Risks Report
  - ddg_search "black swan [domain]" OR "tail risk [domain]" for documented wildcards

scenario (narrative sources):
  - Shell Scenarios (shell.com/scenarios) as exemplar long-range scenarios
  - RAND Pardee Center futures studies for methodology examples
  - Institute for the Future (iftf.org) for published scenario artifacts

--- COMPLETENESS CHECKLIST ---

Before closing a futures foresight task, confirm coverage in each area:

1. STEEP Scan          — signals identified across all 5 STEEP categories
2. Driving Forces      — 2 critical uncertain driving forces selected with justification
3. Predetermined Elements — high-certainty high-impact forces identified as constants
4. Scenario Set        — 4 distinct, plausible, and challenging scenario narratives written
5. Early Warning Signals — observable leading indicators defined for each scenario
6. Strategic Implications — no-regrets and hedging moves identified; wildcards noted

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
