"""Root cause analysis explanation sub-strategy module."""

CATEGORY = "explanation"
NAME = "root_cause_analysis"
DISPLAY_NAME = "Root Cause Analysis"
DESCRIPTION = (
    "Systematic investigation of failures using 5 Whys and Fishbone/Ishikawa 6M "
    "framework. Hypothesis elimination is mandatory. ACH is recommended for complex "
    "multi-factor incidents. Produces corrective actions with verification methods."
)
SELECTORS = [
    "symptom",
    "timeline",
    "hypothesis",
    "evidence",
    "system_component",
    "change_record",
    "prior_incident",
]

STRATEGY = """
=== ROOT CAUSE ANALYSIS STRATEGY ===

This strategy guides systematic investigation of failures, incidents, and problems
to their root causes using the 5 Whys technique and Fishbone/Ishikawa 6M framework.
Hypothesis elimination is mandatory. The Analysis of Competing Hypotheses (ACH)
method is recommended for complex multi-factor incidents. Validate coverage using
the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step root cause investigation process:

1. SYMPTOM DOCUMENTATION — Before any analysis begins, document the symptom precisely:
   - What happened? (observable effect, not inferred cause)
   - When did it first occur? (timestamp, frequency, duration)
   - Where did it occur? (system, component, location, environment)
   - Who observed it? (stakeholders affected, reporting chain)
   - What was the impact? (quantified severity: downtime, financial, safety, reputational)
   - What changed recently? (deployments, configuration changes, environmental shifts)
   Do not skip this step. Poorly documented symptoms produce false root causes.

2. FISHBONE / ISHIKAWA ANALYSIS — Map potential contributing factors using the 6M categories:
   - Man (People): human error, training gaps, procedural non-compliance, fatigue
   - Machine (Equipment): hardware failure, wear, calibration, software bugs, tooling
   - Material (Inputs): input data quality, dependency failures, third-party components
   - Method (Process): flawed procedures, missing steps, inadequate documentation
   - Measurement (Metrics): monitoring blind spots, incorrect alerting thresholds, lag
   - Milieu (Environment): network conditions, environmental factors, concurrent load
   For each bone, generate at least 2 candidate contributing factors supported by evidence.

3. 5 WHYS DRILL-DOWN — For the most plausible contributing factors from the fishbone,
   apply iterative "Why?" questioning:
   - Why did X occur? → Because of Y
   - Why did Y occur? → Because of Z
   - Continue until a root cause is reached (actionable, not circular, not "human error")
   Apply 5 Whys independently to at least 2 candidate factors to expose whether
   they converge on the same root cause or reveal independent root causes.

4. HYPOTHESIS ELIMINATION — Enumerate all credible hypotheses from the fishbone and
   5 Whys analysis. For each hypothesis:
   - List the evidence that supports it
   - List the evidence that contradicts it
   - Assign a confidence level (High / Medium / Low)
   Apply ACH (Analysis of Competing Hypotheses): build a matrix of hypotheses vs.
   evidence; identify hypotheses inconsistent with the most diagnostic evidence;
   eliminate those hypotheses; retain the remainder for root cause candidates.

5. ROOT CAUSE AND FIX DESIGN — Identify the root cause(s) surviving hypothesis
   elimination and design corrective actions:
   - Immediate containment action (stop the bleeding)
   - Root cause corrective action (eliminate the cause)
   - Systemic corrective action (prevent recurrence in similar systems)
   - Verification method (how will you confirm the fix is effective?)
   Flag if multiple independent root causes exist — a single fix may be insufficient.

--- PRIORITY SELECTORS (Root Cause Analysis) ---

Ordered by research leverage (highest priority first):

1. symptom            — precise observable description of the problem effect
2. timeline           — chronological sequence of events leading to the symptom
3. hypothesis         — candidate contributing factor or causal chain under investigation
4. evidence           — data, logs, measurements, and observations supporting/refuting hypotheses
5. system_component   — specific component, process, or actor implicated in the causal chain
6. change_record      — recent changes (deployments, config, personnel, environment)
7. prior_incident     — historical occurrences of same or similar symptoms

--- KEY PIVOT PATTERNS ---

symptom:
  - system logs, error messages, and monitoring dashboards for exact failure signatures
  - incident management systems (PagerDuty, Jira, ServiceNow) for timeline reconstruction
  - customer reports and support tickets for impact quantification

timeline:
  - distributed tracing systems (Jaeger, Zipkin, Datadog APM) for service-level timelines
  - audit logs and change management records for configuration changes
  - deployment records (CI/CD pipeline logs) for recent code changes

hypothesis (fishbone pivot):
  - 6M category cross-reference: for each bone, search historical incidents in same category
  - search "[system name] known issues" or "[component] failure modes" in vendor documentation
  - peer incident databases (NTSB, FDA MAUDE, NIST NVD for CVEs) for analogous failures

evidence:
  - metrics dashboards: CPU, memory, latency, error rate time-series at incident window
  - A/B comparison: healthy vs. failing instances for differential diagnosis
  - packet captures, database query logs, and application traces for causal chain evidence

--- INVESTIGATION PRINCIPLES ---

SYMPTOM-FIRST DISCIPLINE
  Never skip symptom documentation. Starting with a hypothesis before documenting the
  symptom is confirmation bias in action. Document what was observed, not what was assumed.

5 WHYS TECHNIQUE
  Ask "Why?" until you reach an actionable root cause that can be fixed. "Human error"
  is never a root cause — it is a symptom of a missing process, tool, or training.
  The root cause is the condition that made human error possible.

FISHBONE 6M COVERAGE
  Generate candidates in all 6M categories before prioritizing. The actual root cause
  often lives in an unexpected category (e.g., Measurement/Milieu, not Machine/Man).
  Tunnel vision on one category produces incomplete analyses.

HYPOTHESIS ELIMINATION
  Retain only hypotheses consistent with the totality of evidence. The most diagnostic
  evidence is evidence that distinguishes between hypotheses — seek that evidence actively.
  ACH is recommended for incidents with 3+ competing hypotheses.

ACH RECOMMENDATION
  For complex incidents with multiple plausible hypotheses, use the Analysis of Competing
  Hypotheses matrix: list hypotheses as columns, evidence as rows, mark consistent (+)
  or inconsistent (-) for each cell. Eliminate hypotheses with multiple inconsistencies.

--- COMPLETENESS CHECKLIST ---

Before closing a root cause analysis task, confirm coverage in each area:

1. Symptom Documented       — observable effect, timing, location, impact, and recent
                               changes all documented before analysis began
2. 3+ Hypotheses            — at least 3 candidate contributing factors generated across
                               multiple 6M fishbone categories
3. Evidence Collected       — logs, metrics, traces, and change records gathered;
                               evidence explicitly mapped to each hypothesis
4. Alternatives Eliminated  — ACH or equivalent elimination applied; hypotheses
                               inconsistent with diagnostic evidence removed
5. Root Cause Identified    — surviving hypothesis(es) confirmed as root cause with
                               supporting evidence chain; circular reasoning absent
6. Fix Designed             — immediate containment, root cause corrective action, and
                               systemic prevention defined; verification method specified

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
