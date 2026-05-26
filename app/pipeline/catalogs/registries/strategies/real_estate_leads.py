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
            "STEP 1 — Get listings FIRST (free), preferring SOFT sources over HARD ones.\n"
            "  SOFT (low bot-defense, contacts often EXPOSED — start here): Craigslist "
            "  real-estate 'by-owner' (e.g. <region>.craigslist.org/search/reo), FSBO.com, "
            "  ForSaleByOwner.com, Houzeo, Facebook Marketplace, and local/regional MLS-IDX "
            "  + brokerage sites. These render cleanly and frequently expose the seller's "
            "  phone/email directly.\n"
            "  HARD (heavy anti-bot — seller contact is gated behind login/forms; use only "
            "  via run_stealth_browser, expect challenges, and do NOT depend on them for "
            "  contact): Zillow (PerimeterX 'press & hold'), Realtor.com, Redfin.\n"
            "  Use web_search to find matching listings on the SOFT sources first; capture "
            "  address, price, listing URL, beds/baths, agent/seller name. (Apify only if a "
            "  key is configured.) Do NOT start enrichment until you have concrete addresses.\n\n"
            "STEP 2 — Per-listing enrichment, lead with these FREE methods in order:\n"
            "  a. SOFT-SOURCE POSTS CARRY CONTACT DIRECTLY — get it from the post itself. "
            "     For Craigslist by-owner posts, render the post page with run_stealth_browser "
            "     and extract the phone in the body AND the CL reply/relay email (the 'reply' "
            "     button reveals a @reply.craigslist.org relay or the poster's email). "
            "     FSBO.com / ForSaleByOwner posts similarly expose a seller phone or contact "
            "     form. This is where free SELLER contact actually lives — prioritize it.\n"
            "  b. FETCH THE LISTING DETAIL PAGE — for each listing call listing_detail_scrape "
            "     (fetch_content=true) and READ the text for agent/seller name + phone + "
            "     email. ⚠ Writing 'contact available on the page' WITHOUT fetching it is a "
            "     FAILURE. If empty/blocked, retry with run_stealth_browser. NOTE: Zillow/"
            "     Realtor detail pages gate seller contact behind login — don't burn effort "
            "     there; pivot to the soft sources in (a).\n"
            "  c. PUBLIC RECORDS for the OWNER (authoritative, free, STRUCTURED): prefer the "
            "     county's OPEN-DATA API over scraping assessor HTML. web_search '<county> "
            "     parcel OR assessor open data API' to find either a Socrata endpoint "
            "     (datacatalog.<county>.gov / data.<county>.gov — query like "
            "     '?property_address=<ADDR>' returns JSON) or an ArcGIS REST parcel layer "
            "     (services.arcgis.com/.../query?where=...&f=json). Fetch it with "
            "     run_web_search_fetch / run_web_crawl (both handle JSON) and read the OWNER "
            "     name + MAILING ADDRESS. These return clean structured data with no "
            "     bot-blocking (e.g. Cook County's datacatalog.cookcountyil.gov parcel "
            "     dataset returns property_address + mailing_address as JSON). Only if no "
            "     open-data API exists, fall back to the assessor parcel-search page "
            "     (render via run_stealth_browser). Owner phone is rarely in records, but "
            "     the NAME + mailing address are the authoritative free owner identity.\n"
            "     ALSO pull PROPERTY HISTORY + FINANCIALS from the same official records via "
            "     property_history_records (recorder-of-deeds / treasurer / assessor, or the "
            "     listing's price-history): (i) ownership/deed history → PREVIOUS OWNERS + "
            "     transfer dates + sale prices; (ii) TAX records → assessed-value history + "
            "     tax-bill amounts + any delinquency; (iii) financial signals → recorded "
            "     mortgages/liens + last sale price. These are primary-official records — "
            "     they strengthen owner background and the lead's value picture.\n"
            "  d. DERIVE FROM SOCIAL/SEARCH: web_search the agent/owner name + brokerage for "
            "     a LinkedIn/Facebook/brokerage page; extract direct email/phone.\n"
            "  e. OWNER BACKGROUND (free): LLC owner → opencorporates_owner for officers + "
            "     registration; FSBO site / owner domain → whois_owner for the registrant.\n"
            "  f. ACCELERATORS (ONLY if a key is configured): hunter_email_search, "
            "     apollo_contact, pipl_people, phone_osint. If unavailable, skip silently and "
            "     rely on a-e — do NOT report enrichment as blocked.\n\n"
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
            "  - Property history: previous owner(s) | last sale date + price | deed/transfer history\n"
            "  - Financial/tax: assessed value (latest + trend) | annual tax + any delinquency | "
            "    recorded mortgages/liens\n"
            "  - Source URLs for every contact/background/records claim (listing page, county "
            "    records/open-data page, social/brokerage page)\n"
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
