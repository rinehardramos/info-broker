"""PH PSA Civil Registry node — Philippine Statistics Authority birth/marriage/death record search.

Note: The PSA Civil Registration System (CRS) requires authorized access for direct record retrieval.
This node performs a best-effort search via PSA's public portals and web fallback.
For official certified copies, use PSA Serbilis (serbilis.psa.gov.ph) or PSA Online (psaonline.com.ph).
"""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "PSA civil registry records (birth, marriage, death) are the gold standard for Filipino "
    "identity disambiguation — anchors name, birthdate, parents, and civil status"
)
_PSA_BASE = "https://psa.gov.ph"
_PSA_SERBILIS = "https://serbilis.psa.gov.ph"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-PH,en;q=0.9",
}

_RECORD_TYPES = {"birth", "marriage", "death"}


class PhPsaCivilRegistryNode:
    node_type = "ph_psa_civil_registry"
    display_name = "PH PSA Civil Registry"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "title": "Full Name",
                "description": "Full name to search (e.g. 'Juan dela Cruz').",
            },
            "record_type": {
                "type": "string",
                "title": "Record Type",
                "enum": ["birth", "marriage", "death"],
                "default": "birth",
                "description": "Type of civil registry record to search.",
            },
            "birth_year": {
                "type": "string",
                "title": "Birth Year",
                "description": "Optional birth year to narrow results.",
                "default": "",
            },
            "province": {
                "type": "string",
                "title": "Province / City",
                "description": "Optional province or city of registration.",
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
            log.warning("ph_psa_civil_registry: no name provided")
            return [{"error": "No name provided", "source": "ph_psa_civil_registry", "reason": _REASON}]

        record_type = (config.get("record_type") or "birth").strip().lower()
        if record_type not in _RECORD_TYPES:
            record_type = "birth"
        birth_year = (config.get("birth_year") or "").strip()
        province = (config.get("province") or "").strip()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, _search_psa, name, record_type, birth_year, province
        )


def _search_psa(name: str, record_type: str, birth_year: str, province: str) -> list[dict]:
    """Search PSA portals and fall back to DDG for civil registry records."""
    # PSA does not expose a public search API; perform a targeted web search
    return _ddg_search(name, record_type, birth_year, province)


def _ddg_search(name: str, record_type: str, birth_year: str, province: str) -> list[dict]:
    """Search DDG for PSA civil registry references and LCR (Local Civil Registry) data."""
    year_hint = f" {birth_year}" if birth_year else ""
    prov_hint = f" {province}" if province else " Philippines"
    query = (
        f'"{name}"{year_hint}{prov_hint} PSA "{record_type} certificate" OR '
        f'"civil registry" OR "LCR" site:psa.gov.ph OR site:lcr.gov.ph OR filetype:pdf'
    )
    log.info("ph_psa_civil_registry: DDG search for %r (%s)", name, record_type)

    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=5))
        for hit in hits:
            snippet = hit.get("body") or hit.get("snippet") or ""
            ref_no_match = re.search(r'\b(?:PSA|NSO|LCR)[- ]?(?:ref\.?\s*)?(\d{8,})\b', snippet, re.IGNORECASE)
            results.append({
                "name": name,
                "record_type": record_type,
                "birth_year": birth_year,
                "province": province,
                "reference_number": ref_no_match.group(0) if ref_no_match else "",
                "snippet": snippet[:400],
                "reference_url": hit.get("href") or "",
                "source": "ph_psa_civil_registry",
                "reason": _REASON,
                "note": (
                    "PSA CRS requires authorized access for direct retrieval. "
                    "Order certified copies at https://serbilis.psa.gov.ph or https://psaonline.com.ph"
                ),
            })
        return results if results else [_no_results_item(name, record_type)]
    except Exception as exc:
        log.warning("ph_psa_civil_registry: DDG search failed: %s", exc)
        return [_error_item(name, record_type, str(exc))]


def _no_results_item(name: str, record_type: str) -> dict:
    return {
        "name": name,
        "record_type": record_type,
        "birth_year": "",
        "province": "",
        "reference_number": "",
        "snippet": "",
        "reference_url": "",
        "source": "ph_psa_civil_registry",
        "reason": _REASON,
        "note": (
            "No public web results found. PSA civil records require authorized access — "
            "order at https://serbilis.psa.gov.ph or https://psaonline.com.ph"
        ),
    }


def _error_item(name: str, record_type: str, error: str) -> dict:
    return {
        "name": name,
        "record_type": record_type,
        "error": error,
        "source": "ph_psa_civil_registry",
        "reason": _REASON,
    }
