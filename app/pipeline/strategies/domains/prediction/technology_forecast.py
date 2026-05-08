"""Technology forecast prediction sub-strategy module."""

CATEGORY = "prediction"
NAME = "technology_forecast"
DISPLAY_NAME = "Technology Forecast"
DESCRIPTION = (
    "Rigorous technology forecasting using S-curve analysis, weak signal detection, "
    "and scenario construction. Produces a Technology Radar placement "
    "(Adopt/Trial/Assess/Hold) for each technology assessed."
)
SELECTORS = [
    "technology",
    "s_curve_position",
    "weak_signal",
    "scenario",
    "driver",
    "competitor_tech",
    "adoption_metric",
]

STRATEGY = """
=== TECHNOLOGY FORECAST STRATEGY ===

This strategy guides research toward rigorous technology forecasting using S-curve
analysis, weak signal detection, and scenario construction. The output must include
a Technology Radar placement (Adopt/Trial/Assess/Hold) for each technology assessed.
Validate coverage using the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step technology forecasting process:

1. SIGNAL COLLECTION — Gather weak and strong signals about the technology's trajectory:
   - Patent filing trends (velocity, geographic distribution, assignee concentration)
   - Academic publication rate and citation velocity
   - Startup funding signals (Crunchbase, PitchBook — seed/Series A in the domain)
   - Standards activity (IEEE, ISO, IETF working group formation)
   - Government R&D investment signals (DARPA, EU Horizon, national labs)
   - Media and analyst coverage tone shift (from "experimental" to "production-ready")
   Distinguish weak signals (early precursors, minority voices) from strong signals
   (mainstream adoption, regulatory recognition). Do not discard weak signals early.

2. S-CURVE POSITION ASSESSMENT — Position the technology on its S-curve:
   - Emerging: basic research phase, TRL 1-3, no dominant design
   - Growth: rapid capability improvement, TRL 4-6, competing standards
   - Maturity: dominant design established, incremental improvement, TRL 7-9
   - Decline: being displaced by successor technology
   Justify the position using quantitative indicators (publication rate inflection,
   cost trajectory, adoption rate). Identify the inflection point if not yet reached.

3. SCENARIO CONSTRUCTION — Build 3-4 scenarios spanning the uncertainty space:
   - Baseline: most likely trajectory given current signals
   - Accelerated: what triggers faster-than-expected adoption?
   - Delayed: what obstacles could slow the technology?
   - Disrupted: what alternative technology or approach could displace it?
   Ground each scenario in identified drivers and uncertainties.

4. KEY UNCERTAINTIES — Enumerate the principal uncertainties that determine which
   scenario materializes:
   - Technical uncertainties (can the performance gap be closed?)
   - Market uncertainties (will adoption economics improve?)
   - Regulatory uncertainties (will regulators enable or constrain deployment?)
   - Competitive uncertainties (will a disruptive alternative emerge?)
   Rank uncertainties by impact and likelihood.

5. TECHNOLOGY RADAR OUTPUT — Assign a Technology Radar ring for each technology:
   - ADOPT: proven, high confidence; use in production where applicable
   - TRIAL: ready for limited deployment; worth investing in pilots
   - ASSESS: promising but uncertain; worth researching, not yet deploying
   - HOLD: declining, problematic, or being superseded; avoid new investments
   Justify every ring assignment with evidence from signals and S-curve position.

--- PRIORITY SELECTORS (Technology Forecast) ---

Ordered by research leverage (highest priority first):

1. technology         — the specific technology or technology family being forecasted
2. s_curve_position   — current phase and inflection point timing
3. weak_signal        — early precursor signals indicating direction of change
4. scenario           — plausible future trajectory under different conditions
5. driver             — forces accelerating or decelerating adoption
6. competitor_tech    — alternative technologies competing for the same function
7. adoption_metric    — quantitative indicators of current deployment scale

--- KEY PIVOT PATTERNS ---

technology:
  - web_search "[technology] adoption rate" OR "[technology] market size [year]"
  - Gartner Hype Cycle reports for current positioning and time-to-plateau estimates
  - McKinsey Technology Trends annual reports for strategic context
  - IEEE Spectrum and MIT Technology Review for practitioner-level signals

weak_signal:
  - Patent citation network analysis for emerging sub-fields
  - arXiv daily listings for emerging research themes before they hit journals
  - Startup accelerator cohorts (Y Combinator, a16z portfolio) as leading indicators
  - DARPA BAA (Broad Agency Announcements) for government R&D frontier signals

s_curve_position:
  - Publication count by year (Google Scholar, Semantic Scholar) for growth rate
  - Patent filing trend over 5-10 years (declining filing = maturity signal)
  - Component/unit cost trajectory (log-scale plot, Wright's Law curves)
  - Industry analyst consensus on time-to-mainstream

scenario:
  - Identify 2 key uncertainties and build 2x2 scenario matrix
  - Historical analogy: find comparable technology transitions and map timing
  - Delphi expert survey data (if available in literature) for consensus ranges

--- INVESTIGATION PRINCIPLES ---

SIGNAL COVERAGE BREADTH
  Do not forecast from a single signal class. Technology trajectories require
  triangulation across patents, publications, investment, and adoption signals.
  Single-source forecasts have high error rates.

S-CURVE DISCIPLINE
  Position the technology explicitly on the S-curve before building scenarios.
  Forecasting without knowing whether you are pre-inflection or post-inflection
  produces scenarios with wrong time horizons.

WEAK SIGNAL DETECTION
  The most valuable forecasts identify shifts before they are mainstream. Invest
  deliberate search effort in weak signal detection — early indicators in patents,
  government programs, and research preprints.

TECHNOLOGY RADAR OUTPUT
  Every technology assessment must conclude with a Technology Radar ring assignment.
  Ambiguous conclusions without ring placement fail the forecast objective.

--- COMPLETENESS CHECKLIST ---

Before closing a technology forecast research task, confirm coverage in each area:

1. Signal Coverage      — patent, publication, investment, and adoption signals
                          collected and triangulated; sources documented
2. S-Curve Position     — technology positioned on S-curve with quantitative
                          justification; inflection point estimated
3. Key Uncertainties    — top 3-5 uncertainties ranked by impact; monitoring
                          indicators defined for each
4. Scenarios            — at least 3 scenarios (baseline, accelerated, disrupted)
                          with grounding drivers documented
5. Technology Radar     — ring assignment (Adopt/Trial/Assess/Hold) for each
                          technology assessed, with evidence-based justification

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
