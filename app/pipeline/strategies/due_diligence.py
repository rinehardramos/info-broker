"""Due diligence investigation strategy module."""

ENTITY_TYPE = "due_diligence"

STRATEGY = """
=== DUE DILIGENCE STRATEGY ===

This strategy supports KYC (Know Your Customer), AML (Anti-Money Laundering),
compliance screening, and M&A / investment due diligence. It is the most
comprehensive and adversarially rigorous investigation type. Every claim must
be corroborated; every gap must be documented. Audit trail is mandatory.

--- EXECUTION MODEL ---

A 6-step compliance-grade process:

1. SEED — Accept initial selectors: full_name, date_of_birth, nationality,
   employer, domain, registration_number, or passport/ID (where legally
   permissible). Document all seed selectors with source and timestamp.

2. IDENTITY VERIFICATION — Confirm the subject's legal identity through at
   least two independent registry or documentary sources before proceeding.
   Flag any discrepancies as RED FLAGS for manual review.

3. SENTINEL SCREENING (MANDATORY) — Run all three screens before any
   further investigation:
   a. PEP/Sanctions screen — run_pep_sanctions_screen against OFAC, UN,
      EU, HMT, and local watchlists.
   b. Adverse media — run_adverse_media for negative news, fraud allegations,
      litigation, and regulatory actions.
   c. Court records — public court record search for criminal, civil, and
      bankruptcy filings.
   Any positive hit triggers an ESCALATION FLAG and must be documented.

4. EXPAND — For each confirmed selector, pivot using the KEY PIVOT PATTERNS
   table. Trace beneficial ownership through corporate structures. Identify
   all entities the subject controls, directs, or benefits from.

5. CORROBORATE — Every material fact requires two independent sources.
   Single-source findings are UNCONFIRMED and must be labeled as such.
   Apply full Admiralty credibility + reliability ratings to all sources.

6. GAP-FILL & AUDIT — Review the COMPLETENESS CHECKLIST. Document any
   domain as NOT ATTEMPTED with explicit justification. Produce a complete
   audit trail: tool called, timestamp, result summary, source URL.

--- PRIORITY SELECTORS (Due Diligence) ---

Ordered by verification power (highest priority first):

1. full_name + date_of_birth  — combined anchor; prevents false merges on common names
2. national_id / passport     — authoritative identity; use where legally accessible
3. registration_number        — definitive legal entity identifier
4. domain                     — pivots to corporate infrastructure and email patterns
5. employer                   — company affiliation; pivots to ownership structure
6. ticker_symbol              — public entities; pivots to regulatory filings
7. email / phone              — contact anchors; pivots to breach data and social

--- KEY PIVOT PATTERNS ---

Identity anchors:
  - run_pep_sanctions_screen (OFAC SDN, UN Consolidated, EU Asset Freeze,
    HMT Financial Sanctions, World Bank Debarred, local watchlists)
  - run_adverse_media (negative news: fraud, bribery, corruption, AML,
    regulatory enforcement, criminal allegations)
  - public records (court filings, bankruptcies, liens, judgments)

Corporate structure:
  - run_opencorporates (registered companies, officer roles, shareholding)
  - run_ph_sec_dti (PH: corporate filings, beneficial ownership disclosure)
  - run_sec_edgar (US public filings: 10-K, proxy, beneficial ownership 13D/13G)
  - Corporate registry lookups in all relevant jurisdictions

Financial indicators:
  - run_sec_edgar (audited financials, going-concern notes, restatements)
  - run_crypto_tracer (on-chain transaction tracing for crypto assets;
    flag mixer usage, darknet market exposure, sanctioned wallet interactions)
  - Property records (real estate ownership, liens, mortgages)
  - UBO (Ultimate Beneficial Owner) registries where available

Source of wealth / source of funds:
  - Business registration history (founding dates, growth trajectory)
  - Public filings (compensation disclosures, Form 4 insider transactions)
  - run_opencorporates (company valuations, liquidation events)
  - Adverse media for inheritance claims, lawsuit settlements, gifts

Professional background:
  - linkedin_navigator (employment history, endorsements)
  - apollo_zoominfo (cross-reference employment dates)
  - run_multi_search (press releases, conference appearances, board memberships)

Digital footprint (corroborative):
  - run_hibp_lookup (breach exposure; reveals shadow identities or aliases)
  - whois_lookup (domain registrations under subject's name or known entities)
  - run_shodan_search (infrastructure tied to subject-controlled domains)

--- ADMIRALTY RATING (MANDATORY) ---

Apply to every source:

Source Reliability (A–F):
  A — Completely reliable (government registry, audited filing)
  B — Usually reliable (established news outlet, court record)
  C — Fairly reliable (professional database, industry report)
  D — Not always reliable (social media, unverified web content)
  E — Unreliable (anonymous tip, dark web forum)
  F — Cannot be judged

Information Credibility (1–6):
  1 — Confirmed by other independent sources
  2 — Probably true (logical, consistent with other info)
  3 — Possibly true (some corroboration)
  4 — Doubtful (no corroboration)
  5 — Improbable (contradicts known facts)
  6 — Cannot be judged

--- STIX TAGGING ---

Tag all findings with STIX 2.1 object types where applicable:
  identity, threat-actor, relationship, observed-data, report
Document relationships between entities using STIX relationship objects.

--- SENTINEL TACTICS (MANDATORY SCREENS) ---

PEP / SANCTIONS (mandatory before any output):
  - run_pep_sanctions_screen against all major watchlists
  - Include: OFAC SDN, OFAC Non-SDN, UN Security Council, EU Asset Freeze,
    HMT UK Financial Sanctions, World Bank Debarred, INTERPOL Red Notices
  - PEP classification: Tier 1 (heads of state), Tier 2 (senior officials),
    Tier 3 (close associates/family)

ADVERSE MEDIA (mandatory):
  - run_adverse_media with keywords: fraud, bribery, corruption, money
    laundering, tax evasion, regulatory action, criminal, convicted, arrested
  - Time range: at minimum last 10 years; no limit for criminal convictions

COURT RECORDS (mandatory):
  - Criminal records (all relevant jurisdictions)
  - Civil litigation (material suits, judgments, settlements)
  - Bankruptcy / insolvency filings
  - Regulatory enforcement actions (SEC, FCA, MAS, BSP, etc.)

--- HOP DEPTH ---

2–3 hops to trace beneficial ownership through corporate shells:
  subject → owned/controlled companies → parent/holding entities
  → ultimate beneficial owner(s)

Each hop requires corroboration. Flag circular ownership structures
and nominee director patterns as RED FLAGS.

--- COMPLETENESS CHECKLIST ---

Before closing a due diligence investigation, confirm at least one data
point per domain (12+ domains required):

Standard 10 domains:
1.  Identity              — full legal name, aliases, DOB, nationality, national ID
2.  Digital footprint     — email addresses, usernames, social media profiles
3.  Family / associates   — known relatives, business partners, close associates
4.  Professional          — employment history, board memberships, professional licenses
5.  Financial             — business registrations, property, public filings, assets
6.  Public records        — court records, bankruptcies, liens, regulatory actions
7.  Visual                — profile photos, verified likeness, ID document images
8.  Communication         — active phone numbers, messaging app presence
9.  Dark web / breach     — breach exposure, leaked credentials, dark web mentions
10. Online communities    — forums, social platforms, niche communities

Compliance domains (mandatory for KYC/AML):
11. PEP / Sanctions       — watchlist screening result, tier classification, match details
12. Source of wealth      — documented origin of subject's assets and net worth
13. UBO / ownership       — beneficial ownership map through all controlled entities

Mark each domain as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
Document NOT ATTEMPTED with explicit justification for audit purposes.
"""
