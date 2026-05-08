"""Person investigation strategy module."""

ENTITY_TYPE = "person"

STRATEGY = """
=== PERSON INVESTIGATION STRATEGY ===

This strategy defines how to conduct a thorough, selector-centric investigation
into an individual. Follow the execution model, honor the priority selector order,
and validate coverage using the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step selector-centric process:

1. SEED — Accept the initial selectors provided by the requester (name, email,
   phone, username, employer, address, or photo). Do not fabricate selectors.

2. EXPAND — For each confirmed selector, pivot to adjacent selectors using the
   KEY PIVOT PATTERNS table. Every new confirmed selector becomes a first-class
   seed for further pivots.

3. CORROBORATE — A fact is not confirmed until at least two independent sources
   agree. Flag single-source facts as UNCONFIRMED. Never merge profiles solely
   on name similarity.

4. DEDUPLICATE — Consolidate all gathered profiles into one unified record.
   Track selector provenance (which tool returned it, when).

5. GAP-FILL — Review the COMPLETENESS CHECKLIST. For each unchecked domain,
   attempt at least one targeted lookup before closing the investigation.

--- PRIORITY SELECTORS (Person) ---

Ordered by uniqueness and reliability (highest priority first):

1. full_name          — anchor; low uniqueness alone, requires corroboration
2. email              — high uniqueness; pivots to breaches, social, employer
3. phone              — high uniqueness; pivots to carrier, location, social
4. username / handle  — cross-platform pivot; reveals digital footprint breadth
5. employer / domain  — narrows geographic + professional context
6. address            — physical anchor; pivots to relatives, property records
7. photo / face       — biometric anchor; used only when other selectors stall

--- KEY PIVOT PATTERNS ---

IMPORTANT: Use these EXACT tool names. They are available as MCP tools.

full_name:
  - run_multi_search(query="full name" + location) — multi-engine web search (DDG+Google+Brave)
  - run_linkedin_profile_search(search_url) — LinkedIn profile discovery
  - run_apollo_search(query, search_type="people") — professional contact data
  - run_email_enumerator(first_name, last_name) — generate + verify candidate emails at Gmail/Yahoo/Hotmail/Outlook/iCloud/ProtonMail
  - run_email_enumerator(first_name, last_name, domain_hints=["employer.com"]) — try employer domain patterns too
  - run_facebook_pages(query) — Facebook profile and connections
  - run_instagram_profile(username) — Instagram profile data
  - run_twitter_search(query) — Twitter/X presence
  - run_ph_sec_dti(company_name) — PH business registry (if Filipino)
  - run_document_search(query, filetypes=["pdf"]) — find documents mentioning the person

email:
  - run_smtp_verifier(email) — confirm mailbox exists via SMTP RCPT TO
  - run_hibp_lookup(email) — check breach exposure, reveals associated services/passwords
  - run_reverse_lookup(query, query_type="email") — map email to name, phone, other accounts
  - run_hunter_io(domain) — find colleagues at same domain
  - run_username_enumerator(username=email_local_part) — check platforms using email prefix as username
  - run_messaging_check(email=email) — check Telegram/WhatsApp/Signal linked to email

phone:
  - run_phone_osint(phone) — carrier, line type, region, caller ID
  - run_reverse_lookup(query, query_type="phone") — owner name, address
  - run_messaging_check(phone) — WhatsApp/Telegram/Signal presence
  - run_hibp_lookup(email) — some breach DBs index by phone

username / handle:
  - run_username_enumerator(username) — check existence on 9+ platforms (GitHub, Twitter, Instagram, Reddit, LinkedIn, etc.)
  - run_instagram_profile(username) — full Instagram profile data
  - run_multi_search(query="username site:github.com OR site:twitter.com") — find profiles
  - run_github_search(query=username) — GitHub repos and activity

employer / domain:
  - run_hunter_io(domain) — all emails at this domain + email pattern
  - run_apollo_search(query=company, search_type="companies") — org chart, LinkedIn URLs
  - run_whois_lookup(domain) — registrant name, email, phone
  - run_shodan_search(query="org:company") — exposed infrastructure and tech stack
  - run_opencorporates(company_name) — global business registry
  - run_glassdoor_reviews(company) — employee reviews and culture signals

address:
  - run_ph_sec_dti(company_name) — PH business registrations at address
  - run_ph_bir(company_name) — PH tax registration
  - run_opencorporates(company_name) — global company at address
  - run_google_maps_places(query) — local business ratings and reviews
  - run_multi_search(query="address" + name) — property records, public filings

photo / face:
  - run_face_search(image_url) — reverse facial recognition across web (PimEyes)
  - run_exif_extractor(file_url) — extract GPS coordinates, device info, timestamps from photos

crypto_wallet:
  - run_crypto_tracer(wallet_address) — blockchain balance, transactions, counterparties [SENTINEL]

ALWAYS RUN (sentinel checks, even if usually empty):
  - run_pep_sanctions_screen(name) — PEP/sanctions/watchlist screening
  - run_adverse_media(name) — systematic negative news (fraud/corruption/scandal)

--- INVESTIGATION PRINCIPLES ---

EXHAUSTIVE
  Do not stop at the first result. Run all applicable pivot patterns for every
  confirmed selector before moving to the next step.

CROSS-REFERENCING
  Each tool call should target a selector confirmed by a prior tool call.
  Avoid cold-calling tools with unverified selectors — it wastes budget and
  pollutes the profile with false positives.

CORROBORATION
  Two independent sources must agree before a selector is marked CONFIRMED.
  Single-source selectors are CANDIDATE and must be noted as such in the output.

FAMILY EXPANSION
  When the subject has known relatives (siblings, spouse, parents), expand the
  investigation to their selectors only when: (a) the relative is relevant to
  the investigation objective, and (b) the requester has authorized it.

SENTINEL AWARENESS
  Some targets monitor their own digital footprint. Prefer passive/read-only
  lookups (OSINT) over active probes (SMTP RCPT TO, direct social contact)
  unless the requester explicitly accepts an active investigation posture.

--- COMPLETENESS CHECKLIST ---

Before closing a person investigation, confirm at least one data point per domain:

1.  Identity           — full legal name, aliases, date of birth, nationality
2.  Digital footprint  — email addresses, usernames, social media profiles
3.  Family             — known relatives, household members, relationship status
4.  Professional       — employer(s), job title(s), skills, professional networks
5.  Financial          — business registrations, property ownership, public filings
6.  Public records     — court records, voter registration, government IDs (where public)
7.  Visual             — profile photos, tagged images, verified likeness
8.  Communication      — active phone numbers, messaging app presence
9.  Dark web / breach  — breach exposure, leaked credentials, dark web mentions
10. Online communities — forums, subreddits, Discord servers, niche platforms

Mark each domain as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
