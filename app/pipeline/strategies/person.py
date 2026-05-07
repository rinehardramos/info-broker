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

full_name:
  - linkedin_navigator (name + employer for disambiguation)
  - apollo_zoominfo (name + company for professional contact data)
  - clutch_goodfirms (name + role for business affiliations)
  - public records search (court, property, voter registration)

email:
  - run_smtp_verifier (confirm mailbox is live before pivoting)
  - run_hibp_lookup (check breach membership; reveals associated usernames/phones)
  - run_reverse_lookup (map email to name, phone, address where available)
  - hunter_io (domain → employee roster; employee email → employer confirmation)
  - social registration probe (GitHub, LinkedIn, Facebook by email)

phone:
  - run_reverse_lookup (carrier, owner name, location)
  - truecaller / sync.me scrape (crowdsourced name mapping)
  - WhatsApp / Telegram profile probe (avatar, display name, about)
  - run_hibp_lookup with phone normalization (some breach DBs index by phone)

username / handle:
  - sherlock / whatsmyname style scan (cross-platform presence map)
  - apify_actor (Instagram, Twitter/X, Reddit, TikTok profile scrape)
  - wayback_machine lookup (historical username activity)
  - github profile → repos → commit email extraction

employer / domain:
  - hunter_io domain search (employee roster)
  - apollo_zoominfo company search (org chart, LinkedIn profiles)
  - whois_lookup (domain registrant → personal email/phone)
  - shodan_search (exposed infrastructure tied to domain)

address:
  - ph_bir / ph_sec_dti (PH-specific: business registrations at address)
  - opencorporates (global: company registered at address)
  - google_maps / street_view scrape (confirm physical presence)
  - property records (owner name, purchase price, mortgage)

photo / face:
  - reverse image search (Google, Yandex, TinEye)
  - facial recognition pivot (when legally permissible in jurisdiction)
  - EXIF metadata extraction (GPS, device, timestamp)

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
