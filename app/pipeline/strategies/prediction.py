"""Prediction research strategy module."""

ENTITY_TYPE = "prediction"

STRATEGY = """
=== PREDICTION RESEARCH STRATEGY ===

This strategy defines how to conduct rigorous research oriented toward forecasting
future states, trends, or outcomes. The goal is to build well-grounded scenarios
supported by identified signals, quantified uncertainties, and actor assessments.
Follow the execution model, honor the priority selector order, and validate
coverage using the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 6-step signal-to-scenario process:

1. SIGNAL DETECTION — Identify early indicators that the phenomenon of interest
   is changing or emerging. Distinguish strong signals (corroborated, measurable)
   from weak signals (anecdotal, emerging). Cast a wide net across domains,
   geographies, and time horizons before narrowing.

2. TREND IDENTIFICATION — Aggregate signals into coherent trends. A trend is a
   directional change in a measurable variable over a meaningful time period.
   Distinguish genuine trends from noise, cycles, and one-off events. Quantify
   trend trajectories where data permits.

3. DRIVER ANALYSIS — For each trend, identify the underlying forces (drivers)
   sustaining it. Drivers may be technological, economic, demographic, political,
   environmental, or social (STEPES framework). Distinguish primary drivers from
   secondary amplifiers.

4. UNCERTAINTY MAPPING — Identify the critical uncertainties: factors whose future
   state is both highly uncertain and highly impactful. Distinguish knowable
   uncertainties (reducible with more research) from fundamental uncertainties
   (irreducible). Build an uncertainty matrix.

5. SCENARIO CONSTRUCTION — Construct divergent scenarios by varying the critical
   uncertainties. Use a 2x2 matrix for the top two uncertainties, producing four
   distinct scenarios. Each scenario should be internally consistent, distinctly
   different, and plausible given current evidence.

6. ACTOR ASSESSMENT — For each scenario, identify key actors (governments,
   corporations, movements, individuals) who will shape or be shaped by the
   outcome. Assess their interests, capabilities, and likely responses to each
   scenario.

--- PRIORITY SELECTORS (Prediction) ---

Ordered by forecasting leverage (highest priority first):

1. signal        — early indicator of change; the raw input to the prediction process
2. trend         — aggregated directional pattern derived from multiple signals
3. driver        — underlying force sustaining a trend; root of the trajectory
4. uncertainty   — high-impact, high-uncertainty factor that shapes scenario space
5. scenario      — internally consistent future state combining trend + uncertainty outcomes
6. weak_signal   — low-amplitude, early-stage indicator of potential future disruption
7. actor         — entity whose decisions and capabilities will shape the future state
8. constraint    — structural limit (physical, regulatory, economic) that bounds outcomes

--- KEY PIVOT PATTERNS ---

signal:
  - trend validation: search for corroborating signals across independent sources
  - cause/driver search: ask why this signal is appearing now; what is driving it?
  - quantification: find datasets or metrics that make the signal measurable
  - historical precedent: has this signal appeared before? what followed?

trend:
  - projection/forecast: extend the trend using historical rates; model inflection points
  - risk/disruption search: what could reverse, accelerate, or plateau this trend?
  - cross-domain check: is this trend emerging in adjacent domains simultaneously?
  - search for contradictory trends that may offset or interact with this one

uncertainty:
  - scenario construction: place uncertainty on one axis of the scenario matrix
  - expert opinion: search for forecasters, analysts, and domain experts who have
    assessed this uncertainty
  - historical precedent: find analogous uncertainties from history and their resolution
  - sensitivity analysis: how much does the outcome change as this uncertainty shifts?

weak_signal:
  - amplification search: are there conditions that could rapidly amplify this signal?
  - early adopter communities: who is already acting on this signal? what do they see?
  - technology readiness: is there enabling technology approaching maturity?

actor:
  - interest mapping: what does this actor gain or lose under each scenario?
  - capability assessment: what resources, influence, and tools does this actor control?
  - historical behavior: how has this actor responded to analogous conditions before?
  - coalition analysis: which actors are likely to align or conflict under each scenario?

constraint:
  - physical limits: thermodynamic, biological, geographic boundaries on the outcome
  - regulatory landscape: laws, treaties, and standards that bound actor behavior
  - economic viability: cost curves, market size, and financing conditions

--- INVESTIGATION PRINCIPLES ---

MULTI-SOURCE SIGNALS
  No single source is sufficient. Corroborate every signal with at least two
  independent sources before treating it as a confirmed input to trend analysis.
  Single-source signals are labeled CANDIDATE.

DISTINGUISH TREND FROM NOISE
  Not every movement is a trend. Apply time-series discipline: require directional
  consistency across multiple periods before declaring a trend. Distinguish
  structural trends from cyclical fluctuations and random variation.

MAP UNCERTAINTIES
  Prediction without explicit uncertainty mapping is overconfidence. Every forecast
  must be accompanied by a documented set of critical uncertainties and their
  plausible ranges. Assign confidence levels where possible.

BUILD DIVERGENT SCENARIOS
  Do not produce a single "most likely" future. Build at least two divergent
  scenarios that span the uncertainty space. Scenarios that all look similar
  indicate insufficient uncertainty mapping.

IDENTIFY KEY ACTORS
  Futures are not purely structural — they are shaped by human decisions. Identify
  the actors who have the most leverage over each critical uncertainty and assess
  their likely behavior under each scenario.

--- COMPLETENESS CHECKLIST ---

Before closing a prediction research task, confirm coverage in each area:

1. Signal Coverage       — signals gathered from multiple independent domains and sources
2. Trend Identification  — at least 2 directional trends identified and quantified
3. Driver Analysis       — primary drivers identified for each trend using STEPES framework
4. Uncertainty Mapping   — top critical uncertainties documented with impact/confidence
                           ratings
5. Scenario Construction — at least 2 divergent scenarios built from uncertainty matrix
6. Actor Assessment      — key actors identified and their interests/capabilities mapped
                           per scenario

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
