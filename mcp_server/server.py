"""FastMCP server — pipeline node tools for Claude Code IS brain."""
from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from mcp_server.client import api_call

mcp = FastMCP("info-broker")

# ---------------------------------------------------------------------------
# Pipeline node tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def run_ddg_search(query: str, max_results: int = 10) -> str:
    """Search the web using DuckDuckGo. Returns a list of results with title, url, and snippet."""
    result = await api_call(
        "POST",
        "/v3/nodes/ddg_search/execute",
        json={"query": query, "max_results": max_results},
    )
    return json.dumps(result)


@mcp.tool()
async def run_qdrant_search(
    query: str,
    collection: str = "search_results",
    limit: int = 20,
) -> str:
    """Semantic vector search over Qdrant collections.

    collection: 'search_results' or 'linkedin_profiles'
    """
    result = await api_call(
        "POST",
        "/v3/nodes/qdrant_search/execute",
        json={"query": query, "collection": collection, "limit": limit},
    )
    return json.dumps(result)


@mcp.tool()
async def run_rss_monitor(feed_url: str, max_items: int = 20) -> str:
    """Fetch and parse an RSS/Atom feed. Returns recent items with title, url, and summary."""
    result = await api_call(
        "POST",
        "/v3/nodes/rss_monitor/execute",
        json={"feed_url": feed_url, "max_items": max_items},
    )
    return json.dumps(result)


@mcp.tool()
async def run_apify_actor(
    actor_id: str = "harvestapi~linkedin-profile-search",
    search_url: str = "",
    max_items: int = 50,
) -> str:
    """Run an Apify actor (e.g. LinkedIn scraper). Returns structured profile results."""
    result = await api_call(
        "POST",
        "/v3/nodes/apify_actor/execute",
        json={"actor_id": actor_id, "searchUrl": search_url, "max_items": max_items},
    )
    return json.dumps(result)


@mcp.tool()
async def run_ai_scoring(
    items: str,
    criteria: str,
    score_field: str = "ai_score",
    model: str = "claude-haiku-4-5-20251001",
    threshold: int = 50,
) -> str:
    """Score a list of research items against given criteria using an LLM.

    items: JSON array of item objects.
    criteria: description of what makes an item high-quality.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/ai_scoring/execute",
        json={
            "items": json.loads(items),
            "criteria": criteria,
            "score_field": score_field,
            "model": model,
            "threshold": threshold,
        },
    )
    return json.dumps(result)


@mcp.tool()
async def run_ai_provider(
    prompt: str,
    model: str = "claude-haiku-4-5-20251001",
    system_prompt: str = "",
) -> str:
    """Send a prompt to an LLM provider and return the response text."""
    result = await api_call(
        "POST",
        "/v3/nodes/ai_provider/execute",
        json={"prompt": prompt, "model": model, "system_prompt": system_prompt},
    )
    return json.dumps(result)


@mcp.tool()
async def run_summarizer(
    items: str,
    instructions: str = "Summarize the key findings.",
    model: str = "claude-haiku-4-5-20251001",
) -> str:
    """Condense a list of research items into a structured summary.

    items: JSON array of item objects.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/summarizer/execute",
        json={"items": json.loads(items), "instructions": instructions, "model": model},
    )
    return json.dumps(result)


@mcp.tool()
async def run_web_crawl(
    urls: str,
    max_pages: int = 10,
    scrape_depth: int = 1,
) -> str:
    """Crawl one or more web pages and return their parsed text content.

    urls: JSON array of URL strings.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/web_crawl/execute",
        json={"urls": json.loads(urls), "max_pages": max_pages, "scrape_depth": scrape_depth},
    )
    return json.dumps(result)


@mcp.tool()
async def search_obsidian(query: str, collection: str = "obsidian_vault", top_k: int = 10) -> str:
    """Semantic search over an Obsidian vault stored in Qdrant. Returns note chunks ranked by relevance."""
    result = await api_call(
        "POST",
        "/v3/nodes/obsidian_vault/tool-invoke",
        json={"query": query, "collection": collection, "top_k": top_k},
    )
    return json.dumps(result)


@mcp.tool()
async def search_local_files(
    query: str,
    base_path: str,
    glob_pattern: str = "**/*.{md,txt}",
    max_files: int = 50,
) -> str:
    """Search local text/document files by content. base_path must be an absolute directory path."""
    result = await api_call(
        "POST",
        "/v3/nodes/local_files/tool-invoke",
        json={
            "query": query,
            "base_path": base_path,
            "glob_pattern": glob_pattern,
            "max_files": max_files,
        },
    )
    return json.dumps(result)


@mcp.tool()
async def run_manual_scoring(items: str, criteria: str = "") -> str:
    """Queue items for manual human scoring. Returns items tagged with a pending_review flag.

    items: JSON array of item objects.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/manual_scoring/execute",
        json={"items": json.loads(items), "criteria": criteria},
    )
    return json.dumps(result)


