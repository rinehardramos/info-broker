"""PH COMELEC Voter Search node — Philippine voter registration lookup via COMELEC public portal."""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "COMELEC voter records anchor a Filipino person to a specific barangay/precinct — "
    "the most reliable public residency signal for PH identity disambiguation"
)
_COMELEC_VERIFY_URL = "https://voterverification.comelec.gov.ph"
_COMELEC_SEARCH_URL = "https://voterverification.comelec.gov.ph/search"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-PH,en;q=0.9",
    "Referer": _COMELEC_VERIFY_URL,
}


class PhComelecVoterSearchNode:
    node_type = "ph_comelec_voter_search"
    display_name = "PH COMELEC Voter Search"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "title": "Full Name",
                "description": "Full name of the voter to search (e.g. 'Juan dela Cruz').",
            },
            "birth_year": {
                "type": "string",
                "title": "Birth Year",
                "description": "Optional birth year to narrow results (e.g. '1985').",
                "default": "",
            },
            "locality": {
                "type": "string",
                "title": "City / Municipality",
                "description": "Optional city or municipality to narrow results.",
                "default": "",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        name = (config.get("name") or "").strip()
        if not name:
            for item in inputs:
                n = item.get("name") or item.get("full_name") or item.get("person") or ""
                if n:
                    name = str(n).strip()
                    break

        if not name:
            log.warning("ph_comelec_voter_search: no name provided")
            return [{"error": "No name provided", "source": "ph_comelec_voter_search", "reason": _REASON}]

        birth_year = (config.get("birth_year") or "").strip()
        locality = (config.get("locality") or "").strip()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _search_comelec, name, birth_year, locality)


def _search_comelec(name: str, birth_year: str, locality: str) -> list[dict]:
    results = _try_comelec_portal(name, birth_year, locality)
    if results and not results[0].get("error"):
        return results
    return _ddg_fallback(name, locality)


def _try_comelec_portal(name: str, birth_year: str, locality: str) -> list[dict]:
    """Attempt lookup via the COMELEC voter verification portal."""
    # Parse name into parts (last, first, middle)
    parts = name.strip().split()
    last_name = parts[-1] if parts else name
    first_name = parts[0] if len(parts) > 1 else ""
    middle_name = " ".join(parts[1:-1]) if len(parts) > 2 else ""

    payload: dict = {
        "lastName": last_name,
        "firstName": first_name,
        "middleName": middle_name,
    }
    if birth_year:
        payload["birthYear"] = birth_year
    if locality:
        payload["city"] = locality

    try:
        with httpx.Client(timeout=20.0, follow_redirects=True, headers=_BROWSER_HEADERS) as client:
            # Fetch landing page for cookies / CSRF
            resp = client.get(_COMELEC_VERIFY_URL)
            if resp.status_code != 200:
                return [_fallback_item(name, f"Portal returned HTTP {resp.status_code}")]

            csrf_match = re.search(
                r'name=["\'](?:_token|csrf_token|csrfmiddlewaretoken)["\'][^>]*value=["\']([^"\']+)["\']',
                resp.text,
            )
            if csrf_match:
                payload["_token"] = csrf_match.group(1)

            post_resp = client.post(_COMELEC_SEARCH_URL, data=payload)
            if post_resp.status_code not in (200, 302):
                return [_fallback_item(name, f"Portal POST returned HTTP {post_resp.status_code}")]

            return _parse_comelec_html(post_resp.text, name)

    except httpx.TimeoutException:
        log.warning("ph_comelec_voter_search: timeout for %r", name)
        return [_fallback_item(name, "Portal request timed out")]
    except Exception as exc:
        log.warning("ph_comelec_voter_search: error for %r: %s", name, exc)
        return [_fallback_item(name, str(exc))]


def _parse_comelec_html(html: str, name: str) -> list[dict]:
    """Extract voter records from COMELEC portal HTML."""
    row_re = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
    td_re = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
    strip_tags = re.compile(r"<[^>]+>")

    results = []
    for row_m in row_re.finditer(html):
        cells = [strip_tags.sub("", td.group(1)).strip() for td in td_re.finditer(row_m.group(1))]
        if len(cells) < 2:
            continue
        if any(h in cells[0].lower() for h in ("name", "#", "voter", "precinct")):
            continue
        results.append({
            "name": cells[0] if len(cells) > 0 else name,
            "precinct": cells[1] if len(cells) > 1 else "",
            "barangay": cells[2] if len(cells) > 2 else "",
            "city_municipality": cells[3] if len(cells) > 3 else "",
            "province": cells[4] if len(cells) > 4 else "",
            "registration_status": cells[5] if len(cells) > 5 else "",
            "source": "ph_comelec_voter_search",
            "reason": _REASON,
        })

    if not results:
        # Check for "no record found" message
        if re.search(r"no record|not found|no result", html, re.IGNORECASE):
            return [_fallback_item(name, "No voter record found for this name")]
        return [_fallback_item(name, "Could not parse portal response")]
    return results


def _ddg_fallback(name: str, locality: str) -> list[dict]:
    """DDG fallback — search for voter precinct data indexed online."""
    locality_hint = f" {locality}" if locality else " Philippines"
    query = f'"voter" "{name}"{locality_hint} precinct barangay site:comelec.gov.ph OR filetype:pdf'
    log.info("ph_comelec_voter_search: DDG fallback for %r", name)

    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=5))
        for hit in hits:
            snippet = hit.get("body") or hit.get("snippet") or ""
            precinct_match = re.search(r'precinct[:\s]+([^\s,<]+)', snippet, re.IGNORECASE)
            barangay_match = re.search(r'barangay[:\s]+([^\s,<]+)', snippet, re.IGNORECASE)
            results.append({
                "name": name,
                "precinct": precinct_match.group(1) if precinct_match else "",
                "barangay": barangay_match.group(1) if barangay_match else "",
                "city_municipality": locality,
                "province": "",
                "registration_status": "",
                "snippet": snippet[:300],
                "reference_url": hit.get("href") or "",
                "source": "ph_comelec_voter_search",
                "reason": _REASON,
            })
        return results if results else [_fallback_item(name, "No DDG results found")]
    except Exception as exc:
        log.warning("ph_comelec_voter_search: DDG fallback failed: %s", exc)
        return [_fallback_item(name, f"DDG fallback failed: {exc}")]


def _fallback_item(name: str, note: str) -> dict:
    return {
        "name": name,
        "precinct": "",
        "barangay": "",
        "city_municipality": "",
        "province": "",
        "registration_status": "",
        "source": "ph_comelec_voter_search",
        "reason": _REASON,
        "note": f"{note}. Manually verify at https://voterverification.comelec.gov.ph",
    }
