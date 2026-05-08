"""PH FDA LTO Registry lookup node — scrapes the FDA PH verification portal."""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "FDA LTO records confirm whether a Philippine company holds a valid License to Operate "
    "for medical devices, pharmaceuticals, or health products — critical for regulatory due diligence"
)
_FDA_URL = "https://verification.fda.gov.ph"
_SEARCH_PATH = "/verification/search"


def _search_fda(company_name: str) -> list[dict]:
    """Search the FDA PH verification portal for LTO records by company name.

    Returns a list of dicts with keys: company, lto_number, status, category, address, source, reason.
    Falls back to a web_crawl suggestion when the portal is unreachable or returns no results.
    """
    params = {"q": company_name, "type": "lto"}
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(_FDA_URL + _SEARCH_PATH, params=params)
            if response.status_code != 200:
                log.warning("ph_fda_lto: unexpected status %s", response.status_code)
                return [_fallback(company_name, f"HTTP {response.status_code}")]

            rows = _parse_table(response.text)
            if not rows:
                return [_fallback(company_name, "No results returned by portal")]
            return rows

    except httpx.TimeoutException as exc:
        log.warning("ph_fda_lto: timeout searching %r: %s", company_name, exc)
        return [_fallback(company_name, "Portal request timed out")]
    except Exception as exc:
        log.warning("ph_fda_lto: error searching %r: %s", company_name, exc)
        return [_fallback(company_name, str(exc))]


def _parse_table(html: str) -> list[dict]:
    """Extract LTO records from HTML table rows.

    Looks for <tr> elements whose <td> cells follow the expected column order:
    company, lto_number, status, category, address.
    Works without BeautifulSoup using a minimal regex approach.
    """
    results: list[dict] = []

    # Extract all <tr>…</tr> blocks (non-greedy, DOTALL)
    row_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
    td_pattern = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
    tag_strip = re.compile(r"<[^>]+>")

    for row_match in row_pattern.finditer(html):
        row_html = row_match.group(1)
        cells = [
            tag_strip.sub("", td.group(1)).strip()
            for td in td_pattern.finditer(row_html)
        ]
        if len(cells) < 2:
            # Skip header rows or rows without enough data
            continue

        # Best-effort column mapping — portal layout may vary
        results.append({
            "company": cells[0] if len(cells) > 0 else "",
            "lto_number": cells[1] if len(cells) > 1 else "",
            "status": cells[2] if len(cells) > 2 else "",
            "category": cells[3] if len(cells) > 3 else "",
            "address": cells[4] if len(cells) > 4 else "",
            "source": "ph_fda_lto",
            "reason": _REASON,
        })

    return results


def _fallback(company_name: str, reason: str) -> dict:
    return {
        "company": company_name,
        "lto_number": "",
        "status": "",
        "category": "",
        "address": "",
        "source": "ph_fda_lto",
        "reason": _REASON,
        "note": (
            f"FDA portal lookup failed ({reason}). "
            "Use a web_crawl node on https://verification.fda.gov.ph as fallback."
        ),
    }


class PhFdaLtoNode:
    node_type = "ph_fda_lto"
    display_name = "PH FDA LTO Registry"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
                "title": "Company Name",
                "description": "Name of the company to search in the FDA LTO registry.",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        company_name = (config.get("company_name") or "").strip()

        # Fall back to company name extracted from upstream inputs
        if not company_name:
            for item in inputs:
                candidate = (
                    item.get("company_name")
                    or item.get("company")
                    or item.get("name")
                    or ""
                ).strip()
                if candidate:
                    company_name = candidate
                    break

        if not company_name:
            log.warning("ph_fda_lto: no company name provided")
            return [
                {
                    "error": "No company name provided",
                    "source": "ph_fda_lto",
                    "reason": _REASON,
                }
            ]

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, _search_fda, company_name)
        return results