# ---------------------------------------------------------------------------
# New plugin tools (from IS brain suggestions)
# ---------------------------------------------------------------------------


@mcp.tool()
async def run_wikipedia_api(title: str, language: str = "en") -> str:
    """Fetch a structured Wikipedia article summary and content by title.

    Returns title, extract (summary), URL, and optionally full content.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/wikipedia_api/execute",
        json={"query": title, "language": language},
    )
    return json.dumps(result)


@mcp.tool()
async def run_apollo_search(
    query: str,
    search_type: str = "people",
    filters: str = "{}",
) -> str:
    """Search Apollo.io for people or companies. Provides tech stack, intent data, and contact info.

    search_type: 'people' or 'companies'
    filters: JSON string of Apollo search filters (person_titles, organization_locations, etc.)
    """
    result = await api_call(
        "POST",
        "/v3/nodes/apollo_zoominfo/execute",
        json={"query": query, "search_type": search_type, "filters": json.loads(filters)},
    )
    return json.dumps(result)


@mcp.tool()
async def run_ph_sec_dti(company_name: str) -> str:
    """Search Philippine SEC/DTI business registry for company registration, officers, and status."""
    result = await api_call(
        "POST",
        "/v3/nodes/ph_sec_dti/execute",
        json={"query": company_name},
    )
    return json.dumps(result)


@mcp.tool()
async def run_linkedin_lookup(
    linkedin_url: str = "",
    query: str = "",
    lookup_type: str = "person",
) -> str:
    """Look up a LinkedIn profile or search for people/companies via Proxycurl.

    Provide linkedin_url for direct lookup, or query for search.
    lookup_type: 'person' or 'company'
    """
    result = await api_call(
        "POST",
        "/v3/nodes/linkedin_navigator/execute",
        json={"query": query, "linkedin_url": linkedin_url, "lookup_type": lookup_type},
    )
    return json.dumps(result)


@mcp.tool()
async def run_clutch_goodfirms(
    location: str = "Philippines",
    service_type: str = "IT Services",
    platform: str = "both",
) -> str:
    """Search Clutch and GoodFirms for IT service companies and client reviews.

    Returns company listings with ratings, review counts, and reviewer details.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/clutch_goodfirms/execute",
        json={"location": location, "service_type": service_type, "platform": platform},
    )
    return json.dumps(result)


@mcp.tool()
async def run_linkedin_profile_search(
    search_url: str = "",
    max_results: int = 10,
    location: str = "Philippines",
    title_filter: str = "",
) -> str:
    """Search LinkedIn profiles via Apify with location and title filters.

    Provide a LinkedIn search URL, or use location/title_filter to auto-build one.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/linkedin_profile/execute",
        json={"searchUrl": search_url, "maxResults": max_results, "location": location, "title_filter": title_filter},
    )
    return json.dumps(result)


@mcp.tool()
async def run_apify_actor_generic(
    actor_id: str,
    input_json: str = "{}",
    max_items: int = 50,
) -> str:
    """Run any Apify actor with arbitrary input. Generic bridge to the Apify Actor Store.

    actor_id: e.g. 'apify/web-scraper', 'harvestapi/linkedin-profile-search'
    input_json: JSON string of actor input parameters
    """
    result = await api_call(
        "POST",
        "/v3/nodes/apify_mcp/execute",
        json={"actor_id": actor_id, "input": json.loads(input_json), "max_items": max_items},
    )
    return json.dumps(result)


@mcp.tool()
async def run_web_search_fetch(
    query: str,
    max_results: int = 10,
    fetch_content: bool = False,
) -> str:
    """Web search with optional full page content fetching. Alternative to DDG search.

    If fetch_content=true, fetches and extracts text from each result URL.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/web_search_fetch/execute",
        json={"query": query, "max_results": max_results, "fetch_content": fetch_content},
    )
    return json.dumps(result)


