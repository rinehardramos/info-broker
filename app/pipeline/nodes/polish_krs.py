"""Polish KRS enrich node — Polish National Court Register (Krajowy Rejestr Sądowy) company lookup."""

from __future__ import annotations

import logging

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "Polish KRS is the authoritative national business registry — confirms legal status, directors, and company history"
_KRS_API_BASE = "https://api-krs.ms.gov.pl/api/krs"
_KRS_SEARCH_URL = "https://api-krs.ms.gov.pl/api/krs/OData/v1/PodmiotAktywny"


class PolishKrsNode:
    node_type = "polish_krs"
    display_name = "Polish KRS Registry"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "title": "Company Name or KRS Number",
                "description": "Polish company name or KRS registration number",
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 10,
                "minimum": 1,
                "maximum": 30,
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        query = (config.get("query") or "").strip()
        max_results = min(int(config.get("max_results", 10)), 30)

        queries: list[str] = [query] if query else []
        for item in inputs:
            q = (
                item.get("query")
                or item.get("company")
                or item.get("name")
                or item.get("krs_number")
                or ""
            ).strip()
            if q and q not in queries:
                queries.append(q)

        if not queries:
            log.warning("polish_krs: no query provided")
            return [{"error": "No query provided", "source": "polish_krs", "confidence": 0, "error_flagged": True}]

        results: list[dict] = []
        for q in queries:
            batch = await _search_krs(q, max_results)
            results.extend(batch)

        return results


async def _search_krs(query: str, max_results: int) -> list[dict]:
    """Search Polish KRS API or fall back to DDG search."""
    # Try the official KRS OData API first
    results = await _try_krs_api(query, max_results)
    if results and not results[0].get("error_flagged"):
        return results

    # Fallback: DDG search
    from app.search_engine.plugins.ddg import DdgPlugin

    plugin = DdgPlugin()
    ddg_query = f'site:rejestr.io OR site:krs.ms.gov.pl "{query}"'

    try:
        hits = await plugin.search(ddg_query, max_results=max_results)
    except Exception as exc:
        log.warning("polish_krs: DDG fallback failed for %r: %s", query, exc)
        return [{"query": query, "source": "polish_krs", "error": str(exc), "confidence": 0, "error_flagged": True}]

    ddg_results: list[dict] = []
    for hit in hits:
        title = hit.title or ""
        url = hit.url or ""
        snippet = hit.snippet or ""

        if not title and not url:
            continue

        ddg_results.append({
            "source": "polish_krs",
            "title": title,
            "content": snippet[:600],
            "url": url,
            "query": query,
            "confidence": 65,
            "reason": _REASON,
        })

    return ddg_results[:max_results]


async def _try_krs_api(query: str, max_results: int) -> list[dict]:
    """Attempt to query the Polish KRS OData API."""
    # Check if query looks like a KRS number (10 digits)
    import re

    is_krs_number = bool(re.match(r'^\d{10}$', query.strip()))

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            if is_krs_number:
                # Direct lookup by KRS number
                url = f"{_KRS_API_BASE}/OData/v1/PodmiotAktywny({query.zfill(10)})"
                params: dict = {}
            else:
                # Search by name
                url = _KRS_SEARCH_URL
                params = {
                    "$filter": f"startswith(Nazwa, '{query}')",
                    "$top": max_results,
                    "$select": "Numer,Nazwa,FormaWlasnosci,DataRejestracji,Adres",
                }

            response = await client.get(
                url,
                params=params,
                headers={
                    "User-Agent": "info-broker/1.0",
                    "Accept": "application/json",
                },
            )

            if response.status_code == 404:
                return []
            if response.status_code not in (200, 206):
                log.debug("polish_krs: API returned HTTP %d", response.status_code)
                return [{"query": query, "source": "polish_krs", "error": f"HTTP {response.status_code}", "confidence": 0, "error_flagged": True}]

            data = response.json()
    except Exception as exc:
        log.debug("polish_krs: API call failed: %s", exc)
        return [{"query": query, "source": "polish_krs", "error": str(exc), "confidence": 0, "error_flagged": True}]

    return _map_krs_response(data, query, is_krs_number, max_results)


def _map_krs_response(data: dict, query: str, is_krs_number: bool, max_results: int) -> list[dict]:
    """Normalise KRS API response into pipeline result items."""
    results: list[dict] = []

    if is_krs_number:
        # Single entity response
        entities = [data] if data else []
    else:
        entities = data.get("value", [])

    for entity in entities[:max_results]:
        krs_num = entity.get("Numer") or entity.get("numer") or ""
        name = entity.get("Nazwa") or entity.get("nazwa") or ""
        form = entity.get("FormaWlasnosci") or entity.get("formaWlasnosci") or ""
        reg_date = entity.get("DataRejestracji") or entity.get("dataRejestracji") or ""
        address = entity.get("Adres") or entity.get("adres") or {}
        if isinstance(address, dict):
            address_str = ", ".join(filter(None, [
                address.get("Miejscowosc") or address.get("miejscowosc") or "",
                address.get("KodPocztowy") or address.get("kodPocztowy") or "",
            ]))
        else:
            address_str = str(address)

        portal_url = f"https://ekrs.ms.gov.pl/web/wyszukiwarka-krs/strona-glowna/index.html?numer={krs_num}" if krs_num else ""

        results.append({
            "source": "polish_krs",
            "title": name or query,
            "content": f"KRS: {krs_num} | Form: {form} | Registered: {reg_date} | Address: {address_str}",
            "url": portal_url,
            "krs_number": krs_num,
            "company_name": name,
            "legal_form": form,
            "registration_date": reg_date,
            "address": address_str,
            "query": query,
            "confidence": 90,
            "reason": _REASON,
        })

    return results
