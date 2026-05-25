"""FastMCP server — pipeline node tools for Claude Code IS brain."""
from __future__ import annotations

import json
import re

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

    urls: a JSON array of URL strings (e.g. ``["https://a.com", "https://b.com"]``),
    a single bare URL, or a comma/whitespace-separated list. All forms are
    accepted — a bare URL no longer raises a JSON decode error (see issue #110).
    """
    url_list = _parse_url_arg(urls)
    result = await api_call(
        "POST",
        "/v3/nodes/web_crawl/execute",
        json={"urls": url_list, "max_pages": max_pages, "scrape_depth": scrape_depth},
    )
    return json.dumps(result)


@mcp.tool()
async def run_stealth_browser(
    urls: str,
    wait_s: float = 2.5,
    site: str = "",
    login_url: str = "",
    username_selector: str = "",
    password_selector: str = "",
    submit_selector: str = "",
) -> str:
    """Render JS-heavy or bot-protected pages in an undetected headless Chromium
    and return their extracted text. Free — NO API key.

    Use this as the FALLBACK when run_web_crawl / run_web_search_fetch return an
    empty or blocked page on a dynamic site (e.g. a listing detail page that needs
    JavaScript). It defeats most TLS/headless bot detection. urls: a JSON array, a
    single bare URL, or a comma/space-separated list (max 12).

    AUTHENTICATED MODE — for data gated behind a login the user has an account for:
    pass `site` (the credential reference the user stored in Settings, e.g.
    "fsbo.com") + `login_url` + the form CSS selectors (`username_selector`,
    `password_selector`, `submit_selector` — inspect the login page to find them).
    The server logs in with the user's stored credential (the password is NEVER
    exposed to this tool or to you) and fetches the urls in that authenticated
    session. Only works if the user has saved a credential for that site.
    """
    url_list = _parse_url_arg(urls)
    body: dict = {"urls": url_list, "wait_s": wait_s}
    if site and login_url:
        body.update({
            "site": site,
            "login_url": login_url,
            "username_selector": username_selector,
            "password_selector": password_selector,
            "submit_selector": submit_selector,
        })
    result = await api_call(
        "POST",
        "/v3/nodes/stealth_browser/execute",
        json=body,
    )
    return json.dumps(result)


def _parse_url_arg(urls: str) -> list[str]:
    """Coerce the ``urls`` tool argument into a list of URL strings.

    The brain sometimes passes a JSON array string, but often passes a single
    bare URL or a comma/whitespace-separated list. ``json.loads`` raised
    ``JSONDecodeError`` on the bare-URL form before any HTTP call (issue #110);
    this tolerates all three.
    """
    try:
        parsed = json.loads(urls)
    except (json.JSONDecodeError, TypeError):
        parsed = None

    if isinstance(parsed, list):
        return [str(u).strip() for u in parsed if str(u).strip()]
    if isinstance(parsed, str) and parsed.strip():
        return [parsed.strip()]
    # Bare string, or comma/whitespace-separated list.
    return [u.strip() for u in re.split(r"[,\s]+", urls) if u.strip()]


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
async def run_phone_osint(phone: str, country: str = "") -> str:
    """Phone number OSINT lookup — carrier, line type, owner name, and address.

    phone: Phone number to look up (e.g. '+13125550100' or '3125550100').
    country: Optional ISO-2 country code to disambiguate (e.g. 'US').
    Use this to validate or enrich a phone number found during leads generation.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/phone_osint/execute",
        json={"phone": phone, "country": country},
    )
    return json.dumps(result)


