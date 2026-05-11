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
async def run_web_search(
    query: str,
    max_results: int = 15,
    engines: str = "ddg,baidu,yahoo,serper,brave",
) -> str:
    """Multi-engine web search with consensus ranking and auto-translation to English.

    Queries multiple search engines in parallel, deduplicates by URL, and ranks
    by cross-engine consensus score (higher = more engines agree it's relevant).
    Non-English results from Baidu/Yandex are automatically translated to English.

    Use this as the PRIMARY search tool for every research branch.
    For geopolitical/regional/non-Western topics always include baidu and/or yandex.

    engines: comma-separated from:
      ddg     — DuckDuckGo (free, no key)
      baidu   — Baidu (free HTML scrape, Chinese-language web)
      yahoo   — Yahoo Search (free HTML scrape, Bing-powered)
      yandex  — Yandex (free with YANDEX_API_KEY, or HTML scrape fallback; Russian/Slavic web)
      google  — Google direct HTML scrape (free fallback when no serper key)
      bing    — Bing (free HTML scrape, or API with BING_API_KEY)
      serper  — Google via Serper API (key: SERPER_API_KEY — auto-falls back to google direct)
      brave   — Brave Search (key: BRAVE_API_KEY)
      exa     — Exa neural search (key: EXA_API_KEY)
      tavily  — Tavily AI search (key: TAVILY_API_KEY)
    """
    result = await api_call(
        "POST",
        "/v3/nodes/multi_search/execute",
        json={
            "query": query,
            "max_results": max_results,
            "engines": [e.strip() for e in engines.split(",") if e.strip()],
            "translate": True,
        },
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
async def export_research(run_id: str, format: str = "pdf") -> str:
    """Export research results as PDF, CSV, or Excel file. Returns download URL."""
    result = await api_call("POST", f"/v3/exports/research/{run_id}", json={"format": format, "include_analysis": True})
    return json.dumps(result, default=str)


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
    job_titles: str = "CEO, CTO, Founder",
    locations: str = "Philippines",
    max_results: int = 10,
    scraper_mode: str = "Full",
) -> str:
    """Search LinkedIn profiles by job title and location via Apify.

    job_titles: comma-separated list of job titles (e.g. "CEO, CTO, Founder, Managing Director")
    locations: comma-separated list of locations (e.g. "Philippines, United States")
    scraper_mode: "Short", "Full", or "Full + email search"
    """
    result = await api_call(
        "POST",
        "/v3/nodes/linkedin_profile/execute",
        json={
            "job_titles": job_titles,
            "locations": locations,
            "max_results": max_results,
            "scraper_mode": scraper_mode,
        },
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


@mcp.tool()
async def run_ph_fda_lto(company_name: str) -> str:
    """Look up Philippine FDA License to Operate (LTO) records by company name.

    Returns LTO number, status (active/expired/revoked), category, and registered address.
    Covers medical device manufacturers/distributors/importers regulated by the Philippine FDA.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/ph_fda_lto/execute",
        json={"company_name": company_name},
    )
    return json.dumps(result)


@mcp.tool()
async def run_ph_prc_license_search(
    name: str, profession: str = "", license_number: str = ""
) -> str:
    """Search the Philippine PRC licensee database by name.

    Returns license number, profession, validity, and status for regulated professionals
    (nurses, engineers, doctors, CPAs, teachers, architects, and 40+ other professions).
    Falls back to DDG search of passer lists when the portal is unavailable.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/ph_prc_license_search/execute",
        json={"name": name, "profession": profession, "license_number": license_number},
    )
    return json.dumps(result)


@mcp.tool()
async def run_ph_comelec_voter_search(
    name: str, birth_year: str = "", locality: str = ""
) -> str:
    """Search the Philippine COMELEC voter registration database by name.

    Returns precinct, barangay, city/municipality, province, and registration status.
    COMELEC voter records are the most reliable public residency anchor for Filipino persons.
    Falls back to DDG search when the live portal is unavailable.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/ph_comelec_voter_search/execute",
        json={"name": name, "birth_year": birth_year, "locality": locality},
    )
    return json.dumps(result)


@mcp.tool()
async def run_ph_psa_civil_registry(
    name: str, record_type: str = "birth", birth_year: str = "", province: str = ""
) -> str:
    """Search PSA civil registry records (birth, marriage, death) by name.

    record_type: 'birth' (default), 'marriage', or 'death'.
    PSA CRS requires authorized access for direct retrieval — this returns web search results
    and references. For official certified copies, use serbilis.psa.gov.ph.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/ph_psa_civil_registry/execute",
        json={"name": name, "record_type": record_type, "birth_year": birth_year, "province": province},
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
# New pipeline node tools (wayback, ftc_foia, ibpap, polish_krs, sec_edgar,
# glassdoor_reviews, maven_gumroad)
# ---------------------------------------------------------------------------


