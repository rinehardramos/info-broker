"""Engineering R&D research strategy module."""

ENTITY_TYPE = "engineering_rd"

STRATEGY = """
=== ENGINEERING R&D STRATEGY ===

goal: Advance technology from concept to validated prototype using TRL as progression framework. Stage-gate discipline prevents premature scale-up.
execution_model: trl_assess → requirements_define → design_research → prototype_validation_plan → scale_up_path

TRL scale (NASA/DoD): TRL 1=basic_principles | TRL 2=concept_formulated | TRL 3=experimental_PoC | TRL 4=lab_validated | TRL 5=relevant_env_validated | TRL 6=relevant_env_demonstrated | TRL 7=prototype_operational | TRL 8=system_qualified | TRL 9=operational_proven

PRIORITY SELECTORS: technology | trl_level | requirements | prior_art | failure_mode | test_environment | scale_up_path

pivots:
technology → IEEE_Xplore | AIAA/ASME | Google_Patents | NIST/ISO/IEC_standards | arXiv
trl_level → NASA_TRL_calculator | ESA_TRL_guidelines | DoD_TRA_handbook | "[technology] readiness"
failure_mode → FMEA_databases | NTSB/ESA_incident_reports | IEEE_Reliability | "[technology] failure mode"
requirements → MIL-STD-961 | IEEE_829 | regulatory_filings(FCC/FAA/FDA) | benchmark_studies

principles: TRL-ASSESSMENT-FIRST | STAGE-GATE-PROGRESSION | PROTOTYPE-VALIDATION | REQUIREMENTS-TRACEABILITY

COMPLETENESS CHECKLIST: current_TRL(assessed+blockers) | requirements(functional+performance+interface+constraint) | design(SOTA+standards) | validation_plan(KPPs+pass/fail) | scale_up_path(TRL_gates+MRL+regulatory)
"""
