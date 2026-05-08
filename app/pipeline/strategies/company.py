"""Company investigation strategy module."""

ENTITY_TYPE = "company"

STRATEGY = """
=== COMPANY INVESTIGATION STRATEGY ===

This strategy maps a company's legal identity, digital infrastructure,
leadership team, financial standing, competitive position, and technology
stack. Follow the execution model and validate coverage using the completeness
checklist before concluding.

--- EXECUTION MODEL ---

A 5-step entity-centric process:

1. SEED — Accept initial selectors: domain, employer (company name),
   ticker_symbol, registration_number, or LinkedIn company URL.

2. ANCHOR — Resolve the legal entity in at least one company registry
   (OpenCorporates, SEC EDGAR, PH SEC/DTI). Confirm: legal name, jurisdiction,
   registration number, registered address, incorporation date.

3. EXPAND — From the confirmed legal entity, pivot to all adjacent selectors
   using the KEY PIVOT PATTERNS table.

4. DEDUPLICATE — Consolidate records from all registries into one canonical
   company profile. Track provenance for each data point.

5. GAP-FILL — Review the COMPLETENESS CHECKLIST. For each unchecked domain,
   attempt at least one targeted lookup before closing.

--- PRIORITY SELECTORS (Company) ---

Ordered by uniqueness and reliability (highest priority first):

1. domain             — highest uniqueness; pivots to WHOIS, Shodan, Hunter
2. employer           — company name; use for registry and profile lookups
3. ticker_symbol      — public companies only; pivots to SEC EDGAR, financial APIs
4. registration_number — definitive legal identity; use for registry cross-checks

--- KEY PIVOT PATTERNS ---

domain:
  - whois_lookup (registrant, registration date, name servers, hosting provider)
  - run_shodan_search (exposed services, open ports, SSL cert SANs → tech stack)
  - run_hunter_io (domain → employee roster, email patterns, key contacts)
  - run_multi_search (site:domain.com → org structure, press releases, job postings)

employer (company name):
  - run_opencorporates (global registry search → legal name, jurisdiction, officers)
  - run_ph_sec_dti (PH-specific: SEC company lookup, DTI business name registration)
  - apollo_zoominfo (company search → employee count, revenue band, org chart)
  - linkedin_navigator (company page → employee count, recent hires, leadership)

ticker_symbol:
  - run_sec_edgar (10-K, 10-Q, proxy filings → financials, executive compensation)
  - financial data APIs (revenue, market cap, growth metrics)

registration_number:
  - run_opencorporates (direct registry lookup → legal filings, officer history)
  - run_ph_sec_dti (PH: corporate filings, articles of incorporation, GIS)

leadership (extracted from above):
  - apollo_zoominfo (executive profiles → email, phone, LinkedIn)
  - linkedin_navigator (leadership team → tenure, prior employers)
  - run_hunter_io (executive email patterns → verify against known roster)

--- HOP DEPTH ---

Maximum 1 hop for leadership profiles:
  company → executive names → basic professional profiles (name, title, email)
Do not run full PERSON investigation on executives unless explicitly requested.

--- INVESTIGATION PRINCIPLES ---

LEGAL ENTITY FIRST
  Always anchor on the registered legal name before using trade names or
  brand names. "Apple Inc." is the legal entity; "Apple" is the brand.

MULTI-JURISDICTION AWARENESS
  Companies with international operations may have subsidiaries in multiple
  registries. Identify the ultimate parent and material subsidiaries.

TECH STACK FROM INFRASTRUCTURE
  run_shodan_search on the primary domain reveals exposed services (web
  frameworks, database ports, email servers) without active probing of
  application logic.

GLASSDOOR SIGNAL
  Employee reviews surface culture, compensation bands, and leadership
  sentiment — useful for competitive intelligence and acquisition due
  diligence pre-screens.

--- COMPLETENESS CHECKLIST ---

Before closing a company investigation, confirm at least one data point
per domain:

1. Identity          — legal entity name, jurisdiction, registration number, incorporation date
2. Digital presence  — primary domain, hosting provider, tech stack (from Shodan/HTTP headers)
3. Leadership team   — C-suite names and titles; email patterns for key executives
4. Financials        — revenue band, funding rounds or public filings, profitability signal
5. Market position   — industry classification, employee count, key competitors, customer segment
6. Technology stack  — confirmed tech from Shodan, job postings (hiring signals), BuiltWith/Wappalyzer

Mark each domain as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