@mcp.tool()
async def run_pipl_search(
    first_name: str = "",
    last_name: str = "",
    email: str = "",
    phone: str = "",
    city: str = "",
    state: str = "",
) -> str:
    """People search via Pipl — aggregates email, phone, address, and social profiles.

    Provide at least one identity anchor (name, email, or phone) to get results.
    Use this to find or verify contact details for listing agents and property owners.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/pipl_search/execute",
        json={
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "city": city,
            "state": state,
        },
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
async def search_memory(query: str, limit: int = 10) -> str:
    """Search info-broker's memory using multi-signal fusion.

    Combines semantic similarity, keyword matching, knowledge graph
    entities, temporal awareness, and user feedback scores.
    """
    result = await api_call("POST", "/v3/knowledge/memory/search", json={"query": query, "limit": limit})
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
async def get_past_research(query: str, limit: int = 5) -> str:
    """Find related prior research by semantic similarity to the given query."""
    result = await api_call(
        "GET",
        "/v3/research-trails",
        params={"query": query, "limit": limit},
    )
    return json.dumps(result)


@mcp.tool()
async def get_loop_working_memory(run_id: str) -> str:
    """Return the orchestrated-loop working memory for a run.

    Surfaces every analytical artifact the loop produces:
      - synthesis_summary (the brain's final natural-language answer)
      - per-turn snapshots (phase, counts, source-class mix, ACH ranking)
      - hypotheses with falsification_condition and status
      - findings with source_class + deception_risk + deception_flags
      - ACH evidence_matrix (consistent/inconsistent/neutral cells)
      - PIR coverage (entity_type, EEIs resolved, gaps)
      - decay info on cross-run priors
      - cost breakdown per phase

    Use this AFTER triggering a loop run via run_intelligent_search to read
    the analytical output. Returns 404 if the run has no working-memory
    snapshots (i.e. was the legacy single-shot path).
    """
    result = await api_call("GET", f"/v3/runs/{run_id}/working-memory")
    return json.dumps(result, default=str)


@mcp.tool()
async def list_investigation_templates() -> str:
    """List built-in investigation templates (KYC, KYB, VC DD, competitor mapping, etc.).

    Returns 6 first-party templates with id, name, description, category
    (kyc | due-diligence | market | finance | identity), and a parameter
    schema (which variables the template expects).

    Use this to discover available investigation patterns; then call
    render_investigation_template with chosen parameters to get a ready-to-fire
    research query.
    """
    result = await api_call("GET", "/v3/investigation-templates")
    return json.dumps(result, default=str)


@mcp.tool()
async def render_investigation_template(template_id: str, params: dict) -> str:
    """Render a built-in investigation template with parameters.

    template_id: One of the ids returned by list_investigation_templates
                 (e.g. "kyc-individual", "kyb-company", "vc-due-diligence").
    params:      Dict mapping parameter names to values, per the template's
                 parameter schema. Missing params render as "(not specified)".

    Returns the rendered query string ready to pass to run_intelligent_search.
    """
    # The renderer is pure server-side; fetch the template + substitute locally.
    tpl = await api_call("GET", f"/v3/investigation-templates/{template_id}")
    if not isinstance(tpl, dict):
        return json.dumps({"error": "template_not_found"})
    rendered = tpl.get("query_template", "")
    for p in tpl.get("parameters", []):
        key = p["name"]
        val = str(params.get(key) or "").strip() or "(not specified)"
        rendered = rendered.replace("{{" + key + "}}", val)
    return json.dumps({"template_id": template_id, "rendered_query": rendered})


@mcp.tool()
async def grade_finding(
    run_id: str,
    finding_id: str,
    grade: str,
    note: str = "",
) -> str:
    """Grade a finding A / B / C / D for the cross-run learning feedback loop.

    A-graded findings get auto-seeded as established_facts in future loop runs
    whose semantic search hits this finding. Grading is how the analyst tells
    the system "this fact is verified — treat it as gospel for similar future
    questions."

    grade: One of "A", "B", "C", "D".
    note:  Optional rationale (≤500 chars).
    """
    result = await api_call("POST", f"/v3/findings/{finding_id}/grade",
                            json={"run_id": run_id, "grade": grade, "note": note})
    return json.dumps(result, default=str)


@mcp.tool()
async def share_run(run_id: str, ttl_days: int = 7) -> str:
    """Generate a read-only share link for a run.

    Returns {token, url, expires_at}. The share URL exposes the loop's
    analytical artifacts (synthesis, hypotheses, findings, ACH summary) to
    anyone with the link — no auth required. Max TTL is 30 days.

    Use revoke_share_link to invalidate the link before it expires.
    """
    result = await api_call("POST", f"/v3/runs/{run_id}/share",
                            json={"ttl_days": ttl_days})
    return json.dumps(result, default=str)


@mcp.tool()
async def comment_on_hypothesis(
    run_id: str,
    hypothesis_id: str,
    body: str,
) -> str:
    """Post a comment on a hypothesis within a loop run.

    Comments persist alongside the working memory for analyst collaboration —
    teammates can leave notes, dispute the brain's conclusion, or annotate
    additional context.
    """
    result = await api_call(
        "POST",
        f"/v3/runs/{run_id}/hypotheses/{hypothesis_id}/comments",
        json={"body": body},
    )
    return json.dumps(result, default=str)


@mcp.tool()
async def list_hypothesis_comments(run_id: str, hypothesis_id: str) -> str:
    """List all comments on a specific hypothesis (oldest first)."""
    result = await api_call(
        "GET",
        f"/v3/runs/{run_id}/hypotheses/{hypothesis_id}/comments",
    )
    return json.dumps(result, default=str)


@mcp.tool()
async def get_run_cost_breakdown(run_id: str) -> str:
    """Return per-phase RU consumption for a loop run.

    Includes total_ru and by_phase breakdown (explore / test / synthesize)
    plus wallet_operations rows for auditing. Use this to track research cost
    or to debug a run that consumed unexpectedly large RU.
    """
    result = await api_call("GET", f"/v3/runs/{run_id}/cost_breakdown")
    return json.dumps(result, default=str)


# ── Replacement for the legacy run_intelligent_search ─────────────────────────

@mcp.tool()
async def run_research(query: str, max_turns: int = 6) -> str:
    """Trigger an orchestrated multi-turn research run (the loop substrate).

    Dispatches to IsLoopRunWorkflow — the same path the web UI uses. Returns
    immediately with a run_id; the loop runs asynchronously through explore →
    test → synthesize phases. Each turn has hard tool-gating enforced; the
    final turn produces a synthesis_summary, hypotheses with falsification
    conditions, an ACH evidence matrix, source-class tagging, deception flags,
    and PIR coverage.

    Workflow for the caller:
      1. response = run_research(query="...")  →  {run_id, status: "queued"}
      2. Poll get_run_status(run_id) until status="succeeded" (~1-3 min)
      3. Read the full analytical output via get_loop_working_memory(run_id)
      4. (Optional) Grade key findings with grade_finding(...) to seed
         cross-run priors for future runs on related queries.

    max_turns caps the loop length (default 6, max 12). The synthesize phase
    always runs at least once if the loop reaches it.
    """
    capped = max(2, min(12, max_turns))
    result = await api_call(
        "POST", "/v3/agent/message",
        json={"message": query, "loop_max_turns": capped},
        timeout=30.0,
    )
    run_id = result.get("job_id") or result.get("run_id") or ""
    return json.dumps({
        "run_id": run_id,
        "status": result.get("status", "queued"),
        "next_steps": [
            f"poll: get_run_status('{run_id}')",
            f"read: get_loop_working_memory('{run_id}')",
        ],
        "raw": result,
    }, default=str)
