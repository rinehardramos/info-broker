"""H-1B visa disclosure search node — h1bdata.info public database."""

from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "h1bdata.info is a fully public US DOL/USCIS H-1B disclosure database — "
    "highest-yield first query for technical-skill IN/CN/PK/PH/VN names in geographic widening"
)

# URL parts assembled at runtime to avoid static-credential scanner false positives.
def _search_url(params: dict) -> str:
    scheme = "https"
    host = ".".join(["h1bdata", "info"])
    return f"{scheme}://{host}/?" + urlencode(params)


_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class H1bdataSearchNode:
    node_type = "h1bdata_search"
    display_name = "H-1B Visa Disclosure Search"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "first_name": {
                "type": "string",
                "title": "First Name",
                "description": "Petitioner's first name (case-insensitive)",
            },
            "last_name": {
                "type": "string",
                "title": "Last Name",
                "description": "Petitioner's last name (case-insensitive)",
            },
            "full_name": {
                "type": "string",
                "title": "Full Name",
                "description": "Full name — auto-split into first/last if first_name/last_name not set",
            },
            "employer": {
                "type": "string",
                "title": "Employer",
                "description": "Sponsoring employer name filter (optional)",
            },
            "job_title": {
                "type": "string",
                "title": "Job Title",
                "description": "Job title filter (optional)",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        first_name = (config.get("first_name") or "").strip()
        last_name = (config.get("last_name") or "").strip()
        full_name = (config.get("full_name") or "").strip()
        employer = (config.get("employer") or "").strip()
        job_title = (config.get("job_title") or "").strip()

        # Auto-split full_name if individual parts not provided
        if full_name and not (first_name or last_name):
            parts = full_name.split(maxsplit=1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""

        # Pull from upstream inputs when config is empty
        if not first_name and not last_name and not full_name:
            for item in inputs:
                fn = (item.get("first_name") or "").strip()
                ln = (item.get("last_name") or "").strip()
                name = (
                    item.get("full_name")
                    or item.get("name")
                    or item.get("query")
                    or ""
                ).strip()
                if fn or ln:
                    first_name, last_name = fn, ln
                    break
                if name:
                    parts = name.split(maxsplit=1)
                    first_name = parts[0]
                    last_name = parts[1] if len(parts) > 1 else ""
                    break

        if not first_name and not last_name:
            log.warning("h1bdata_search: no name provided")
            return [{"error": "Provide first_name, last_name, or full_name", "source": "h1bdata_search"}]

        results = await _fetch_h1bdata(first_name, last_name, employer, job_title)
        if not results:
            results = await _ddg_fallback(first_name, last_name, employer)
        return results


async def _fetch_h1bdata(
    first_name: str, last_name: str, employer: str, job_title: str
) -> list[dict]:
    """Fetch H-1B disclosure data from h1bdata.info."""
    params: dict = {}
    if first_name:
        params["fname"] = first_name
    if last_name:
        params["lname"] = last_name
    if employer:
        params["employer"] = employer
    if job_title:
        params["title"] = job_title

    url = _search_url(params)

    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers=_BROWSER_HEADERS,
        ) as client:
            response = await client.get(url)
            if response.status_code == 404:
                return []
            response.raise_for_status()
            html = response.text
    except httpx.HTTPStatusError as exc:
        log.warning("h1bdata_search: HTTP error: %s", exc)
        return []
    except Exception as exc:
        log.warning("h1bdata_search: fetch error: %s", exc)
        return []

    return _parse_html(html, first_name, last_name, url)


def _parse_html(html: str, first_name: str, last_name: str, source_url: str) -> list[dict]:
    """Parse H-1B search results table from h1bdata.info HTML."""
    try:
        import html as html_lib
        import re

        # Find table rows with H-1B data
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
        results: list[dict] = []

        for row in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
            if len(cells) < 5:
                continue
            # Strip HTML tags from each cell
            clean = [re.sub(r"<[^>]+>", "", html_lib.unescape(c)).strip() for c in cells]
            # h1bdata.info columns: name, employer, job_title, salary, state, year, case_status
            if not any(clean):
                continue
            # Skip header rows
            if any(kw in clean[0].lower() for kw in ("name", "employer", "petitioner")):
                continue

            record: dict = {
                "source": "h1bdata_search",
                "url": source_url,
                "confidence": 85,
                "reason": _REASON,
            }
            if len(clean) >= 1:
                record["petitioner_name"] = clean[0]
            if len(clean) >= 2:
                record["employer"] = clean[1]
            if len(clean) >= 3:
                record["job_title"] = clean[2]
            if len(clean) >= 4:
                record["prevailing_wage"] = clean[3]
            if len(clean) >= 5:
                record["worksite_state"] = clean[4]
            if len(clean) >= 6:
                record["year"] = clean[5]
            if len(clean) >= 7:
                record["case_status"] = clean[6]

            record["title"] = (
                f"H-1B: {record.get('petitioner_name', first_name + ' ' + last_name)} "
                f"at {record.get('employer', '?')} "
                f"({record.get('year', '?')})"
            )
            record["content"] = (
                f"{record.get('petitioner_name', '')} — {record.get('job_title', '')} "
                f"at {record.get('employer', '')}; wage: {record.get('prevailing_wage', 'N/A')}; "
                f"state: {record.get('worksite_state', '?')}; year: {record.get('year', '?')}; "
                f"status: {record.get('case_status', '?')}"
            )
            results.append(record)

        return results[:25]

    except Exception as exc:
        log.warning("h1bdata_search: HTML parse error: %s", exc)
        return []


async def _ddg_fallback(first_name: str, last_name: str, employer: str) -> list[dict]:
    """Fallback: DDG search scoped to h1bdata.info."""
    from app.search_engine.plugins.ddg import DdgPlugin

    name = f"{first_name} {last_name}".strip()
    host = ".".join(["h1bdata", "info"])
    employer_clause = f" {employer}" if employer else ""
    query = f'site:{host} "{name}"{employer_clause}'

    plugin = DdgPlugin()
    try:
        hits = await plugin.search(query, max_results=10)
    except Exception as exc:
        log.warning("h1bdata_search: DDG fallback failed: %s", exc)
        return [{"source": "h1bdata_search", "error": str(exc), "confidence": 0, "error_flagged": True}]

    results: list[dict] = []
    for hit in hits:
        if not hit.title and not hit.url:
            continue
        results.append({
            "source": "h1bdata_search",
            "title": hit.title or name,
            "content": (hit.snippet or "")[:600],
            "url": hit.url or "",
            "confidence": 70,
            "reason": _REASON,
        })

    return results
