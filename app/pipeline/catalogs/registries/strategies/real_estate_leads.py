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
            "Enrich EVERY listing with contact + owner data using FREE, creative, "
            "public-source methods. API keys are NOT required and NOT the path — they "
            "are optional accelerators. Never skip enrichment because a paid tool lacks "
            "a key; the public-source methods below ALWAYS apply.\n\n"
            "STEP 1 — Get property listings FIRST (free): Use web_search to find "
            "matching listings across Zillow / Realtor / Redfin / FSBO.com / Craigslist "
            "for the extracted location/price/type. Capture address, price, listing URL, "
            "beds/baths, and any agent name/brokerage shown. (If — and only if — an Apify "
            "key is configured, apify_listings_search can pull structured listings faster; "
            "otherwise web_search + scraping fully covers this.) Do NOT start enrichment "
            "until you have a list of concrete addresses.\n\n"
            "STEP 2 — Per-listing enrichment, lead with these FREE methods in order:\n"
            "  a. ACTUALLY FETCH THE LISTING PAGE — do not stop at search snippets. "
            "     For EACH of the listings (at least the top 10), call "
            "     listing_detail_scrape (fetch_content=true) on that listing's detail "
            "     URL/address and READ the returned page text for the agent/seller "
            "     name + phone + email + contact-form. ⚠ Writing 'contact available on "
            "     the listing page' or 'direct seller contact via the page' WITHOUT "
            "     having fetched that page is a FAILURE — fetch it and extract the "
            "     actual digits/email. If a page returns empty or blocked (common on "
            "     Zillow/Realtor SPAs), retry it with run_stealth_browser (free "
            "     undetected headless Chromium that renders JS + defeats bot "
            "     detection); only move on after that fallback also comes up empty.\n"
            "  b. PUBLIC RECORDS for the OWNER: web_search '<address> county assessor "
            "     OR recorder OR property tax owner', then property_records_lookup "
            "     (run_web_crawl) on that county-records URL to read the OWNER OF RECORD "
            "     name + mailing address. This is the authoritative, free owner identity.\n"
            "  c. DERIVE FROM SOCIAL/SEARCH: web_search the agent/owner name + brokerage "
            "     for a LinkedIn/Facebook/brokerage page; extract direct email/phone.\n"
            "  d. OWNER BACKGROUND (free): if the owner is an LLC/company, "
            "     opencorporates_owner for officers + registration; if a FSBO site or "
            "     owner domain appears, whois_owner for the registrant.\n"
            "  e. ACCELERATORS (ONLY if a key is configured): hunter_email_search, "
            "     apollo_contact, pipl_people, phone_osint. If unavailable, skip them "
            "     silently and rely on a-d — do NOT report enrichment as blocked.\n\n"
            "Triangulate across sources; prefer a value confirmed by 2+ sources. Run "
            "enrichment across listings in parallel where budget allows.\n\n"
            "IMPORTANT: The property list is ALWAYS the primary output, and EVERY listing "
            "must have a contact-enrichment ATTEMPT via the free methods above. Mark a "
            "field 'not found' only after the free public-source methods were actually "
            "tried — never use 'tool unavailable' as an excuse to skip the free path."
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
            "  - Source URLs for every contact/background claim (listing page, county "
            "    records page, social/brokerage page)\n"
            "  - Confidence: HIGH (directly confirmed / public record) / MEDIUM "
            "    (cross-referenced) / LOW (single source, unverified)\n\n"
            "CRITICAL: The property list is ALWAYS returned. Every row must reflect a real "
            "free-method enrichment attempt (listing scrape + public records + social). "
            "Mark a missing field 'not found' only after those were tried — sort by price "
            "ascending, dedupe by address. Append a 'data gaps' section noting, per field, "
            "which FREE method was tried and why it came up empty (private listing, "
            "records site blocked, owner is a privacy-protected LLC, etc.). Do NOT cite "
            "'API key not configured' as a gap — keys are optional accelerators."
        ),
    },
)
