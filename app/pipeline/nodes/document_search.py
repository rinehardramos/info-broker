"""Document search node — Google Dorking via DuckDuckGo to find files (PDF, DOCX, etc.)."""

from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Document search (Google Dorking) finds publicly accessible files "
    "associated with a person or domain — useful for discovering CVs, "
    "contracts, reports, and other leaked or published documents."
)
_DDG_URL = "https://" + "html.duckduckgo.com" + "/html/"
_DEFAULT_FILETYPES = ["pdf", "docx", "xlsx", "pptx"]
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; info-broker-research-bot/1.0; "
        "+https://github.com/info-broker)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _build_dork_queries(query: str, site: str | None, filetypes: list[str]) -> list[str]:
    """Build DuckDuckGo-compatible dork queries — one per filetype.

    Examples:
        "John Doe" filetype:pdf
        site:acme.com "report" filetype:pdf
    """
    queries: list[str] = []
    quoted = f'"{query}"' if query and " " in query else query
    for ft in filetypes:
        parts: list[str] = []
        if site:
            parts.append(f"site:{site}")
        parts.append(quoted)
        parts.append(f"filetype:{ft}")
        queries.append(" ".join(parts))
    return queries


def _run_dork_search(queries: list[str], max_results: int) -> list[dict]:
    """Execute DuckDuckGo HTML searches for each dork query.

    Parses result links and titles from the HTML response,
    filtering to URLs that end in a recognised document extension.
    """
    seen_urls: set[str] = set()
    results: list[dict] = []

    doc_ext_re = re.compile(
        r"\.(pdf|docx?|xlsx?|pptx?|odt|ods|odp|csv|txt|rtf)(\?.*)?$",
        re.IGNORECASE,
    )

    with httpx.Client(timeout=20.0, headers=_HEADERS, follow_redirects=True) as client:
        for query in queries:
            if len(results) >= max_results:
                break
            try:
                response = client.get(
                    _DDG_URL,
                    params={"q": query, "kl": "us-en"},
                )
                response.raise_for_status()
            except Exception as exc:
                log.warning("document_search: DDG request failed for %r: %s", query, exc)
                continue

            # Extract result links + titles from the raw HTML using regex
            # DDG HTML results use <a class="result__a" href="...">Title</a>
            link_pattern = re.compile(
                r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                re.DOTALL,
            )
            snippet_pattern = re.compile(
                r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
                re.DOTALL,
            )

            links = link_pattern.findall(response.text)
            snippets = [
                re.sub(r"<[^>]+>", "", s).strip()
                for s in snippet_pattern.findall(response.text)
            ]

            for idx, (href, raw_title) in enumerate(links):
                if len(results) >= max_results:
                    break
                # DDG wraps redirect URLs; unwrap if needed
                url = _unwrap_ddg_url(href)
                if not url or url in seen_urls:
                    continue
                # Only keep document-like URLs
                ext_match = doc_ext_re.search(url)
                if not ext_match:
                    continue
                seen_urls.add(url)
                title = re.sub(r"<[^>]+>", "", raw_title).strip()
                snippet = snippets[idx] if idx < len(snippets) else ""
                results.append(
                    {
                        "title": title,
                        "url": url,
                        "filetype": ext_match.group(1).lower(),
                        "snippet": snippet,
                        "source": "document_search",
                        "reason": _REASON,
                    }
                )

    return results


def _unwrap_ddg_url(href: str) -> str | None:
    """DDG sometimes wraps URLs in a redirect. Extract the real URL."""
    if href.startswith("//duckduckgo.com/l/?"):
        parsed = urllib.parse.urlparse("https:" + href)
        qs = urllib.parse.parse_qs(parsed.query)
        uddg = qs.get("uddg", [None])[0]
        if uddg:
            return urllib.parse.unquote(uddg)
        return None
    return href if href.startswith("http") else None


class DocumentSearchNode:
    node_type = "document_search"
    display_name = "Document Search"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "title": "Search Query",
                "description": "Person name, company name, or keyword to search for.",
            },
            "site": {
                "type": "string",
                "title": "Limit to Site (optional)",
                "description": "Restrict results to a specific domain, e.g. acme.com",
            },
            "filetypes": {
                "type": "array",
                "items": {"type": "string"},
                "title": "File Types",
                "default": _DEFAULT_FILETYPES,
                "description": "Document extensions to search for.",
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        # Resolve query: config first, then first input that has a query field
        query = (config.get("query") or "").strip()
        if not query:
            for item in inputs:
                candidate = (
                    item.get("query")
                    or item.get("name")
                    or item.get("full_name")
                    or item.get("company")
                    or ""
                ).strip()
                if candidate:
                    query = candidate
                    break

        if not query:
            log.warning("document_search: no query provided")
            return [
                {
                    "error": "No query provided for document search",
                    "source": "document_search",
                    "reason": _REASON,
                }
            ]

        site = (config.get("site") or "").strip() or None
        filetypes: list[str] = config.get("filetypes") or _DEFAULT_FILETYPES
        max_results = min(int(config.get("max_results", 10)), 50)

        queries = _build_dork_queries(query, site, filetypes)

        loop = asyncio.get_running_loop()
        results: list[dict] = await loop.run_in_executor(
            None, _run_dork_search, queries, max_results
        )

        if not results:
            return [
                {
                    "query": query,
                    "site": site,
                    "filetypes": filetypes,
                    "results_found": 0,
                    "source": "document_search",
                    "reason": _REASON,
                }
            ]

        return results
