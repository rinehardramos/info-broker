"""Engineering R&D generation sub-strategy module."""

CATEGORY = "generation"
NAME = "engineering_rd"
DISPLAY_NAME = "Engineering R&D"
DESCRIPTION = (
    "Advances a technology from concept to validated prototype using TRL as the "
    "progression framework. Stage-gate discipline prevents premature scale-up. "
    "Covers requirements definition, design research, and validation planning."
)
SELECTORS = [
    "technology",
    "trl_level",
    "requirements",
    "prior_art",
    "failure_mode",
    "test_environment",
    "scale_up_path",
]

STRATEGY = """
=== ENGINEERING R&D STRATEGY ===

This strategy guides engineering research and development toward advancing a technology
from concept to validated prototype using TRL (Technology Readiness Level) as the
progression framework. Stage-gate discipline prevents premature scale-up. Validate
coverage using the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step stage-gate R&D process anchored to TRL progression:

1. TRL ASSESSMENT — Determine the current Technology Readiness Level of the technology
   under investigation using NASA/DoD TRL definitions:
     TRL 1: Basic principles observed
     TRL 2: Technology concept formulated
     TRL 3: Experimental proof of concept
     TRL 4: Technology validated in lab
     TRL 5: Technology validated in relevant environment
     TRL 6: Technology demonstrated in relevant environment
     TRL 7: System prototype demonstrated in operational environment
     TRL 8: System complete and qualified
     TRL 9: Actual system proven in operational environment
   Justify the TRL assignment with evidence. Identify blockers to reaching the next TRL.

2. REQUIREMENTS DEFINITION — Gather and document all requirements constraining the system:
   - Functional requirements (what it must do)
   - Performance requirements (how well it must do it, with quantitative targets)
   - Interface requirements (physical, electrical, software, data interfaces)
   - Constraint requirements (cost, weight, size, power, materials, regulatory)
   - Verification criteria (how each requirement will be confirmed)

3. DESIGN RESEARCH — Search the engineering and scientific literature for:
   - State-of-the-art approaches at the current TRL and one level above
   - Failure modes and known limitations of existing designs
   - Materials, components, and subsystems available for integration
   - Reference architectures, standards (ISO, IEC, MIL-SPEC, IEEE), and best practices
   - Cost and supply chain considerations for key components

4. PROTOTYPE VALIDATION PLANNING — Define the validation plan for the next TRL gate:
   - Prototype type (paper, virtual, breadboard, brassboard, engineering model)
   - Test environment (laboratory, simulated, relevant environment, operational)
   - Key performance parameters (KPPs) to be measured in validation
   - Pass/fail criteria for each KPP
   - Risk mitigation strategies for top-ranked technical risks
   - Resource and timeline estimates for the validation activity

5. SCALE-UP PATH ANALYSIS — Document the path from current TRL to deployment:
   - Identify the critical TRL gates and their entry/exit criteria
   - Flag manufacturing readiness level (MRL) implications at each stage
   - Identify long-lead items, supply chain risks, and regulatory approval timelines
   - Estimate cost-to-completion by stage

--- PRIORITY SELECTORS (Engineering R&D) ---

Ordered by research leverage (highest priority first):

1. technology         — the core technology or system being developed
2. trl_level          — current TRL and target TRL for the research phase
3. requirements       — performance targets and constraints bounding the design
4. prior_art          — existing designs, patents, and standards to build upon
5. failure_mode       — known failure modes and technical risks at current TRL
6. test_environment   — the environment in which validation will be conducted
7. scale_up_path      — manufacturing, regulatory, and deployment pathway

--- KEY PIVOT PATTERNS ---

technology:
  - IEEE Xplore, AIAA Digital Library, ASME for technical papers on the system
  - Google Patents for prior art and design space mapping
  - NIST, ISO, IEC standards databases for applicable standards
  - arXiv (cs.RO, eess, physics) for preprints in fast-moving engineering areas

trl_level:
  - NASA TRL definitions and TRL calculator for objective assessment
  - ESA TRL guidelines for space systems context
  - DoD Technology Readiness Assessment Handbook for defense applications
  - Search "[technology] TRL" or "[technology] readiness" in defense/aerospace literature

failure_mode:
  - FMEA (Failure Mode and Effects Analysis) databases and templates
  - NTSB/ESA incident reports for lessons learned in operational systems
  - IEEE Reliability Society publications for failure rate data
  - web_search "[technology] failure mode" OR "[technology] root cause" in engineering forums

requirements:
  - MIL-STD-961, IEEE 829 for requirements documentation standards
  - Customer specifications, regulatory filings (FCC, FAA, FDA) for hard constraints
  - Benchmark studies and competitive teardowns for performance targets

--- INVESTIGATION PRINCIPLES ---

TRL ASSESSMENT FIRST
  Establish the current TRL before proposing any design or validation activity. Work
  at the wrong TRL wastes resources — you cannot skip stages in hardware development.

STAGE-GATE PROGRESSION
  Each gate requires documented evidence that the current TRL is achieved before
  advancing. Evidence must be empirical, not theoretical. "It should work" is not
  evidence.

PROTOTYPE VALIDATION
  Every design requires a validation plan before prototyping begins. Define KPPs,
  test environments, and pass/fail criteria upfront to avoid underpowered tests.

REQUIREMENTS TRACEABILITY
  Every design decision must trace to a requirement. Undocumented design decisions
  become technical debt and create integration failures at higher TRL stages.

--- COMPLETENESS CHECKLIST ---

Before closing an engineering R&D research task, confirm coverage in each area:

1. Current TRL         — TRL assessed with justifying evidence; blockers to next TRL identified
2. Requirements        — functional, performance, interface, and constraint requirements
                         documented with quantitative targets where applicable
3. Design              — state-of-the-art approaches surveyed; reference architectures
                         and applicable standards identified
4. Validation Plan     — prototype type, test environment, KPPs, and pass/fail criteria
                         defined for the next TRL gate
5. Scale-Up Path       — critical TRL gates, MRL implications, long-lead items, and
                         regulatory timeline documented

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
