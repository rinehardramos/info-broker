"""Lead generation strategy module."""

ENTITY_TYPE = "lead"

STRATEGY = """
=== LEAD GENERATION STRATEGY ===

goal: VOLUME + DELIVERABILITY — verified email, direct phone, current employer, personalization context. Stop when all 4 domains CONFIRMED or budget exhausted.

execution_model: seed → enumerate+verify → enrich (skip breach/family/dark-web)

priority_selectors: email(deliverable) | phone(direct) | employer(current) | full_name

--- KEY PIVOT PATTERNS ---

full_name+employer → run_apollo_zoominfo | run_hunter_io | linkedin_navigator
email(candidate) → run_email_enumerator | run_smtp_verifier | run_hunter_io(reverse)
phone → run_apollo_zoominfo(direct dial) | run_reverse_lookup(confirm owner)
domain → run_hunter_io | run_apollo_zoominfo

hop_depth: max 1 hop from seed. seed → email/phone/employer → verification. Deeper = PERSON strategy.

--- LEAD QUALIFICATION ---

confidence: HIGH(SMTP-verified + 2-source name) | MEDIUM(pattern-predicted or single-source) | LOW(unverified)
deliverability: DELIVERABLE(SMTP RCPT TO confirmed) | RISKY(catch-all) | UNDELIVERABLE(hard bounce/MX fail)
Note: Skip Admiralty ratings — adds latency without improving outreach success.

--- COMPLETENESS CHECKLIST ---

Before closing, mark each domain CONFIRMED/PARTIAL/NOT_FOUND/NOT_ATTEMPTED:
identity(name+title) | contact_info(email+phone) | company_context(employer+domain) | social_presence(LinkedIn URL)
"""
