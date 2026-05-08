"""Lead generation retrieval sub-strategy module."""

CATEGORY = "retrieval"
NAME = "lead"
DISPLAY_NAME = "Lead Generation"
DESCRIPTION = (
    "Optimizes for volume and deliverability: verified email, direct phone, "
    "current employer, and personalization context. Uses SMTP verification and "
    "pattern enumeration. Stops when all 4 contact domains are confirmed."
)
SELECTORS = [
    "email",
    "phone",
    "employer",
    "full_name",
    "job_title",
    "domain",
]

STRATEGY = """
=== LEAD GENERATION STRATEGY ===

This strategy optimizes for VOLUME and DELIVERABILITY, not depth. The goal is
a clean, actionable contact record — verified email, direct phone, current
employer, and enough context to personalize outreach. Do not over-investigate;
stop when all 4 domains are CONFIRMED or budget is exhausted.

--- EXECUTION MODEL ---

A 3-step volume-oriented process:

1. SEED — Accept initial selectors: full_name, employer, job_title, domain,
   or LinkedIn URL. Do not fabricate selectors.

2. ENUMERATE & VERIFY — Generate candidate emails using pattern enumeration,
   then verify deliverability via SMTP before recording. Prioritize direct
   phone lines over switchboards.

3. ENRICH — Fill employer and social presence fields from professional
   databases. Skip breach, family, and dark-web lookups — out of scope for
   lead generation.

--- PRIORITY SELECTORS (Lead) ---

Ordered by outreach utility (highest priority first):

1. email              — deliverable address; must pass SMTP verification
2. phone              — direct line preferred over main switchboard
3. employer           — current company only; stale employers waste outreach budget
4. full_name          — anchor for deduplication and personalization

--- KEY PIVOT PATTERNS ---

full_name + employer:
  - run_apollo_zoominfo (name + company → email pattern, title, LinkedIn URL)
  - run_hunter_io (domain → employee roster with confidence scores)
  - linkedin_navigator (name + employer → canonical profile, current title)

email (candidate):
  - run_email_enumerator (generate first.last@domain, f.last@domain variants)
  - run_smtp_verifier (confirm mailbox is live; discard bouncing addresses)
  - run_hunter_io (reverse: email → employer confirmation, name)

phone:
  - run_apollo_zoominfo (direct dial extraction from professional profiles)
  - run_reverse_lookup (confirm owner name matches lead record)

domain:
  - run_hunter_io (domain search → employee roster with email patterns)
  - run_apollo_zoominfo (company search → employee list with titles)

--- LEAD QUALIFICATION ---

CONFIDENCE SCORING (simplified — skip full Admiralty scale)
  HIGH    — email SMTP-verified + name corroborated by 2 sources
  MEDIUM  — email pattern-predicted (not SMTP-verified) or single source
  LOW     — email unverified, phone only, or name-matched without corroboration

EMAIL DELIVERABILITY CLASSIFICATION
  DELIVERABLE     — SMTP RCPT TO confirmed mailbox exists
  RISKY           — catch-all domain; mailbox existence unverifiable
  UNDELIVERABLE   — hard bounce or MX lookup failed; discard

Skip Admiralty credibility/source ratings — they add latency without improving
outreach success rates.

--- HOP DEPTH ---

Maximum 1 hop from the seed selectors. Do not chain pivots beyond:
  seed → email/phone/employer → verification
Deeper investigation belongs in the PERSON strategy.

--- COMPLETENESS CHECKLIST ---

Before closing a lead record, confirm at least one data point per domain:

1. Identity          — full_name (legal or display), job_title
2. Contact info      — email (DELIVERABLE or RISKY), phone (direct line preferred)
3. Company context   — current employer name, company domain, seniority level
4. Social presence   — LinkedIn URL or one verified social profile

Mark each domain as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
