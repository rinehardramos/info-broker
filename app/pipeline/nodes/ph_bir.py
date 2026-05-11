"""PH BIR MSME Registry node — Philippine Bureau of Internal Revenue business lookup."""

from __future__ import annotations

import asyncio
import logging
import re

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "BIR registration confirms MSME status and tax compliance — "
    "critical for PH business due diligence"
)

_BIR_BASE = "https://www.bir.gov.ph"
_BIR_SEARCH_URL = "https://www.bir.gov.ph/index.php/bir-forms/registration-forms.html"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class PhBirNode:
    node_type = "ph_bir"
    display_name = "PH BIR MSME Registry"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "tin": {
                "type": "string",
                "title": "Tax Identification Number (TIN)",
                "description": "Philippine TIN, e.g. 123-456-789-000",
            },
            "business_name": {
                "type": "string",
                "title": "Business Name",
                "description": "Registered business or company name to look up",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        tin = config.get("tin", "").strip()
        business_name = config.get("business_name", "").strip()

        # Also accept tin / business_name from pipeline inputs
        loop = asyncio.get_running_loop()
        results: list[dict] = []

        # Collect queries from both config and upstream inputs
        queries: list[dict] = []
        if tin or business_name:
            queries.append({"tin": tin, "business_name": business_name})
        for item in inputs:
            q_tin = item.get("tin", "").strip()
            q_name = (
                item.get("business_name")
                or item.get("company")
                or item.get("company_name")
                or ""
            ).strip()
            if q_tin or q_name:
                queries.append({"tin": q_tin, "business_name": q_name})

        if not queries:
            return [{"error": "Provide tin or business_name", "source": "ph_bir"}]

        for q in queries:
            result = await loop.run_in_executor(None, _lookup, q["business_name"], q["tin"])
            results.extend(result)

        return results


# ---------------------------------------------------------------------------
# Lookup logic
# ---------------------------------------------------------------------------

def _lookup(business_name: str, tin: str) -> list[dict]:
    """
    Attempt BIR lookup. BIR does not expose a public search API, so we:
    1. Try a direct HTTP scrape of the BIR website search.
    2. Fall back to a DuckDuckGo search scoped to bir.gov.ph.
    All failures return graceful error items.
    """
    results = _try_bir_scrape(business_name, tin)
    if results and not results[0].get("error"):
        return results

    # Fallback: DDG search
    query = tin if tin else business_name
    if query:
        ddg_results = _try_ddg_fallback(query)
        if ddg_results:
            return ddg_results

    # Return the scrape error (or a generic unavailability notice)
    if results:
        return results
    return [_error_item(business_name, tin, "BIR public search unavailable")]


def _try_bir_scrape(business_name: str, tin: str) -> list[dict]:
    """
    Best-effort scrape of BIR's public site.

    BIR does not expose a true search API; this attempts the main site
    with a query string and parses whatever structured data is returned.
    """
    import httpx

    query = tin if tin else business_name
    if not query:
        return [_error_item(business_name, tin, "No query provided")]

    search_url = f"{_BIR_BASE}/"
    params = {"q": query, "s": query}

    log.info("ph_bir: scraping BIR site for %r", query)
    try:
        with httpx.Client(follow_redirects=True, timeout=20) as client:
            resp = client.get(search_url, params=params, headers=_BROWSER_HEADERS)
            if resp.status_code != 200:
                log.info("ph_bir: BIR site returned HTTP %d", resp.status_code)
                return [_error_item(business_name, tin, f"HTTP {resp.status_code}")]
            html = resp.text
    except Exception as exc:
        log.warning("ph_bir: failed to reach BIR site: %s", exc)
        return [_error_item(business_name, tin, str(exc))]

    return _parse_bir_html(html, business_name, tin)


def _parse_bir_html(html: str, business_name: str, tin: str) -> list[dict]:
    """
    Extract BIR business registration data from HTML.
    BIR's public pages rarely expose machine-readable registry data,
    so this is a best-effort extraction of any relevant details found.
    """
    results: list[dict] = []

    # Look for TIN patterns in the page
    tin_matches = re.findall(r'\b\d{3}-\d{3}-\d{3}(?:-\d{3})?\b', html)
    # Look for RDO codes
    rdo_matches = re.findall(r'RDO[^<]*?(?:No\.?|Code)?\s*(\d{1,3})', html, re.IGNORECASE)

    # Look for registration status keywords
    status_match = re.search(
        r'(active|inactive|deregistered|cancelled|registered)',
        html,
        re.IGNORECASE,
    )
    registration_status = status_match.group(1).title() if status_match else ""

    # Look for business type
    biz_type_match = re.search(
        r'(sole proprietor(?:ship)?|corporation|partnership|cooperative|non-?stock)',
        html,
        re.IGNORECASE,
    )
    business_type = biz_type_match.group(1).title() if biz_type_match else ""

    # Extract address from common patterns
    address_match = re.search(
        r'<(?:td|span|p)[^>]*>\s*([^<]*(?:Street|St\.|Avenue|Ave\.|Road|Rd\.|Blvd|City)[^<]*)\s*</(?:td|span|p)>',
        html,
        re.IGNORECASE,
    )
    address = address_match.group(1).strip() if address_match else ""

    # If we found anything meaningful, return a result
    found_tin = tin_matches[0] if tin_matches else tin
    found_rdo = rdo_matches[0] if rdo_matches else ""

    if found_tin or registration_status or address:
        results.append({
            "business_name": business_name,
            "tin": found_tin,
            "rdo_code": found_rdo,
            "registration_status": registration_status,
            "business_type": business_type,
            "address": address,
            "source": "ph_bir",
            "reason": _REASON,
        })
        return results

    # Nothing useful found on the page
    return [_error_item(business_name, tin, "No BIR records found on public page")]


def _try_ddg_fallback(query: str) -> list[dict]:
    """
    Fallback: search DuckDuckGo scoped to bir.gov.ph and extract any
    TIN / RDO / registration data from the snippets.
    """
    log.info("ph_bir: DDG fallback search for %r", query)
    try:
        from app.lib.ddg_fallback import search_ddg  # type: ignore
        ddg_query = f"site:bir.gov.ph {query}"
        hits = search_ddg(ddg_query, max_results=5)
    except Exception as exc:
        log.debug("ph_bir: DDG fallback failed: %s", exc)
        return []

    results: list[dict] = []
    for hit in hits:
        snippet = hit.get("snippet") or hit.get("body") or ""
        title = hit.get("title") or ""
        url = hit.get("url") or hit.get("href") or ""

        tin_match = re.search(r'\b\d{3}-\d{3}-\d{3}(?:-\d{3})?\b', snippet)
        rdo_match = re.search(r'RDO[^<]*?(?:No\.?|Code)?\s*(\d{1,3})', snippet, re.IGNORECASE)

        results.append({
            "business_name": query,
            "tin": tin_match.group(0) if tin_match else "",
            "rdo_code": rdo_match.group(1) if rdo_match else "",
            "registration_status": "",
            "business_type": "",
            "address": "",
            "snippet": snippet[:500],
            "reference_url": url,
            "source": "ph_bir",
            "reason": _REASON,
        })

    return results


def _error_item(business_name: str, tin: str, error: str) -> dict:
    return {
        "business_name": business_name,
        "tin": tin,
        "rdo_code": None,
        "registration_status": None,
        "business_type": None,
        "address": None,
        "source": "ph_bir",
        "reason": _REASON,
        "error": error,
    }
