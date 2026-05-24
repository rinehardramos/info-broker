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
            "Execute a two-stage enrichment pipeline:\n\n"
            "STAGE 1 — Listings: Query Zillow/MLS sources via apify_listings_search "
            "for properties matching the extracted criteria. For each listing capture: "
            "URL, address, price, beds/baths, sqft, listing type, and listing agent "
            "name/brokerage if shown.\n\n"
            "STAGE 2 — Contact enrichment (per listing):\n"
            "  a. Agent/owner discovery: run web_search for 'listing agent OR owner "
            "     contact <address>' to surface name, brokerage, and any contact info.\n"
            "  b. Email: if a brokerage domain is known, use hunter_email_search on "
            "     that domain; also try apollo_contact with the agent name + brokerage.\n"
            "  c. Phone: validate/enrich any phone found via phone_osint; use "
            "     pipl_people for a full contact-aggregation search on the agent/owner.\n"
            "  d. Owner background: if the listing shows an owner LLC or company, "
            "     use opencorporates_owner to find its officers and registration status; "
            "     if the owner has a web domain, use whois_owner for registrant info.\n\n"
            "Run stage 2 in parallel across listings where budget allows. Skip enrichment "
            "steps that clearly won't yield data (e.g. whois_owner without a domain). "
            "Budget note: apify_listings_search costs 10 RU; enrichment tools cost 1-3 RU each."
        ),
        "gate_checks": [
            {"kind": "min_listings_returned", "params": {"min": 1}},
        ],
    },
    synthesize={
        "briefing": (
            "Produce a contactable leads table, one row per listing, with columns:\n"
            "  - Property: address, price, beds/baths, listing URL\n"
            "  - Listing agent: name, brokerage, email, phone, LinkedIn (if found)\n"
            "  - Owner: name or LLC, email, phone (if different from agent)\n"
            "  - Owner background: LLC registration state + status, other holdings count, "
            "    WHOIS registrant (if applicable), OpenCorporates officers\n"
            "  - Source URLs for every contact/background claim\n"
            "  - Confidence: HIGH (directly confirmed) / MEDIUM (cross-referenced) / "
            "    LOW (single source, unverified)\n\n"
            "Dedupe by address. Mark rows where contact enrichment found nothing as "
            "'no contact found' rather than dropping them. Sort by price ascending. "
            "Append a 'data gaps' section listing listings that could not be enriched "
            "and why (no brokerage domain, private listing, etc.)."
        ),
    },
)
