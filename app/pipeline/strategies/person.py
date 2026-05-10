"""Person investigation strategy module."""

ENTITY_TYPE = "person"

STRATEGY = """
=== PERSON INVESTIGATION STRATEGY ===

execution_model: seed → expand → corroborate → deduplicate → gap_fill

priority_selectors: full_name | email | phone | username | employer/domain | address | photo

--- KEY PIVOT PATTERNS ---

full_name → multi_search | linkedin_profile_search | apollo_search | email_enumerator | facebook_pages | instagram_profile | twitter_search | ph_sec_dti | document_search
email → smtp_verifier | hibp_lookup | reverse_lookup | hunter_io | username_enumerator | messaging_check
phone → phone_osint | reverse_lookup | messaging_check
username → username_enumerator | instagram_profile | multi_search("username site:github.com")
employer/domain → hunter_io | apollo_search | whois_lookup | shodan_search | opencorporates | glassdoor_reviews
address → ph_sec_dti | ph_bir | opencorporates | google_maps_places | multi_search(address+name)
photo → face_search | exif_extractor
crypto_wallet → crypto_tracer [SENTINEL]
ALWAYS: run_pep_sanctions_screen + run_adverse_media [SENTINEL — run even if expected empty]

--- INVESTIGATION PRINCIPLES ---

EXHAUSTIVE: Run all pivots for every confirmed selector before moving on.
CROSS-REF: Each tool call targets a selector confirmed by a prior call; no cold-calling unverified selectors.
CORROBORATE: 2 independent sources = CONFIRMED. 1 source = CANDIDATE (label as such).
SENTINEL: Always run pep_sanctions_screen + adverse_media regardless of subject profile.

--- COMPLETENESS CHECKLIST ---

Before closing, mark each domain CONFIRMED/PARTIAL/NOT_FOUND/NOT_ATTEMPTED:
identity | digital_footprint | family | professional | financial | public_records | visual | communication | breach | communities

--- CELEBRITY / PUBLIC FIGURE IDENTIFICATION ---

No name given (e.g. "korean girl with mole", "actor in Dyson ad"):
BRAND-FIRST: product type → dominant brand → brand ambassador → person. Search "[brand] [year] 광고모델" for Korean deals.
NATIVE-LANGUAGE: Non-Western subjects → search native language (Korean: 한국어 via Naver) before English.
DESCRIPTION-AS-FILTER: Physical traits are disambiguation filters, not primary queries — apply after brand/ambassador identified.
K-POP SOURCES: Naver News, Soompi, Allkpop, Koreaboo, OSEN, Sports Chosun.
"""
