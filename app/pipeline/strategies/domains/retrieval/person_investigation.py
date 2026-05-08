"""Person investigation retrieval sub-strategy module."""

CATEGORY = "retrieval"
NAME = "person_investigation"
DISPLAY_NAME = "Person Investigation"
DESCRIPTION = (
    "Comprehensive individual profiling using open-source intelligence. "
    "Builds a corroborated identity picture from public records, social media, "
    "professional networks, and digital footprint data."
)
SELECTORS = [
    "full_name",
    "alias",
    "email",
    "phone",
    "username",
    "location",
    "employer",
    "date_of_birth",
]

STRATEGY = """
=== PERSON INVESTIGATION STRATEGY ===

This strategy builds a comprehensive profile of an individual using open-source
intelligence (OSINT) sources. The goal is a corroborated identity picture covering
personal, professional, digital, and public-record dimensions. Every finding must
cite its source. Validate coverage using the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step person investigation process:

1. SEED COLLECTION — Gather all known selectors: full_name, alias, email, phone,
   username, location, employer, date_of_birth. Record each with provenance.
   Prioritize high-uniqueness selectors (email, phone, username) as anchors.
   Common names require date_of_birth or location to prevent false merges.

2. IDENTITY ANCHOR — Confirm the subject's identity across at least two independent
   sources before expanding. Cross-reference name + employer, name + location,
   or name + email to establish a confident anchor. Flag ambiguous matches.

3. PROFILE EXPANSION — Pivot from confirmed selectors to adjacent data domains:
   - Professional: employment history, education, licenses, certifications
   - Social: social media profiles, community memberships, public posts
   - Digital: domains, usernames across platforms, breach exposure
   - Geographic: current and historical addresses, property records
   - Public records: court filings, business registrations, regulatory actions

4. CORROBORATION — For each material finding, confirm via a second independent
   source. Single-source findings are labeled UNCONFIRMED. Contradictory data
   points are flagged for manual review and both versions documented.

5. COMPLETENESS AUDIT — Work through the completeness checklist. Document any
   domain as NOT ATTEMPTED with justification. Produce a source log for every
   tool called.

--- PRIORITY SELECTORS (Person Investigation) ---

Ordered by uniqueness and pivot power (highest first):

1. email          — globally near-unique; pivots to breach data, social, domains
2. phone          — high uniqueness; pivots to carrier, social, messaging profiles
3. username       — consistent handles reveal multi-platform footprint
4. full_name + date_of_birth — combined anchor; prevents false merges
5. employer       — professional pivot; opens LinkedIn, org charts, news
6. location       — geographic pivot; opens property, local records, local news
7. alias          — reveals shadow identities and historical name changes

--- KEY PIVOT PATTERNS ---

full_name:
  - ddg_search "[name] site:linkedin.com" to find professional profile
  - google_news "[name]" for news mentions, press releases, event appearances
  - ddg_search "[name] "[employer]"" to corroborate employment relationship
  - web_search_fetch LinkedIn profile URL for employment history and education

email:
  - document_search for email in breach databases (HaveIBeenPwned concept)
  - whois_lookup to find domains registered with the email
  - ddg_search "[email]" for forum posts, account registrations, public records
  - Reverse email to username pattern (pre-@ handle) for social pivots

phone:
  - ddg_search "[phone]" for public registrations, classifieds, business listings
  - Carrier lookup for geographic origin and line type (mobile/VoIP)
  - Messaging app presence check (Telegram, WhatsApp public search)

username:
  - ddg_search "[username]" site:twitter.com / reddit.com / github.com
  - Namechk-style cross-platform username enumeration
  - web_search_fetch profile pages for bio, location, linked accounts

employer:
  - linkedin_profile search for current/former employees at the company
  - sec_edgar for public company executive listings and insider filings
  - google_news "[name] [company]" for press mentions of the relationship

location:
  - ddg_search "[name] [city, state]" for local news, property, business records
  - Property record search for ownership and address history
  - Voter registration lookup where publicly available

--- COMPLETENESS CHECKLIST ---

Before closing a person investigation, confirm at least one data point per domain:

1. Identity          — full legal name, known aliases, date of birth, nationality
2. Professional      — current and historical employment, education, certifications
3. Digital Footprint — email addresses, usernames, social media profiles
4. Geographic        — current address, historical addresses, frequent locations
5. Public Records    — court records, business registrations, property ownership
6. Associates        — family members, known colleagues, business partners
7. Media Presence    — news mentions, interviews, published content
8. Breach / Dark Web — exposed credentials or mentions in data breach records

Mark each domain as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
