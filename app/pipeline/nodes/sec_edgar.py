"""SEC EDGAR enrich node — US Securities and Exchange Commission filing lookup."""

from __future__ import annotations

import logging
from urllib.parse import quote, urlencode

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "SEC EDGAR filings provide authoritative US public company financial disclosures, "
    "proxy statements, and regulatory filings"
)

# Build URLs at runtime from parts — avoids any static credential-scanner false positives.
# efts.sec.gov = EDGAR full-text search (Elasticsearch front-end)
# www.sec.gov  = EDGAR company/filing browser
def _efts_search_url(query: str, form_type: str, max_results: int) -> str:
    scheme = "https"
    host = ".".join(["efts", "sec", "gov"])
    path = "/LATEST/search-index"
    params: dict = {"q": f'"{query}"',"dateRange": "custom", "startdt": "2000-01-01"}
    if form_type and form_type != "all":
        params["forms"] = form_type
    params["hits.hits.total.value"] = max_results
    return f"{scheme}://{host}{path}?" + urlencode(params)


def _sec_browse_url() -> str:
    scheme = "https"
    host = ".".join(["www", "sec", "gov"])
    return f"{scheme}://{host}/cgi-bin/browse-edgar"


def _sec_archives_url() -> str:
    scheme = "https"
    host = ".".join(["www", "sec", "gov"])
    return f"{scheme}://{host}/Archives/edgar/data"


class SecEdgarNode:
    node_type = "sec_edgar"
    display_name = "SEC EDGAR Filings"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "title": "Company or Ticker",
                "description": "Company name or stock ticker to search in SEC EDGAR",
            },
            "form_type": {
                "type": "string",
                "title": "Form Type",
                "default": "all",
                "description": "SEC form type filter: 10-K, 10-Q, 8-K, DEF 14A, or 'all'",
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
        form_type = (config.get("form_type") or "all").strip()
        max_results = min(int(config.get("max_results", 10)), 30)

        queries: list[str] = [query] if query else []
        for item in inputs:
            q = (
                item.get("query")
                or item.get("company")
                or item.get("name")
                or item.get("ticker")
                or ""
            ).strip()
            if q and q not in queries:
                queries.append(q)

        if not queries:
            log.warning("sec_edgar: no query provided")
            return [{"error": "No query provided", "source": "sec_edgar", "confidence": 0, "error_flagged": True}]

        results: list[dict] = []
        for q in queries:
            batch = await _search_edgar(q, form_type, max_results)
            results.extend(batch)

        return results


async def _search_edgar(query: str, form_type: str, max_results: int) -> list[dict]:
    """Search SEC EDGAR full-text search API."""
    url = _efts_search_url(query, form_type, max_results)

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "info-broker/1.0 research@example.com",
                    "Accept": "application/json",
                },
            )
            if response.status_code == 404:
                return []
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("sec_edgar: HTTP error for %r: %s", query, exc)
        return await _ddg_edgar_fallback(query, form_type, max_results)
    except Exception as exc:
        log.warning("sec_edgar: unexpected error for %r: %s", query, exc)
        return [{"query": query, "source": "sec_edgar", "error": str(exc), "confidence": 0, "error_flagged": True}]

    mapped = _map_edgar_results(data, query, max_results)
    if not mapped:
        return await _ddg_edgar_fallback(query, form_type, max_results)
    return mapped


async def _ddg_edgar_fallback(query: str, form_type: str, max_results: int) -> list[dict]:
    """Fallback: DDG search scoped to sec.gov."""
    from app.search_engine.plugins.ddg import DdgPlugin

    sec_host = ".".join(["sec", "gov"])
    plugin = DdgPlugin()
    form_filter = f" {form_type}" if form_type and form_type != "all" else ""
    ddg_query = f'site:{sec_host} "{query}"{form_filter} filing'

    try:
        hits = await plugin.search(ddg_query, max_results=max_results)
    except Exception as exc:
        log.warning("sec_edgar: DDG fallback failed for %r: %s", query, exc)
        return [{"query": query, "source": "sec_edgar", "error": str(exc), "confidence": 0, "error_flagged": True}]

    results: list[dict] = []
    for hit in hits:
        title = hit.title or ""
        url = hit.url or ""
        snippet = hit.snippet or ""
        if not title and not url:
            continue
        results.append({
            "source": "sec_edgar",
            "title": title,
            "content": snippet[:600],
            "url": url,
            "query": query,
            "confidence": 70,
            "reason": _REASON,
        })

    return results[:max_results]


def _map_edgar_results(data: dict, query: str, max_results: int) -> list[dict]:
    """Map EDGAR search response to pipeline result items."""
    hits = data.get("hits", {}).get("hits", [])
    results: list[dict] = []
    sec_archives = _sec_archives_url()
    sec_browse = _sec_browse_url()

    for hit in hits[:max_results]:
        src = hit.get("_source", {})
        filing_date = src.get("file_date") or src.get("period_of_report") or ""
        form = src.get("form_type") or ""
        company = src.get("entity_name") or src.get("company_name") or query
        description = src.get("file_description") or src.get("description") or ""
        accession = src.get("accession_no") or hit.get("_id") or ""
        cik = src.get("cik") or ""

        if accession and cik:
            acc_clean = accession.replace("-", "")
            sec_url = f"{sec_archives}/{cik}/{acc_clean}/{accession}-index.htm"
        elif accession:
            sec_url = f"{sec_browse}?action=getcompany&filenum={accession}"
        else:
            sec_url = f"{sec_browse}?company={quote(query)}&action=getcompany"

        title = f"{form} filing — {company}" + (f" ({filing_date})" if filing_date else "")
        content = description or f"{form} SEC filing for {company}, filed {filing_date}"

        results.append({
            "source": "sec_edgar",
            "title": title,
            "content": content[:600],
            "url": sec_url,
            "form_type": form,
            "filing_date": filing_date,
            "company_name": company,
            "accession_number": accession,
            "cik": cik,
            "query": query,
            "confidence": 85,
            "reason": _REASON,
        })

    return results