# ---------------------------------------------------------------------------
# OSINT source tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def run_facebook_pages(
    query: str = "",
    page_urls: str = "[]",
    max_results: int = 20,
) -> str:
    """Search Facebook pages for company info, executives, and contact details.

    query: search term for FB pages. page_urls: JSON array of FB page URLs.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/facebook_pages/execute",
        json={"query": query, "page_urls": json.loads(page_urls), "max_results": max_results},
    )
    return json.dumps(result)


@mcp.tool()
async def run_twitter_search(query: str, max_results: int = 20) -> str:
    """Search Twitter/X for tweets and user profiles matching a query."""
    result = await api_call(
        "POST",
        "/v3/nodes/twitter_search/execute",
        json={"query": query, "max_results": max_results},
    )
    return json.dumps(result)


@mcp.tool()
async def run_opencorporates(company_name: str, jurisdiction: str = "") -> str:
    """Search OpenCorporates global business registry for company data."""
    result = await api_call(
        "POST",
        "/v3/nodes/opencorporates/execute",
        json={"query": company_name, "jurisdiction": jurisdiction},
    )
    return json.dumps(result)


@mcp.tool()
async def run_instagram_profile(username: str = "", query: str = "", max_results: int = 10) -> str:
    """Look up Instagram profiles or search for users. Good for executive social presence."""
    result = await api_call(
        "POST",
        "/v3/nodes/instagram_profile/execute",
        json={"username": username, "query": query, "max_results": max_results},
    )
    return json.dumps(result)


@mcp.tool()
async def run_hunter_io(domain: str = "", company: str = "", max_results: int = 10) -> str:
    """Find email addresses for a company domain via Hunter.io."""
    result = await api_call(
        "POST",
        "/v3/nodes/hunter_io/execute",
        json={"domain": domain, "company": company, "max_results": max_results},
    )
    return json.dumps(result)


@mcp.tool()
async def run_whois_lookup(domain: str) -> str:
    """WHOIS lookup for domain registration info — registrant, dates, nameservers."""
    result = await api_call(
        "POST",
        "/v3/nodes/whois_lookup/execute",
        json={"domain": domain},
    )
    return json.dumps(result)


@mcp.tool()
async def run_google_news(query: str, max_results: int = 10) -> str:
    """Search Google News for recent articles about a topic, company, or person."""
    result = await api_call(
        "POST",
        "/v3/nodes/google_news/execute",
        json={"query": query, "max_results": max_results},
    )
    return json.dumps(result)


@mcp.tool()
async def run_shodan_search(query: str = "", target: str = "", max_results: int = 10) -> str:
    """Search Shodan for internet-connected devices and services. Useful for tech infrastructure recon."""
    result = await api_call(
        "POST",
        "/v3/nodes/shodan_search/execute",
        json={"query": query, "target": target, "max_results": max_results},
    )
    return json.dumps(result)


@mcp.tool()
async def run_clutch_buyer(
    company_url: str = "",
    location: str = "Philippines",
    max_results: int = 20,
) -> str:
    """Scrape buyer-side reviews from a Clutch company profile.

    Extracts reviewer (client/buyer) info: name, title, company, industry, and project summary.
    Provide company_url for a specific profile, or leave blank to scrape top companies by location.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/clutch_buyer/execute",
        json={"company_url": company_url, "location": location, "max_results": max_results},
    )
    return json.dumps(result)


@mcp.tool()
async def run_headless_crawler(
    urls: str,
    max_pages: int = 5,
) -> str:
    """Crawl JavaScript-rendered pages via Apify's web-scraper actor.

    Use this instead of run_web_crawl for SPAs and dynamic sites where httpx returns empty pages.
    urls: JSON array of URL strings, or a single URL string.
    """
    # Accept both a JSON array and a plain URL string
    try:
        parsed_urls = json.loads(urls)
        if isinstance(parsed_urls, str):
            parsed_urls = [parsed_urls]
    except (json.JSONDecodeError, TypeError):
        parsed_urls = [urls] if urls else []

    result = await api_call(
        "POST",
        "/v3/nodes/headless_crawler/execute",
        json={"urls": parsed_urls, "max_pages": max_pages},
    )
    return json.dumps(result)


