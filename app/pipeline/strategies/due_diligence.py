"""Due diligence investigation strategy module."""

ENTITY_TYPE = "due_diligence"

STRATEGY = """
=== DUE DILIGENCE STRATEGY ===

scope: KYC/AML, compliance screening, M&A/investment due diligence. Most rigorous mode — every claim corroborated, every gap documented, audit trail mandatory.

execution_model: seed → identity_verify(2+ sources) → sentinel_screening(MANDATORY) → expand → corroborate → gap_fill+audit

priority_selectors: full_name+DOB | national_id/passport | registration_number | domain | employer | ticker_symbol | email/phone

--- KEY PIVOT PATTERNS ---

identity_anchors → run_pep_sanctions_screen | run_adverse_media | public_court_records
corporate_structure → run_opencorporates | run_ph_sec_dti | run_sec_edgar | jurisdiction registries
financial_indicators → run_sec_edgar | run_crypto_tracer[SENTINEL] | property_records | UBO_registries
source_of_wealth → business_registration_history | public_filings | run_opencorporates | adverse_media(inheritance/lawsuit)
professional_background → linkedin_navigator | apollo_zoominfo | run_multi_search(press/board/conference)
digital_footprint(corroborative) → run_hibp_lookup | whois_lookup | run_shodan_search

--- SENTINEL SCREENING (MANDATORY — run before any output) ---

PEP/SANCTIONS: run_pep_sanctions_screen — OFAC SDN/Non-SDN, UN, EU, HMT, World Bank, INTERPOL. PEP tiers: T1(heads of state) | T2(senior officials) | T3(close associates/family).
ADVERSE_MEDIA: run_adverse_media — fraud/bribery/corruption/AML/tax evasion/regulatory/criminal. Min 10 years lookback; no limit for criminal convictions.
COURT_RECORDS: criminal | civil | bankruptcy/insolvency | regulatory enforcement (SEC/FCA/MAS/BSP).
Any positive hit → ESCALATION FLAG + document.

--- ADMIRALTY RATING (MANDATORY — due_diligence only) ---

Source reliability: A(gov registry/audited filing) | B(established news/court record) | C(professional DB) | D(social media/unverified web) | E(anon tip/dark web) | F(cannot judge)
Information credibility: 1(confirmed multi-source) | 2(probably true) | 3(possibly true) | 4(doubtful) | 5(improbable) | 6(cannot judge)

--- STIX TAGGING ---

Tag findings with STIX 2.1: identity | threat-actor | relationship | observed-data | report. Document entity relationships using STIX relationship objects.

hop_depth: 2-3 hops to trace beneficial ownership. subject → owned/controlled entities → parent/holding → UBO. Flag circular ownership and nominee director patterns as RED FLAGS.

--- COMPLETENESS CHECKLIST ---

Before closing, mark each domain CONFIRMED/PARTIAL/NOT_FOUND/NOT_ATTEMPTED (12+ domains required):
identity | digital_footprint | family/associates | professional | financial | public_records | visual | communication | breach | communities | pep_sanctions | source_of_wealth | ubo_ownership
NOT_ATTEMPTED must include explicit justification for audit purposes.
"""