@mcp.tool()
async def run_wayback_machine(url: str, mode: str = "snapshots", limit: int = 10) -> str:
    """Look up Wayback Machine snapshots or availability for a URL.

    mode: 'snapshots' returns a list of archived snapshots; 'diff' returns the closest snapshot.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/wayback_machine/execute",
        json={"url": url, "mode": mode, "limit": limit},
    )
    return json.dumps(result, default=str)


@mcp.tool()
async def run_ftc_foia(query: str, max_results: int = 10) -> str:
    """Search FTC enforcement actions and regulatory records for a company or individual."""
    result = await api_call(
        "POST",
        "/v3/nodes/ftc_foia/execute",
        json={"query": query, "max_results": max_results},
    )
    return json.dumps(result, default=str)


@mcp.tool()
async def run_ibpap(query: str, max_results: int = 10) -> str:
    """Search the IBPAP Philippine IT-BPM industry member directory."""
    result = await api_call(
        "POST",
        "/v3/nodes/ibpap/execute",
        json={"query": query, "max_results": max_results},
    )
    return json.dumps(result, default=str)


@mcp.tool()
async def run_polish_krs(query: str, max_results: int = 10) -> str:
    """Look up a company in the Polish National Court Register (KRS).

    query: company name or 10-digit KRS number.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/polish_krs/execute",
        json={"query": query, "max_results": max_results},
    )
    return json.dumps(result, default=str)


@mcp.tool()
async def run_sec_edgar(query: str, form_type: str = "all", max_results: int = 10) -> str:
    """Search SEC EDGAR for US public company filings.

    form_type: 10-K, 10-Q, 8-K, DEF 14A, or 'all'.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/sec_edgar/execute",
        json={"query": query, "form_type": form_type, "max_results": max_results},
    )
    return json.dumps(result, default=str)


@mcp.tool()
async def run_glassdoor_reviews(company: str, max_results: int = 10) -> str:
    """Search Glassdoor for company reviews, ratings, and employee sentiment."""
    result = await api_call(
        "POST",
        "/v3/nodes/glassdoor_reviews/execute",
        json={"company": company, "max_results": max_results},
    )
    return json.dumps(result, default=str)


@mcp.tool()
async def run_maven_gumroad(
    query: str, platform: str = "both", max_results: int = 10
) -> str:
    """Search Maven and/or Gumroad for courses and digital products.

    platform: 'maven', 'gumroad', or 'both'.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/maven_gumroad/execute",
        json={"query": query, "platform": platform, "max_results": max_results},
    )
    return json.dumps(result, default=str)


@mcp.tool()
async def run_github_search(
    query: str, search_type: str = "repositories", max_results: int = 10
) -> str:
    """Search GitHub for repositories, code snippets, or user profiles.

    search_type: 'repositories' (default), 'code', or 'users'.
    Useful for tech-stack recon, finding open-source projects, and developer OSINT.
    Requires GITHUB_TOKEN env var for higher rate limits (optional).
    """
    result = await api_call(
        "POST",
        "/v3/nodes/github_search/execute",
        json={"query": query, "search_type": search_type, "max_results": max_results},
    )
    return json.dumps(result)


@mcp.tool()
async def run_github_repo_stats(
    repo: str,
    include_commit_activity: bool = True,
    max_releases: int = 5,
) -> str:
    """Fetch GitHub repo metrics: stars, forks, weekly commit velocity, top contributors, and releases.

    repo: full repo name like 'mem0ai/mem0' or comma-separated list (e.g. 'mem0ai/mem0,letta-ai/letta').
    Returns time-series commit activity, contributor count, and release cadence — critical for OSS competitive analysis.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/github_repo_stats/execute",
        json={
            "repo": repo,
            "include_commit_activity": include_commit_activity,
            "max_releases": max_releases,
        },
    )
    return json.dumps(result)


@mcp.tool()
async def run_arxiv_search(
    query: str,
    category: str = "",
    sort_by: str = "relevance",
    max_results: int = 10,
) -> str:
    """Search arXiv preprints for AI/ML, CS, math, and science papers.

    category: optional arXiv category filter (e.g. 'cs.AI', 'cs.LG', 'stat.ML').
    sort_by: 'relevance' (default), 'lastUpdatedDate', or 'submittedDate'.
    Returns title, authors, abstract, published date, PDF link, and arxiv ID.
    Free API — no key required.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/arxiv_search/execute",
        json={
            "query": query,
            "category": category,
            "sort_by": sort_by,
            "max_results": max_results,
        },
    )
    return json.dumps(result)


