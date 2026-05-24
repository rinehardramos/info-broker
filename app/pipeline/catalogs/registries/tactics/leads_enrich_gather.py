"""Gather tactic for real-estate leads generation.

Pulls property listings via Apify Zillow FIRST, then enriches each listing
with agent/owner contact info (email, phone) and owner background (corporate
registration, WHOIS). Uses the full enrichment toolchain:
  web_search → agent/owner discovery
  hunter_email_search → email lookup by domain/company
  opencorporates_owner → owner LLC / corporate registration + officers
  whois_owner → domain registrant background
  apollo_contact → people contact (email/phone/LinkedIn)
  phone_osint → phone number validation and carrier info
  pipl_people → aggregated personal contact profiles

Only apify_listings_search is required for the tactic to fire; enrichment
techniques are best-effort and degrade gracefully.
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
        # Step 1: pull listings (required anchor)
        {
            "technique_id": "apify_listings_search",
            "params_template": {
                "location": "{location}",
                "min_price": "{price_min}",
                "max_price": "{price_max}",
                "listing_type": "{listing_type}",
                "max_results": 20,
            },
            "expect_schema": {"min_results": 1},
            "fail_modes": ["no_evidence", "tool_error", "schema_violation"],
            "budget_ru": 10,
        },
        # Step 2: web search for listing agent / owner identity per listing
        {
            "technique_id": "web_search",
            "params_template": {
                "query": "listing agent OR owner contact '{address}' site:zillow.com OR site:realtor.com",
                "max_results": 5,
            },
            "expect_schema": {"min_results": 0},
            "fail_modes": ["no_evidence", "tool_error"],
            "budget_ru": 2,
        },
        # Step 3: Hunter.io email lookup for brokerage / owner domain
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
        # Step 4: Apollo contact lookup for listing agent / owner
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
        # Step 5: OpenCorporates for owner LLC background
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
        # Step 6: WHOIS for owner domain registrant background
        {
            "technique_id": "whois_owner",
            "params_template": {
                "domain": "{owner_domain}",
            },
            "expect_schema": {"min_results": 0},
            "fail_modes": ["no_evidence", "tool_error"],
            "budget_ru": 1,
        },
        # Step 7: Phone OSINT to validate or enrich phone numbers found above
        {
            "technique_id": "phone_osint",
            "params_template": {
                "phone": "{contact_phone}",
                "country": "US",
            },
            "expect_schema": {"min_results": 0},
            "fail_modes": ["no_evidence", "tool_error", "invalid_phone"],
            "budget_ru": 2,
        },
        # Step 8: Pipl people search for aggregated personal contact profile
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
    required_techniques=["apify_listings_search"],
    enforcement={"min_distinct_outputs": 1},
)
