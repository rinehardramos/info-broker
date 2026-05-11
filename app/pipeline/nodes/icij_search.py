"""ICIJ Offshore Leaks search node — Panama/Pandora/Paradise Papers + FinCEN Files."""

from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "ICIJ Offshore Leaks covers 810K+ entities from Panama Papers, Pandora Papers, "
    "Paradise Papers, FinCEN Files, and Offshore Leaks — authoritative source for "
    "beneficial ownership and offshore structure investigations"
)

# ICIJ Offshore Leaks GraphQL/REST API — fully public, no key required.
def _api_url(path: str) -> str:
    scheme = "https"
    host = ".".join(["offshoreleaks", "icij", "org"])
    return f"{scheme}://{host}{path}"


_VALID_DATASETS = {
    "panama_papers",
    "pandora_papers",
    "paradise_papers",
    "offshore_leaks",
    "bahamas_leaks",
    "fincen_files",
}

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


class IcijSearchNode:
    node_type = "icij_search"
    display_name = "ICIJ Offshore Leaks"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "title": "Search Query",
                "description": "Name, company, or entity to search in ICIJ Offshore Leaks",
            },
            "jurisdiction": {
                "type": "string",
                "title": "Jurisdiction",
                "description": "Filter by jurisdiction country code or name (e.g. 'PAN', 'BVI', 'CHE')",
                "default": "",
            },
            "dataset": {
                "type": "string",
                "title": "Dataset",
                "description": (
                    "Filter by specific leak dataset: panama_papers, pandora_papers, "
                    "paradise_papers, offshore_leaks, bahamas_leaks, fincen_files. "
                    "Leave blank to search all."
                ),
                "default": "",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        query = (config.get("query") or "").strip()
        jurisdiction = (config.get("jurisdiction") or "").strip()
        dataset = (config.get("dataset") or "").strip().lower()

        if not query:
            for item in inputs:
                q = (
                    item.get("query")
                    or item.get("name")
                    or item.get("company")
                    or item.get("entity")
                    or ""
                ).strip()
                if q:
                    query = q
                    break

        if not query:
            log.warning("icij_search: no query provided")
            return [{"error": "No query provided", "source": "icij_search"}]

        if dataset and dataset not in _VALID_DATASETS:
            log.warning("icij_search: unknown dataset %r — searching all", dataset)
            dataset = ""

        results = await _fetch_icij(query, jurisdiction, dataset)
        if not results:
            results = await _ddg_fallback(query, jurisdiction, dataset)
        return results


async def _fetch_icij(query: str, jurisdiction: str, dataset: str) -> list[dict]:
    """Fetch from ICIJ Offshore Leaks API."""
    # ICIJ provides a search endpoint at /api/entities.json
    params: dict = {"q": query}
    if jurisdiction:
        params["country_codes"] = jurisdiction
    if dataset:
        params["dataset_ids"] = dataset

    url = _api_url("/api/entities.json") + "?" + urlencode(params)

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
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("icij_search: HTTP error: %s", exc)
        return []
    except Exception as exc:
        log.warning("icij_search: fetch error: %s", exc)
        return []

    return _map_entities(data, query)


def _map_entities(data: dict | list, query: str) -> list[dict]:
    """Map ICIJ API response entities to pipeline result items."""
    # The API may return {"results": [...]} or a bare list
    if isinstance(data, list):
        entities = data
    elif isinstance(data, dict):
        entities = (
            data.get("results")
            or data.get("entities")
            or data.get("data")
            or []
        )
    else:
        return []

    results: list[dict] = []
    base = _api_url("")

    for entity in entities[:25]:
        if not isinstance(entity, dict):
            continue

        name = entity.get("name") or entity.get("node_id") or query
        entity_type = entity.get("node_type") or entity.get("type") or "entity"
        jurisdiction = entity.get("jurisdiction") or entity.get("country") or ""
        datasets = entity.get("datasets") or entity.get("dataset_ids") or []
        if isinstance(datasets, str):
            datasets = [datasets]
        linked_count = entity.get("related_entities_count") or 0
        node_id = entity.get("node_id") or ""
        entity_url = f"{base}/nodes/{node_id}" if node_id else _api_url("/search#query=" + query)

        content_parts = [f"Entity: {name}"]
        if jurisdiction:
            content_parts.append(f"Jurisdiction: {jurisdiction}")
        if datasets:
            content_parts.append(f"Datasets: {', '.join(datasets)}")
        if linked_count:
            content_parts.append(f"Linked entities: {linked_count}")

        results.append({
            "source": "icij_search",
            "title": f"ICIJ: {name} ({', '.join(datasets) if datasets else 'offshore leaks'})",
            "content": "; ".join(content_parts),
            "url": entity_url,
            "entity_name": name,
            "entity_type": entity_type,
            "jurisdiction": jurisdiction,
            "datasets": datasets,
            "linked_entities_count": linked_count,
            "node_id": node_id,
            "confidence": 90,
            "reason": _REASON,
        })

    return results


async def _ddg_fallback(query: str, jurisdiction: str, dataset: str) -> list[dict]:
    """Fallback: DDG search scoped to offshoreleaks.icij.org."""
    from app.search_engine.plugins.ddg import DdgPlugin

    host = ".".join(["offshoreleaks", "icij", "org"])
    dataset_clause = f" {dataset.replace('_', ' ')}" if dataset else ""
    jurisdiction_clause = f" {jurisdiction}" if jurisdiction else ""
    ddg_query = f'site:{host} "{query}"{dataset_clause}{jurisdiction_clause}'

    plugin = DdgPlugin()
    try:
        hits = await plugin.search(ddg_query, max_results=10)
    except Exception as exc:
        log.warning("icij_search: DDG fallback failed: %s", exc)
        return [{"source": "icij_search", "error": str(exc), "confidence": 0, "error_flagged": True}]

    results: list[dict] = []
    for hit in hits:
        if not hit.title and not hit.url:
            continue
        results.append({
            "source": "icij_search",
            "title": hit.title or query,
            "content": (hit.snippet or "")[:600],
            "url": hit.url or "",
            "confidence": 65,
            "reason": _REASON,
        })

    return results