@mcp.tool()
async def run_name_origin_lookup(
    first_name: str = "", last_name: str = "", full_name: str = ""
) -> str:
    """Infer nationality/origin probability from a person's name.

    Returns top countries of origin by probability, romanization artifact hints
    (e.g. Tan=Hokkien/PH, Chan=Cantonese/HK, Chen=Mandarin/CN, Tran=Vietnamese),
    and diaspora ambiguity flags. Use at the START of any person investigation,
    before committing to a locale. Powered by Forebears.io + optional Namsor API.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/name_origin_lookup/execute",
        json={"first_name": first_name, "last_name": last_name, "full_name": full_name},
    )
    return json.dumps(result)


@mcp.tool()
async def run_migration_corridor_lookup(
    origin_country: str, max_destinations: int = 10
) -> str:
    """Return top destination countries for a given origin country by migrant stock.

    Uses IOM Migration Data Portal API with hardcoded corridor fallback.
    Returns destination countries ranked by migrant population with search tips
    specific to each destination (h1bdata.info for US, Gazette for UK, DMW for PH, etc.).
    Use as Step 1 of geographic widening when initial locale search is low-yield.

    Key corridors: PH→US/UAE/SA/CA/AU/SG; IN→UAE/SA/US/UK/CA; VN→US/JP/AU/KR;
    CN→US/HK/SG/CA/AU; PK→SA/UAE/UK/US; NG→US/UK/CA; MX→US/CA/ES.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/migration_corridor_lookup/execute",
        json={"origin_country": origin_country, "max_destinations": max_destinations},
    )
    return json.dumps(result)


@mcp.tool()
async def run_h1bdata_search(
    first_name: str = "", last_name: str = "", full_name: str = "",
    employer: str = "", job_title: str = "",
) -> str:
    """Search the H-1B visa disclosure database for a person's US employment history.

    H-1B data is publicly filed with US DOL/USCIS. Returns employer, job title,
    salary, location, and year for each H-1B filing. Highest-yield first query
    for any technical-skill IN/CN/PK/PH/VN name in geographic widening.
    No API key required — fully public data.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/h1bdata_search/execute",
        json={"first_name": first_name, "last_name": last_name,
              "full_name": full_name, "employer": employer, "job_title": job_title},
    )
    return json.dumps(result)


@mcp.tool()
async def run_icij_search(query: str, jurisdiction: str = "", dataset: str = "") -> str:
    """Search the ICIJ Offshore Leaks database for entities in offshore structures.

    Covers 810K+ entities from Panama Papers, Pandora Papers, Paradise Papers,
    FinCEN Files, and Offshore Leaks. Returns entity name, jurisdiction, linked
    companies/individuals, and source dataset.
    Use for beneficial ownership tracing and offshore structure investigations.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/icij_search/execute",
        json={"query": query, "jurisdiction": jurisdiction, "dataset": dataset},
    )
    return json.dumps(result)


@mcp.tool()
async def run_intelligent_search(
    query: str,
    max_depth: int = 3,
    max_branches: int = 12,
) -> str:
    """Run the full Intelligent Search (IS) brain on a query.

    This executes the complete recursive investigation loop with:
    - Multi-engine web search + past research retrieval
    - Entity-type detection and strategy selection
    - Meta-strategy injection (geographic widening, financial trail, ACH, etc.)
    - Recursive branch exploration up to max_depth
    - Findings fusion and confidence scoring

    Returns a structured JSON result with summary, findings, investigation tree,
    suggested pipeline, and gaps.

    This is the highest-capability research tool — use it for complex queries
    that require multi-step investigation rather than single-tool lookups.
    For simple factual lookups, prefer run_web_search + run_web_crawl.
    """
    result = await api_call(
        "POST",
        "/v3/agent/research/sync",
        json={"query": query, "max_depth": max_depth, "max_branches": max_branches},
        timeout=300.0,
    )
    return json.dumps(result, default=str)


# ---------------------------------------------------------------------------
# Research run access (knowledge base reference)
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_memory(query: str, limit: int = 10) -> str:
    """Search info-broker's memory using multi-signal fusion.

    Combines semantic similarity, keyword matching, knowledge graph
    entities, temporal awareness, and user feedback scores.
    """
    result = await api_call("POST", "/v3/knowledge/memory/search", json={"query": query, "limit": limit})
    return json.dumps(result, default=str)


@mcp.tool()
async def curate_knowledge() -> str:
    """Get knowledge graph curation status -- contradictions and stale observations.

    Returns total counts, unresolved contradictions, and active stale flags.
    Use this to assess knowledge graph quality before research.
    """
    stats = await api_call("GET", "/v3/knowledge/curation/stats")
    contradictions = await api_call("GET", "/v3/knowledge/contradictions", params={"status": "needs_review", "limit": 10})
    stale = await api_call("GET", "/v3/knowledge/stale", params={"status": "stale", "limit": 10})
    result = {
        **(stats if isinstance(stats, dict) else {}),
        "recent_contradictions": contradictions[:10] if isinstance(contradictions, list) else [],
        "recent_stale": stale[:10] if isinstance(stale, list) else [],
    }
    return json.dumps(result, default=str)


