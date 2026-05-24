"""Strategy catalog entry: real_estate_leads.

Real-estate leads generation — find matching listings THEN enrich each listing
with listing-agent / property-owner contact info (email, phone, brokerage) AND
owner background (LLC registration, other holdings, WHOIS domain registration).

Default mode: leads_generation.
Routed from: (intent="real_estate", mode="leads_generation") via composite
             routing in app/routers/v3/preflight.py _resolve_strategy.
"""
from __future__ import annotations

from app.pipeline.catalogs.builders.research_skeleton import build_research_strategy

STRATEGY = build_research_strategy(
    id="real_estate_leads",
    default_mode="leads_generation",
    hypothesis_count="single",
    applies_to={
        "signals": [
            "properties_in", "for_rent", "for_sale", "mls_listings",
            "find_leads", "prospect_list", "contact_list", "outreach",
            "rental_leads", "real_estate_leads",
        ],
        "entity_types": ["property", "listing", "person"],
    },
    extract={
        "briefing": (
            "Parse the real-estate leads-generation brief. Extract: "
            "location (city/neighborhood/zip), price band (min/max in USD), "
            "listing type (rent vs sale), property type (house/condo/apartment), "
            "bed/bath count, and any explicit must-haves. "
            "Also note the desired output: the caller wants a contactable leads "
            "list — property + listing agent/owner email + phone + background. "
            "Emit a typed signal dict the gather phase can query against. "
            "No tool calls — pure analysis of the query text."
        ),
    },
    gather={
        "preferred_tactic_id": "leads_enrich_gather",
        "briefing": (
            "STEP 1 — Get property listings FIRST: Call apify_listings_search "
            "with the extracted location/price/type criteria. Capture address, price, "
            "listing URL, beds/baths, and listing-agent name/brokerage for EACH listing. "
            "Do NOT start enrichment until you have listings in hand.\n\n"
            "STEP 2 — Contact enrichment (per listing, once you have the list):\n"
            "  a. Agent/owner discovery: run web_search for 'listing agent OR owner "
            "     contact <address>' to surface name, brokerage, and any contact info.\n"
            "  b. Email: if a brokerage domain is known, use hunter_email_search on "
            "     that domain; also try apollo_contact with the agent name + brokerage.\n"
            "  c. Phone: validate/enrich any phone found via phone_osint; use "
            "     pipl_people for a full contact-aggregation search on the agent/owner.\n"
            "  d. Owner background: if the listing shows an owner LLC or company, "
            "     use opencorporates_owner to find its officers and registration status; "
            "     if the owner has a web domain, use whois_owner for registrant info.\n\n"
            "Run enrichment in parallel across listings where budget allows. Skip enrichment "
            "steps that clearly won't yield data (e.g. whois_owner without a domain). "
            "Budget note: apify_listings_search costs 10 RU; enrichment tools cost 1-3 RU each.\n\n"
            "IMPORTANT: The property list from STEP 1 is ALWAYS the primary output. "
            "Even if all enrichment steps fail (e.g. API keys not configured), "
            "return the full property list with address + price + listing URL. "
            "Mark missing contact fields as 'not found (or tool unavailable)' — "
            "do not drop properties because enrichment was thin."
        ),
        "gate_checks": [
            {"kind": "min_listings_returned", "params": {"min": 1}},
        ],
    },
    synthesize={
        "briefing": (
            "Assemble a contactable leads table — one row per property — with these columns:\n"
            "  - Property: address | price | listing URL | beds/baths\n"
            "  - Listing agent: name | brokerage | email | phone | LinkedIn\n"
            "  - Owner: name or LLC | email | phone (if different from agent)\n"
            "  - Owner background: LLC registration state + status | other holdings count | "
            "    WHOIS registrant | OpenCorporates officers\n"
            "  - Source URLs for every contact/background claim\n"
            "  - Confidence: HIGH (directly confirmed) / MEDIUM (cross-referenced) / "
            "    LOW (single source, unverified)\n\n"
            "CRITICAL: The property list is ALWAYS returned, even when enrichment is thin. "
            "Mark every missing contact field as 'not found (or tool unavailable)' rather "
            "than dropping the property row. Sort by price ascending. "
            "Dedupe by address. Append a 'data gaps' section listing which enrichment "
            "tools returned no data and why (key not configured, no brokerage domain, "
            "private listing, etc.)."
        ),
    },
)
