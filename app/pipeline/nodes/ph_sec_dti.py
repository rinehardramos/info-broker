"""PH SEC/DTI Registry enrich node — best-effort scraper for Philippine company records."""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "Authoritative source to confirm SME headcount/revenue brackets and identify registered officers"
_SEC_SEARCH_URL = "https://www.sec.gov.ph/company-search/"

# Known SEC eSPARC search endpoint (may change as the site evolves)
_SEC_ESPARC_URL = "https://esparc.sec.gov.ph/api/search/company"


class PhSecDtiNode:
    node_type = "ph_sec_dti"
    display_name = "PH SEC/DTI Registry"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "search_type": {
                "type": "string",
                "title": "Search Type",
                "enum": ["company_name", "sec_number"],
                "default": "company_name",
                "description": "Search by company name or SEC registration number",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        search_type = config.get("search_type", "company_name")
        loop = asyncio.get_running_loop()
        results: list[dict] = []

        for item in inputs:
            query = (
                item.get("company")
                or item.get("title")
                or item.get("query")
                or item.get("sec_number")
                or item.get("registration_number")
                or ""
            ).strip()
            if not query:
                log.debug("ph_sec_dti: skipping item with no query: %s", item)
                continue

            result = await loop.run_in_executor(
                None, _search_sec, search_type, query
            )
            results.extend(result)

        return results


def _search_sec(search_type: str, query: str) -> list[dict]:
    """
    Best-effort SEC scraper.

    Tries the eSPARC JSON API first; falls back to scraping the HTML search page.
    The SEC website structure is unstable — all failures return a graceful error item.
    """
    results = _try_esparc_api(query, search_type)
    if results:
        return results

    # Fallback: scrape the public search page
    return _try_html_scrape(query, search_type)


def _try_esparc_api(query: str, search_type: str) -> list[dict]:
    """Attempt the eSPARC JSON endpoint (unofficial; may break)."""
    params = (
        {"companyName": query}
        if search_type == "company_name"
        else {"companyCode": query}
    )
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            response = client.get(
                _SEC_ESPARC_URL,
                params=params,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; info-broker/1.0)",
                    "Accept": "application/json",
                },
            )
            if response.status_code != 200:
                return []
            data = response.json()
    except Exception as exc:
        log.debug("ph_sec_dti: eSPARC API unavailable: %s", exc)
        return []

    # eSPARC returns {"data": [...]} or a list directly
    items = data if isinstance(data, list) else data.get("data") or []
    if not items:
        return []

    return [_map_esparc_item(item) for item in items[:10]]


def _map_esparc_item(item: dict) -> dict:
    return {
        "company_name": item.get("companyName") or item.get("company_name", ""),
        "registration_number": item.get("companyCode") or item.get("sec_number", ""),
        "registration_date": item.get("registrationDate") or item.get("reg_date", ""),
        "status": item.get("companyStatus") or item.get("status", ""),
        "company_type": item.get("companyType") or item.get("type", ""),
        "address": item.get("address", ""),
        "source": "sec_ph",
        "reason": _REASON,
    }


def _try_html_scrape(query: str, search_type: str) -> list[dict]:
    """Scrape the SEC public search page HTML with basic string ops."""
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(
                _SEC_SEARCH_URL,
                params={"q": query},
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; info-broker/1.0)",
                    "Accept": "text/html",
                },
            )
            if response.status_code != 200:
                log.info(
                    "ph_sec_dti: SEC search returned HTTP %d for %r",
                    response.status_code,
                    query,
                )
                return [_error_item(query, f"HTTP {response.status_code}")]
            html = response.text
    except Exception as exc:
        log.warning("ph_sec_dti: failed to fetch SEC page for %r: %s", query, exc)
        return [_error_item(query, str(exc))]

    records = _parse_sec_html(html, query)
    if not records:
        log.info("ph_sec_dti: no records parsed from SEC HTML for %r", query)
        return [_error_item(query, "No records found or page structure changed")]
    return records


def _parse_sec_html(html: str, query: str) -> list[dict]:
    """
    Extract company records from SEC search HTML using basic string operations.

    The SEC website layout changes periodically; this is a best-effort extraction.
    Looks for common table row patterns containing company names and SEC numbers.
    """
    results: list[dict] = []

    # Try to find table rows — SEC search results are usually in <tr> tags
    rows = _extract_between(html, "<tr", "</tr>")
    for row in rows:
        # Skip header rows
        if "<th" in row.lower():
            continue

        cells = _extract_between(row, "<td", "</td>")
        if len(cells) < 2:
            continue

        # Strip HTML tags from each cell
        cell_texts = [_strip_tags(c).strip() for c in cells]
        # Filter out empty rows
        if not any(cell_texts):
            continue

        # Heuristic: first non-empty cell is often the company name,
        # second is often the registration number
        company_name = ""
        reg_number = ""
        status = ""

        for i, text in enumerate(cell_texts):
            if not text:
                continue
            if not company_name:
                company_name = text
            elif not reg_number and (
                text.startswith("CS") or text.startswith("SEC") or text.isdigit()
                or (len(text) > 6 and text[:2].isalpha() and text[2:].replace("-", "").isdigit())
            ):
                reg_number = text
            elif not status and text.upper() in ("ACTIVE", "REVOKED", "SUSPENDED", "DEREGISTERED"):
                status = text

        if company_name and (
            query.upper() in company_name.upper() or company_name.upper() in query.upper()
        ):
            results.append({
                "company_name": company_name,
                "registration_number": reg_number,
                "status": status,
                "source": "sec_ph",
                "reason": _REASON,
            })

    return results[:10]


def _extract_between(text: str, start_tag: str, end_tag: str) -> list[str]:
    """Extract all substrings between start_tag and end_tag (case-insensitive on tag name)."""
    results: list[str] = []
    lower = text.lower()
    start_lower = start_tag.lower()
    end_lower = end_tag.lower()
    pos = 0
    while True:
        tag_start = lower.find(start_lower, pos)
        if tag_start == -1:
            break
        # Find the closing > of the opening tag
        tag_close = lower.find(">", tag_start)
        if tag_close == -1:
            break
        content_start = tag_close + 1
        content_end = lower.find(end_lower, content_start)
        if content_end == -1:
            break
        results.append(text[content_start:content_end])
        pos = content_end + len(end_lower)
    return results


def _strip_tags(html: str) -> str:
    """Remove HTML tags from a string."""
    result = []
    in_tag = False
    for ch in html:
        if ch == "<":
            in_tag = True
        elif ch == ">":
            in_tag = False
        elif not in_tag:
            result.append(ch)
    # Collapse whitespace
    return " ".join("".join(result).split())


def _error_item(query: str, error: str) -> dict:
    return {
        "company_name": query,
        "registration_number": None,
        "status": None,
        "source": "sec_ph",
        "reason": _REASON,
        "error": error,
    }