@mcp.tool()
async def ask_user(question: str, run_id: str, options: list[str] = []) -> str:
    """Ask the user a clarifying question before proceeding with research.

    Use this when the research query is ambiguous or multi-faceted.
    The question is displayed in the chat UI. If options are provided,
    they appear as quick-reply buttons. The tool blocks until the user responds.

    Args:
        question: The clarifying question to ask
        run_id: The current research run ID (from your context)
        options: Optional list of suggested answers shown as buttons
    """
    result = await api_call("POST", "/v3/agent/brain-question", json={
        "run_id": run_id,
        "question": question,
        "options": options,
        "uid": "",  # uid is resolved server-side from session
    })
    return result.get("answer", "") if isinstance(result, dict) else str(result)


@mcp.tool()
async def query_uploaded_data(query: str, filename: str = "", source_id: str = "", limit: int = 20) -> str:
    """Search through uploaded file data (CSV, Excel, PDF, DOCX, TXT).

    Use this to find specific rows, sections, or content within files the user has uploaded.
    The data has been indexed and you can search by any column value, keyword, or phrase.
    IMPORTANT: Always pass the filename to scope results to a single file.

    Args:
        query: What to search for (e.g., "distributors in Manila", "Class III devices")
        filename: Filter to a specific file (e.g., "MEDICAL_DEVICE_DISTRIBUTOR.xls")
        source_id: Filter by source upload ID (alternative to filename)
        limit: Max results to return (default 20)
    """
    result = await api_call("POST", "/v3/sources/query", json={
        "query": query,
        "filename": filename,
        "source_id": source_id,
        "limit": limit,
    })
    if isinstance(result, list) and result:
        return json.dumps(result, default=str)
    return json.dumps({"message": "No matching data found in uploaded files", "query": query, "filename": filename}, default=str)


@mcp.tool()
async def get_research_by_id(run_id: str) -> str:
    """Fetch a specific research trail by its run ID.

    Returns the full research data: query, findings, trail tree, entity_type,
    tool_calls count, and suggested_pipeline. Use this to access prior research
    results by their reference ID.
    """
    result = await api_call("GET", f"/v3/research-trails/{run_id}")
    return json.dumps(result, default=str)


@mcp.tool()
async def get_run_status(run_id: str) -> str:
    """Get the status and metadata of a pipeline/research run by ID.

    Returns: status, query, trigger_type, error_message, started_at, finished_at.
    """
    result = await api_call("GET", f"/v3/pipelines/runs/{run_id}")
    return json.dumps(result, default=str)


@mcp.tool()
async def list_recent_runs(limit: int = 10) -> str:
    """List recent research and pipeline runs with their IDs, queries, and status.

    Use this to find run IDs for further lookup with get_research_by_id or get_run_status.
    """
    result = await api_call("GET", "/v3/pipelines/runs/all", params={"limit": limit})
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

    # Try auto-create if enabled
    try:
        from app.pipeline.auto_create import auto_create_plugin
        auto_result = await auto_create_plugin(normalized, description, reason)
        if auto_result.get("status") == "auto_created":
            return json.dumps({
                "status": "auto_created",
                "tool_name": auto_result["tool_name"],
                "message": f"Plugin '{normalized}' was auto-created and is now available as {auto_result['tool_name']}. You can call it immediately.",
            })
    except Exception as exc:
        log.warning("Auto-create attempt failed (non-fatal): %s", exc)
        # Fall through to standard "new" flow

    # Truly unique — create new request
    result = await api_call(
        "POST",
        "/v3/plugin-requests",
        json={"name": name, "description": description, "reason": reason},
    )
    return json.dumps({"status": "new", "message": "New plugin request created.", **result})


@mcp.tool()
async def log_cycle(
    pir: str,
    hypotheses: list[str],
    cycle_id: str = "cycle_1",
    parent_cycle_id: str = "",
) -> str:
    """
    Declare the start of an INVESTIGATE cycle. Call this before any BROADEN searches.

    pir: The specific question this cycle answers (one sentence).
    hypotheses: Competing hypotheses for this PIR, e.g. ["H1: PH-based person", "H2: EU-migrant", "H3: alias abroad", "H_last: no public trace"].
    cycle_id: Unique ID for this cycle, e.g. "cycle_1", "cycle_2", "cycle_1_child_1".
    parent_cycle_id: ID of the parent cycle if this is a child PIR, else empty string.
    """
    return json.dumps({"logged": True, "cycle_id": cycle_id or "cycle_1"})
