"""Gather tactic for real-estate leads generation.

Finds property listings, then enriches EACH listing with agent/owner contact
(email, phone) and owner background — leading with FREE, creative, public-source
methods so enrichment is never blocked by a missing API key:

  PRIMARY (key-free, always available):
    web_search            → find listings + agent/owner identity
    listing_detail_scrape → fetch each listing's detail page for agent/owner contact
    property_records_lookup → county assessor/recorder for the OWNER OF RECORD
    opencorporates_owner  → LLC owner officers/registration (free)
    whois_owner           → FSBO-site registrant background (free)

  OPTIONAL accelerators (used ONLY if a key is configured — never required):
    apify_listings_search → faster structured listings (needs APIFY token)
    hunter_email_search   → email-by-domain (needs Hunter key)
    apollo_contact        → people contact (needs Apollo key)
    phone_osint           → phone validation/carrier
    pipl_people           → aggregated personal profile (needs Pipl key)

Only web_search is required — listings and contacts are derived from free public
sources (direct scraping + public records) so a run with NO keys still produces
enriched leads. Paid tools merely accelerate.
"""
from app.pipeline.catalogs.schemas import Tactic


TACTIC = Tactic(
    id="leads_enrich_gather",
    phase_compatibility=["gather"],
    accepts={
        "signals": (
            "parsed real-estate leads criteria from extract (location, "
            "price_min, price_max, listing_type) plus intent to produce "
            "a contactable-leads list (agent/owner email + phone + background)"
        ),
    },
    produces=[
        # --- PRIMARY: free, key-free path (listings + per-listing enrichment) ---
        # Find listings + identities via free multi-engine search (required anchor).
        {
            "technique_id": "web_search",
            "params_template": {
                "query": "{listing_type} {location} {price_min}-{price_max} listings address agent owner contact",
                "max_results": 15,
            },
            "expect_schema": {"min_results": 1},
            "fail_modes": ["no_evidence", "tool_error"],
            "budget_ru": 2,
        },
        # Drill into EACH listing's detail page for agent/owner contact (free).
        {
            "technique_id": "listing_detail_scrape",
            "params_template": {
                "query": "{address} listing agent owner contact phone email",
                "max_results": 5,
                "fetch_content": True,
            },
            "expect_schema": {"min_results": 0},
            "fail_modes": ["no_results", "empty_page", "tool_error"],
            "budget_ru": 3,
        },
        # Owner of record from PUBLIC county records (free, authoritative).
        {
            "technique_id": "property_records_lookup",
            "params_template": {
                "urls": "{county_records_url}",
                "max_pages": 3,
            },
            "expect_schema": {"min_results": 0},
            "fail_modes": ["no_evidence", "empty_page", "blocked"],
            "budget_ru": 2,
        },
        # Property history + financial/tax records: prior owners, deed/sale
        # history, assessed-value + tax history, liens (recorder/treasurer/assessor).
        {
            "technique_id": "property_history_records",
            "params_template": {
                "urls": "{county_records_url}",
                "max_pages": 3,
            },
            "expect_schema": {"min_results": 0},
            "fail_modes": ["no_evidence", "empty_page", "blocked"],
            "budget_ru": 2,
        },
        # Owner LLC officers/registration (free).
        {
            "technique_id": "opencorporates_owner",
            "params_template": {
                "company_name": "{owner_company_name}",
                "jurisdiction": "{owner_jurisdiction}",
            },
            "expect_schema": {"min_results": 0},
            "fail_modes": ["no_evidence", "tool_error", "rate_limited"],
            "budget_ru": 3,
        },
        # FSBO-site / owner domain registrant background (free).
        {
            "technique_id": "whois_owner",
            "params_template": {"domain": "{owner_domain}"},
            "expect_schema": {"min_results": 0},
            "fail_modes": ["no_evidence", "tool_error"],
            "budget_ru": 1,
        },
        # --- OPTIONAL accelerators: used ONLY if a key is configured ---
        # Faster structured listings (needs APIFY token) — optional; web_search covers the no-key case.
        {
            "technique_id": "apify_listings_search",
            "params_template": {
                "location": "{location}",
                "min_price": "{price_min}",
                "max_price": "{price_max}",
                "listing_type": "{listing_type}",
                "max_results": 20,
            },
            "expect_schema": {"min_results": 0},
            "fail_modes": ["no_evidence", "tool_error", "schema_violation"],
            "budget_ru": 10,
        },
        # Email-by-domain (needs Hunter key) — optional accelerator.
        {
            "technique_id": "hunter_email_search",
            "params_template": {
                "domain": "{brokerage_domain}",
                "company": "{brokerage_name}",
                "max_results": 5,
            },
            "expect_schema": {"min_results": 0},
            "fail_modes": ["no_evidence", "tool_error", "rate_limited"],
            "budget_ru": 3,
        },
        # People contact (needs Apollo key) — optional accelerator.
        {
            "technique_id": "apollo_contact",
            "params_template": {
                "query": "{agent_name} {brokerage_name} {location}",
                "search_type": "people",
                "filters": "{}",
            },
            "expect_schema": {"min_results": 0},
            "fail_modes": ["no_evidence", "tool_error", "rate_limited"],
            "budget_ru": 3,
        },
        # Phone validation/carrier — optional.
        {
            "technique_id": "phone_osint",
            "params_template": {"phone": "{contact_phone}", "country": "US"},
            "expect_schema": {"min_results": 0},
            "fail_modes": ["no_evidence", "tool_error", "invalid_phone"],
            "budget_ru": 2,
        },
        # Aggregated personal profile (needs Pipl key) — optional accelerator.
        {
            "technique_id": "pipl_people",
            "params_template": {
                "first_name": "{contact_first_name}",
                "last_name": "{contact_last_name}",
                "city": "{location_city}",
                "state": "{location_state}",
            },
            "expect_schema": {"min_results": 0},
            "fail_modes": ["no_evidence", "tool_error", "insufficient_query_data"],
            "budget_ru": 3,
        },
    ],
    cost_class="expensive",
    # Free, always-healthy anchor — the tactic fires and enriches with NO keys.
    required_techniques=["web_search"],
    enforcement={"min_distinct_outputs": 1},
)
