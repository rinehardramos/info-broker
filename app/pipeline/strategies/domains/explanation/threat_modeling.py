"""Threat modeling explanation sub-strategy module."""

CATEGORY = "explanation"
NAME = "threat_modeling"
DISPLAY_NAME = "Threat Modeling"
DESCRIPTION = (
    "Systematic identification and analysis of threats to a system using STRIDE, "
    "attack trees, and MITRE ATT&CK frameworks. Produces a prioritized threat "
    "register with mitigations and residual risk assessments."
)
SELECTORS = [
    "system_component",
    "threat_actor",
    "attack_vector",
    "vulnerability",
    "data_flow",
    "trust_boundary",
    "mitigation",
]

STRATEGY = """
=== THREAT MODELING STRATEGY ===

This strategy guides systematic identification and analysis of threats to a system,
application, or organization. It applies structured threat frameworks (STRIDE, MITRE
ATT&CK, attack trees) to produce a prioritized threat register with evidence-based
mitigations and residual risk assessments. Validate coverage using the completeness
checklist before concluding.

--- EXECUTION MODEL ---

A 5-step threat modeling process:

1. SYSTEM DECOMPOSITION — Build a model of the system being analyzed:
   - Enumerate system components: services, databases, interfaces, external dependencies
   - Map data flows: where does data originate, where does it go, how is it transformed?
   - Identify trust boundaries: where does code or data cross from a lower- to
     higher-privilege context? (user → server, server → database, external API → service)
   - Document entry points: all external interfaces where input enters the system
   - Document assets: what is worth protecting? (PII, credentials, intellectual property,
     system availability, financial data, configuration)

2. THREAT ENUMERATION — Identify threats using structured frameworks:
   - STRIDE analysis for each component and data flow:
     S — Spoofing identity (authentication bypass)
     T — Tampering with data (integrity violation)
     R — Repudiation (denial of action without proof)
     I — Information disclosure (confidentiality breach)
     D — Denial of service (availability disruption)
     E — Elevation of privilege (authorization bypass)
   - MITRE ATT&CK: map applicable Tactics and Techniques for the target environment
   - Attack tree construction: for critical assets, build attack trees (root = goal,
     leaves = prerequisite conditions) to enumerate attack paths

3. VULNERABILITY ASSESSMENT — Evaluate which threats are exploitable given current controls:
   - For each threat: does a corresponding vulnerability exist?
   - Control inventory: what existing security controls address this threat?
   - Control gaps: where are controls absent or insufficient?
   - Known CVEs: for external components, check NVD/CVE databases for known vulnerabilities
   - Prioritize by: exploitability × impact × exposure

4. RISK SCORING — Prioritize threats by risk level:
   - Use DREAD or CVSS as a scoring framework:
     DREAD: Damage + Reproducibility + Exploitability + Affected users + Discoverability
   - Risk = Likelihood × Impact
   - Produce a ranked threat register: High / Medium / Low
   - Flag any threats that require immediate action (critical risk threshold)

5. MITIGATION DESIGN — Define countermeasures for prioritized threats:
   - For each high/critical threat: propose one or more specific mitigations
   - Mitigations should be specific and actionable (not "implement security")
   - Classify mitigations: preventive, detective, corrective
   - Residual risk: after mitigation, what risk remains?
   - Assign mitigation ownership and target remediation timeline

--- PRIORITY SELECTORS (Threat Modeling) ---

Ordered by threat modeling leverage (highest first):

1. system_component    — the asset or service being modeled; anchor for STRIDE analysis
2. trust_boundary      — where privilege changes; highest risk interface points
3. attack_vector       — the mechanism of exploitation; determines control requirements
4. data_flow           — movement of sensitive data; source of interception risk
5. vulnerability       — exploitable weakness; connects threat to current control gaps
6. threat_actor        — who has motive and capability to attack; shapes risk prioritization
7. mitigation          — countermeasure; the output of the threat modeling process

--- KEY PIVOT PATTERNS ---

system_component + trust_boundary:
  - OWASP Threat Modeling resources (owasp.org/www-community/Threat_Modeling)
  - Microsoft STRIDE documentation and threat modeling tools
  - ddg_search "[system type] threat modeling" for domain-specific examples
  - NIST SP 800-154 and SP 800-30 for risk assessment methodology

attack_vector:
  - MITRE ATT&CK (attack.mitre.org): Tactics and Techniques for enterprise, cloud, mobile
  - OWASP Top 10 for web application attack vectors
  - CVE/NVD (nvd.nist.gov): known vulnerabilities for specific software components
  - ddg_search "[component or technology] known vulnerabilities [year]"

threat_actor:
  - MITRE ATT&CK Groups for known threat actor profiles and TTPs
  - CISA advisories (cisa.gov/news-events/cybersecurity-advisories) for recent threats
  - Mandiant, CrowdStrike, and Recorded Future public threat intel reports
  - ddg_search "[industry] cyber threat actors" for sector-specific threat intel

vulnerability:
  - NVD (nvd.nist.gov) for CVE search by component and version
  - Exploit Database (exploit-db.com) for public proof-of-concept exploits
  - Vendor security advisories and patch notes
  - ddg_search "[software component] CVE [year]" for recent vulnerability disclosures

mitigation:
  - NIST SP 800 series for control implementation guidance
  - CIS Controls (cisecurity.org/controls) for prioritized security controls
  - OWASP Cheat Sheet Series for specific mitigation implementation guidance
  - ddg_search "mitigate [threat type] [technology stack]" for specific countermeasures

--- COMPLETENESS CHECKLIST ---

Before closing a threat modeling task, confirm coverage in each area:

1. System Model        — components, data flows, trust boundaries, and assets documented
2. Threat Enumeration  — STRIDE applied to all components and data flows; ATT&CK mapped
3. Vulnerability Check — control gaps identified; known CVEs checked for external components
4. Risk Prioritization — threat register produced with High/Medium/Low ratings
5. Mitigations         — specific countermeasures defined for all High/Critical threats
6. Residual Risk       — post-mitigation risk assessed; acceptance or escalation documented

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
