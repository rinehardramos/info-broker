"""PH PRC License Search node — Philippine Professional Regulation Commission licensee lookup."""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "PRC records confirm professional licensure status for Philippine doctors, nurses, engineers, "
    "CPAs, teachers, and 40+ other regulated professions — authoritative identity anchor for PH persons"
)
_PRC_VERIFY_URL = "https://www.prc.gov.ph/check-your-license"
_PRC_API_URL = "https://www.prc.gov.ph/index.php/online-services/verify-license"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_PROFESSIONS = [
    "nurse", "physician", "doctor", "engineer", "accountant", "cpa",
    "teacher", "architect", "lawyer", "dentist", "pharmacist", "midwife",
    "chemist", "psychologist", "social worker", "criminologist", "physical therapist",
]


class PhPrcLicenseSearchNode:
    node_type = "ph_prc_license_search"
    display_name = "PH PRC License Search"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "title": "Full Name",
                "description": "Full name of the licensed professional to search (e.g. 'Juan dela Cruz').",
            },
            "profession": {
                "type": "string",
                "title": "Profession",
                "description": "Optional profession filter (e.g. nurse, engineer, accountant). Leave blank to search all.",
                "default": "",
            },
            "license_number": {
                "type": "string",
                "title": "License Number",
                "description": "Optional PRC license number for direct lookup.",
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
            log.warning("ph_prc_license_search: no name provided")
            return [{"error": "No name provided", "source": "ph_prc_license_search", "reason": _REASON}]

        profession = (config.get("profession") or "").strip()
        license_number = (config.get("license_number") or "").strip()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _search_prc, name, profession, license_number)


def _search_prc(name: str, profession: str, license_number: str) -> list[dict]:
    # Try the PRC verification portal first
    results = _try_prc_portal(name, profession, license_number)
    if results and not results[0].get("error"):
        return results

    # Fallback: DDG search scoped to prc.gov.ph + passer list sites
    return _ddg_fallback(name, profession)


def _try_prc_portal(name: str, profession: str, license_number: str) -> list[dict]:
    """Attempt POST to PRC verification portal."""
    payload: dict = {"fullname": name}
    if profession:
        payload["profession"] = profession
    if license_number:
        payload["license_no"] = license_number

    try:
        with httpx.Client(timeout=20.0, follow_redirects=True, headers=_BROWSER_HEADERS) as client:
            # Get CSRF token / session first
            resp = client.get(_PRC_VERIFY_URL)
            if resp.status_code != 200:
                return [_fallback_item(name, f"Portal returned HTTP {resp.status_code}")]

            # Extract CSRF if present
            csrf_match = re.search(r'name=["\']_token["\'][^>]*value=["\']([^"\']+)["\']', resp.text)
            if csrf_match:
                payload["_token"] = csrf_match.group(1)

            post_resp = client.post(_PRC_API_URL, data=payload)
            if post_resp.status_code not in (200, 302):
                return [_fallback_item(name, f"Portal POST returned HTTP {post_resp.status_code}")]

            return _parse_prc_html(post_resp.text, name)

    except httpx.TimeoutException:
        log.warning("ph_prc_license_search: portal timeout for %r", name)
        return [_fallback_item(name, "Portal request timed out")]
    except Exception as exc:
        log.warning("ph_prc_license_search: portal error for %r: %s", name, exc)
        return [_fallback_item(name, str(exc))]


def _parse_prc_html(html: str, name: str) -> list[dict]:
    """Extract license records from PRC portal HTML."""
    row_re = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
    td_re = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
    strip_tags = re.compile(r"<[^>]+>")

    results = []
    for row_m in row_re.finditer(html):
        cells = [strip_tags.sub("", td.group(1)).strip() for td in td_re.finditer(row_m.group(1))]
        if len(cells) < 3:
            continue
        # Skip header rows
        if any(h in cells[0].lower() for h in ("name", "#", "no.", "profession")):
            continue
        results.append({
            "name": cells[0] if len(cells) > 0 else name,
            "license_number": cells[1] if len(cells) > 1 else "",
            "profession": cells[2] if len(cells) > 2 else "",
            "status": cells[3] if len(cells) > 3 else "",
            "validity": cells[4] if len(cells) > 4 else "",
            "source": "ph_prc_license_search",
            "reason": _REASON,
        })

    if not results:
        return [_fallback_item(name, "No records found in portal response")]
    return results


def _ddg_fallback(name: str, profession: str) -> list[dict]:
    """Search DDG for PRC passer lists and licensee data."""
    prof_hint = f" {profession}" if profession else ""
    query = f'site:prc.gov.ph OR site:nurse.com.ph OR "PRC license" "{name}"{prof_hint}'
    log.info("ph_prc_license_search: DDG fallback for %r", name)

    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=5))
        for hit in hits:
            snippet = hit.get("body") or hit.get("snippet") or ""
            license_match = re.search(r'\b\d{7}\b', snippet)
            results.append({
                "name": name,
                "license_number": license_match.group(0) if license_match else "",
                "profession": profession,
                "status": "",
                "validity": "",
                "snippet": snippet[:300],
                "reference_url": hit.get("href") or "",
                "source": "ph_prc_license_search",
                "reason": _REASON,
            })
        return results if results else [_fallback_item(name, "No DDG results found")]
    except Exception as exc:
        log.warning("ph_prc_license_search: DDG fallback failed: %s", exc)
        return [_fallback_item(name, f"DDG fallback failed: {exc}")]


def _fallback_item(name: str, note: str) -> dict:
    return {
        "name": name,
        "license_number": "",
        "profession": "",
        "status": "",
        "validity": "",
        "source": "ph_prc_license_search",
        "reason": _REASON,
        "note": f"{note}. Manually verify at https://www.prc.gov.ph/check-your-license",
    }