@mcp.tool()
async def run_ph_bir(
    business_name: str = "",
    tin: str = "",
) -> str:
    """Look up Philippine BIR MSME registry for a company or TIN.

    Returns registration status, RDO code, business type, and address.
    BIR's public portal is limited — the node falls back to DDG search when direct scrape fails.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/ph_bir/execute",
        json={"business_name": business_name, "tin": tin},
    )
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Financial / marketplace tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def run_stripe_marketplace(metric_type: str = "balance", date_range_days: int = 30) -> str:
    """Fetch Stripe marketplace metrics (balance, charges, customers, disputes, payouts)."""
    result = await api_call(
        "POST",
        "/v3/nodes/stripe_marketplace/execute",
        json={"metric_type": metric_type, "date_range_days": date_range_days},
    )
    return json.dumps(result, default=str)


@mcp.tool()
async def run_financial_projections(
    projection_type: str = "revenue_forecast",
    time_horizon: str = "12 months",
    items: list[dict] | None = None,
) -> str:
    """Build financial projections from research findings using LLM analysis."""
    result = await api_call(
        "POST",
        "/v3/nodes/financial_projections/execute",
        json={
            "projection_type": projection_type,
            "time_horizon": time_horizon,
            "inputs": items or [],
        },
    )
    return json.dumps(result, default=str)


# ---------------------------------------------------------------------------
# Meta tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def save_pipeline(name: str, description: str, nodes: str, edges: str) -> str:
    """Save a reusable pipeline definition to the database.

    nodes: JSON array of pipeline node objects.
    edges: JSON array of pipeline edge objects.
    """
    result = await api_call(
        "POST",
        "/v3/pipelines",
        json={
            "name": name,
            "description": description,
            "nodes": json.loads(nodes),
            "edges": json.loads(edges),
        },
    )
    return json.dumps(result)


@mcp.tool()
async def save_research_trail(
    query: str,
    entity_type: str,
    findings: str,
    trail: str,
) -> str:
    """Persist research findings and the reasoning trail to the database.

    findings: JSON array of result items.
    trail: JSON object describing the research steps taken.
    """
    result = await api_call(
        "POST",
        "/v3/research-trails",
        json={
            "query": query,
            "entity_type": entity_type,
            "findings": json.loads(findings),
            "trail": json.loads(trail),
        },
    )
    return json.dumps(result)


@mcp.tool()
async def get_past_research(query: str, limit: int = 5) -> str:
    """Find related prior research by semantic similarity to the given query."""
    result = await api_call(
        "GET",
        "/v3/research-trails",
        params={"query": query, "limit": limit},
    )
    return json.dumps(result)


@mcp.tool()
async def suggest_plugin(name: str, description: str, reason: str) -> str:
    """Suggest a new plugin or tool that should be built into info-broker.

    IMPORTANT: Before calling this, verify the capability doesn't already exist.
    This tool will check for duplicates automatically and return guidance.
    - If an exact match exists: returns the existing tool name to use instead.
    - If a partial match exists: flags it as an enhancement request.
    - Only truly unique capabilities create a new plugin request.
    """
    # Pre-check: fetch existing node types and check for overlap
    try:
        health_data = await api_call("GET", "/v3/pipelines/nodes/types/health")
        existing_nodes = {n["node_type"]: n["display_name"] for n in health_data}
    except Exception:
        existing_nodes = {}

    normalized = name.lower().replace("-", "_").replace(" ", "_")

    # Exact match — tell brain to use existing tool
    if normalized in existing_nodes:
        return json.dumps({
            "status": "duplicate",
            "message": f"Tool '{normalized}' already exists as '{existing_nodes[normalized]}'. Use run_{normalized}() instead.",
            "existing_tool": f"run_{normalized}",
        })

    # Partial match — auto-flag as enhancement
    for et, display in existing_nodes.items():
        if normalized in et or et in normalized:
            # Auto-prefix reason with ENHANCE
            enhanced_reason = reason if reason.startswith("ENHANCE:") else f"ENHANCE ({et}): {reason}"
            result = await api_call(
                "POST",
                "/v3/plugin-requests",
                json={"name": et, "description": description, "reason": enhanced_reason},
            )
            return json.dumps({
                "status": "enhancement",
                "message": f"Existing tool '{et}' ({display}) partially covers this. Flagged as enhancement request.",
                "existing_tool": f"run_{et}",
                **result,
            })

    # Keyword overlap check — compare description words against existing display names
    desc_words = set(description.lower().split())
    for et, display in existing_nodes.items():
        display_words = set(display.lower().split())
        overlap = desc_words & display_words - {"the", "and", "for", "a", "an", "of", "in", "to"}
        if len(overlap) >= 2:
            enhanced_reason = f"ENHANCE ({et}): {reason}" if not reason.startswith("ENHANCE:") else reason
            result = await api_call(
                "POST",
                "/v3/plugin-requests",
                json={"name": et, "description": description, "reason": enhanced_reason},
            )
            return json.dumps({
                "status": "enhancement",
                "message": f"Existing tool '{et}' ({display}) may cover this (overlap: {overlap}). Flagged as enhancement.",
                "existing_tool": f"run_{et}",
                **result,
            })

    # Truly unique — create new request
    result = await api_call(
        "POST",
        "/v3/plugin-requests",
        json={"name": name, "description": description, "reason": reason},
    )
    return json.dumps({"status": "new", "message": "New plugin request created.", **result})
