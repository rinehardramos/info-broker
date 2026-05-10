"""Systems analysis research strategy module."""

ENTITY_TYPE = "systems_analysis"

STRATEGY = """
=== SYSTEMS ANALYSIS STRATEGY ===

goal: Identify high-leverage interventions in complex systems using feedback loop mapping and Meadows' 12 leverage points.
execution_model: system_boundary_define → feedback_loop_map → stock_flow_analyze → leverage_point_identify → intervention_design

loop types: Reinforcing(R+,exponential) | Balancing(B-,equilibrium_seeking)

Meadows leverage points (weakest→strongest):
12=numbers | 11=buffer_sizes | 10=stock-flow_structures | 9=delays | 8=balancing_loop_strength | 7=reinforcing_loop_gain | 6=information_flows | 5=rules | 4=self-organization | 3=goals | 2=paradigms | 1=transcend_paradigms

PRIORITY SELECTORS: system_boundary | feedback_loop | leverage_point | stock | delay | reference_behavior | intervention

pivots:
system_boundary → stakeholder_identification | "[problem] systems thinking" | Meadows/Sterman_canonical_examples
feedback_loop → "[domain] feedback loop" | "[domain] vicious_cycle" | System_Dynamics_Review_journal | Vensim/AnyLogic_models
leverage_point → Meadows(1999)_primary_reference | "[domain] systemic intervention"
stock → slow-moving_quantities(institutions/infrastructure/beliefs) | ISDC_conference_proceedings
delay → supply_chain_lead_times | information_reporting_lags | policy_implementation_delays

principles: FEEDBACK-LOOP-PRIMACY | R-VS-B-DISTINCTION | MEADOWS-12-LEVERAGE(seek_6-1) | CLD-REQUIRED | UNINTENDED-CONSEQUENCES(trace_2_degrees)

COMPLETENESS CHECKLIST: system_boundary(scope+exogenous+reference_behavior) | feedback_loops(R+B_named+CLD) | leverage_points(mapped_to_Meadows) | reference_behavior(stocks+delays) | intervention_design(mechanism+unintended_consequences+monitoring)
"""
