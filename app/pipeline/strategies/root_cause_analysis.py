"""Root cause analysis research strategy module."""

ENTITY_TYPE = "root_cause_analysis"

STRATEGY = """
=== ROOT CAUSE ANALYSIS STRATEGY ===

goal: Systematic investigation of failures to root causes using 5 Whys + Fishbone/Ishikawa 6M. ACH recommended for complex incidents.
execution_model: symptom_document → fishbone_6M → 5_Whys_drilldown → hypothesis_elimination(ACH) → root_cause + fix_design

6M categories: Man(human_error) | Machine(hardware/software) | Material(inputs/dependencies) | Method(process) | Measurement(monitoring) | Milieu(environment)

PRIORITY SELECTORS: symptom | timeline | hypothesis | evidence | system_component | change_record | prior_incident

pivots:
symptom → system_logs | incident_mgmt(PagerDuty/Jira/ServiceNow) | customer_reports
timeline → distributed_tracing(Jaeger/Zipkin/Datadog) | audit_logs | CI/CD_pipeline_records
hypothesis → 6M_cross_reference | "[system] known issues" | peer_incident_databases(NTSB/NIST_NVD)
evidence → metrics_dashboards(CPU/memory/latency/error) | A/B_comparison(healthy_vs_failing) | packet_captures

5 Whys: ask "Why?" iteratively until actionable root cause — "human error" is NOT a root cause, it's a symptom of missing process/tool/training.
ACH matrix: hypotheses_as_columns × evidence_as_rows → mark consistent(+)/inconsistent(-) → eliminate multi-inconsistent.

principles: SYMPTOM-FIRST | 5-WHYS-TECHNIQUE | FISHBONE-6M-COVERAGE | HYPOTHESIS-ELIMINATION | ACH-FOR-COMPLEX

COMPLETENESS CHECKLIST: symptom_documented(what+when+where+impact+changes) | 3+_hypotheses(across_6M_categories) | evidence_collected | alternatives_eliminated | root_cause_identified | fix_designed(containment+corrective+systemic+verification)
"""
