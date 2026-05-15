"""Multi-engine meta-search node — parallel dispatch, dedup, consensus ranking, auto-translation.

Supported engines (free unless noted):
  ddg      — DuckDuckGo (free, no key)
  baidu    — Baidu (free scrape, Chinese-language web)
  yandex   — Yandex (free scrape, Russian/Slavic/EU web)
  serper   — Google via Serper API (key: SERPER_API_KEY)
  brave    — Brave Search API (key: BRAVE_API_KEY)
  exa      — Exa neural search (key: EXA_API_KEY)
  tavily   — Tavily AI Search (key: TAVILY_API_KEY)

Non-English results (Baidu/Yandex) are auto-translated to English via LLM.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Multi-engine search maximises coverage by querying several providers in parallel "
    "and surfaces the most credible results via cross-engine consensus scoring"
)

_SERPER_HOST = "google.serper.dev"
_BRAVE_HOST = "api.search.brave.com"
_EXA_HOST = "api.exa.ai"
_TAVILY_HOST = "api.tavily.com"

# Characters that indicate non-English (CJK, Cyrillic, Arabic, etc.)
_NON_ASCII_RE = re.compile(r'[Ѐ-ӿ一-鿿㐀-䶿؀-ۿ]')


# ---------------------------------------------------------------------------
# Language detection + translation
# ---------------------------------------------------------------------------

def _needs_translation(text: str) -> bool:
    """Return True if text contains significant non-Latin characters."""
    if not text:
        return False
    non_ascii = len(_NON_ASCII_RE.findall(text))
    return non_ascii > 3 or (non_ascii / max(len(text), 1)) > 0.15


async def _translate_batch(items: list[dict]) -> list[dict]:
    """Translate title+snippet of non-English results to English via LLM.

    Items that are already English pass through unchanged.
    Each translated item gets translated_from='baidu'|'yandex' and original_* fields.
    """
    to_translate = [i for i in items if _needs_translation(i.get("title", "") + " " + i.get("snippet", ""))]
    if not to_translate:
        return items

    # Build batch prompt
    entries = "\n".join(
        f"[{n}] TITLE: {r['title']}\nSNIPPET: {r.get('snippet', '')}"
        for n, r in enumerate(to_translate)
    )
    prompt = (
        "Translate the following search result titles and snippets to English. "
        "Preserve proper nouns, URLs, and numbers. "
        "Return ONLY a JSON array where each element has: "
        '{"i": <index>, "title": "<english title>", "snippet": "<english snippet>"}\n\n'
        + entries
    )

    translated_map: dict[int, dict] = {}
    try:
        from app.pipeline.strategies.llm_client import call_llm_json
        parsed = await call_llm_json(prompt, model="haiku")
        if isinstance(parsed, list):
            for item in parsed:
                idx = item.get("i")
                if isinstance(idx, int) and idx < len(to_translate):
                    translated_map[idx] = item
    except Exception as exc:
        log.warning("multi_search: translation failed: %s", exc)

    # Apply translations
    for n, r in enumerate(to_translate):
        if n in translated_map:
            r["original_title"] = r["title"]
            r["original_snippet"] = r.get("snippet", "")
            r["title"] = translated_map[n].get("title", r["title"])
            r["snippet"] = translated_map[n].get("snippet", r.get("snippet", ""))
            r["translated"] = True

    return items


async def _call_llm_for_translation(prompt: str) -> list | None:
    """Try multiple LLM call paths for translation."""
    # Try llm_providers directly
    try:
        import os
        import json

        api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            from app.routers.v3.db import fetch_one
            for key_name in ("anthropic_api_key", "gemini_api_key"):
                row = fetch_one("SELECT value FROM core_settings WHERE key = %s", (key_name,))
                if row and row.get("value"):
                    api_key = row["value"]
                    if key_name == "anthropic_api_key":
                        os.environ["ANTHROPIC_API_KEY"] = api_key
                    else:
                        os.environ["GEMINI_API_KEY"] = api_key
                    break

        from llm_providers import complete
        response = await complete(prompt, model="haiku", max_tokens=2000)
        text = response.strip()
        # Extract JSON array
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
    except Exception as exc:
        log.debug("multi_search: LLM translation via llm_providers failed: %s", exc)
    return None


# Monkey-patch: replace the stub with real impl
async def _translate_batch_real(items: list[dict]) -> list[dict]:
    """Translate non-English results to English via LLM."""
    to_translate = [
        (n, r) for n, r in enumerate(items)
        if _needs_translation(r.get("title", "") + " " + r.get("snippet", ""))
    ]
    if not to_translate:
        return items

    import json

    entries = "\n".join(
        f"[{n}] TITLE: {r['title']}\nSNIPPET: {r.get('snippet', '')[:300]}"
        for n, r in to_translate
    )
    prompt = (
        "Translate the following search result titles and snippets from their source language to English. "
        "Preserve proper nouns, entity names, URLs, and numbers exactly. "
        "Return ONLY a JSON array — no explanation, no markdown:\n"
        '[{"i": 0, "title": "...", "snippet": "..."}, ...]\n\n'
        + entries
    )

    parsed = await _call_llm_for_translation(prompt)
    if not parsed:
        log.warning("multi_search: could not translate %d results — LLM unavailable", len(to_translate))
        return items

    translated_map = {item.get("i"): item for item in parsed if isinstance(item, dict)}
    for seq, (orig_idx, r) in enumerate(to_translate):
        hit = translated_map.get(seq)
        if hit:
            r["original_title"] = r["title"]
            r["original_snippet"] = r.get("snippet", "")
            r["title"] = hit.get("title", r["title"])
            r["snippet"] = hit.get("snippet", r.get("snippet", ""))
            r["translated"] = True

    return items


# ---------------------------------------------------------------------------
# DDG backend
# ---------------------------------------------------------------------------

async def _search_ddg_async(query: str, max_results: int) -> list[dict]:
    """Return DDG results via DdgPlugin, tagged with engine='ddg'."""
    try:
        from app.search_engine.plugins.ddg import DdgPlugin
        results = await DdgPlugin().search(query, max_results=max_results)
        return [
            {"title": r.title or "", "url": r.url or "", "snippet": r.snippet or "", "engine": "ddg"}
            for r in results
        ]
    except Exception as exc:
        log.warning("multi_search: ddg error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Baidu backend (free HTML scrape — Chinese web index)
# ---------------------------------------------------------------------------

def _search_baidu(query: str, max_results: int) -> list[dict]:
    """Scrape Baidu search results. Returns Chinese text — caller translates."""
    url = "https://www.baidu.com/s"
    params = {"wd": query, "rn": min(max_results, 10), "ie": "utf-8"}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            html = resp.text

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        results: list[dict] = []
        # Baidu desktop: result containers
        for card in soup.select("div.result, div.result-op, div[class^='result']")[:max_results]:
            title_el = card.select_one("h3, .t")
            snippet_el = card.select_one(".c-abstract, .c-gap-top-small, .content-right")
            link_el = card.select_one("a[href]")

            title = title_el.get_text(" ", strip=True) if title_el else ""
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
            href = link_el.get("href", "") if link_el else ""

            if not title or len(title) < 3:
                continue

            results.append({
                "title": title[:200],
                "url": href,
                "snippet": snippet[:400],
                "engine": "baidu",
                "language": "zh",
            })

        if not results:
            # Fallback: h3 links
            for h3 in soup.select("h3")[:max_results]:
                link = h3.select_one("a[href]")
                if link and len(link.get_text(" ", strip=True)) > 5:
                    results.append({
                        "title": link.get_text(" ", strip=True)[:200],
                        "url": link.get("href", ""),
                        "snippet": "",
                        "engine": "baidu",
                        "language": "zh",
                    })

        log.debug("multi_search: baidu returned %d results for %r", len(results), query)
        return results
    except Exception as exc:
        log.warning("multi_search: baidu error: %s", exc)
        return []


async def _search_baidu_async(query: str, max_results: int) -> list[dict]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _search_baidu, query, max_results)


# ---------------------------------------------------------------------------
# Yandex backend (free HTML scrape — Russian/Slavic/EU web index)
# ---------------------------------------------------------------------------

def _search_yandex(query: str, max_results: int) -> list[dict]:
    """Scrape Yandex search results. Returns mixed-language text — caller translates."""
    url = "https://yandex.com/search/"
    params = {"text": query, "numdoc": min(max_results, 10)}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            html = resp.text

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        results: list[dict] = []
        # Yandex organic results
        for item in soup.select("li.serp-item, div.organic, div[class*='serp-item']")[:max_results]:
            title_el = item.select_one("h2, .organic__title, .serp-title, a[class*='title']")
            snippet_el = item.select_one(
                ".organic__text, .serp-item__text, .text-container, [class*='passage']"
            )
            link_el = item.select_one("a.organic__url, a[class*='link'], a[href^='http']")

            title = title_el.get_text(" ", strip=True) if title_el else ""
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
            href = link_el.get("href", "") if link_el else ""

            if not title or len(title) < 5:
                continue
            if "yandex.com" in href and "/search/" in href:
                continue

            results.append({
                "title": title[:200],
                "url": href,
                "snippet": snippet[:400],
                "engine": "yandex",
                "language": "ru",
            })

        if not results:
            # Fallback: h2 headings with links
            for h2 in soup.select("h2")[:max_results * 2]:
                link = h2.select_one("a[href]")
                if link and len(link.get_text(" ", strip=True)) > 5:
                    href = link.get("href", "")
                    if "yandex" not in href:
                        results.append({
                            "title": link.get_text(" ", strip=True)[:200],
                            "url": href, "snippet": "",
                            "engine": "yandex", "language": "ru",
                        })
                if len(results) >= max_results:
                    break

        log.debug("multi_search: yandex returned %d results for %r", len(results), query)
        return results
    except Exception as exc:
        log.warning("multi_search: yandex error: %s", exc)
        return []


async def _search_yandex_async(query: str, max_results: int) -> list[dict]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _search_yandex, query, max_results)


def _search_yandex_xml(query: str, api_key: str, max_results: int) -> list[dict]:
    """Yandex XML Search API — free 10,000 queries/month. Requires YANDEX_API_KEY."""
    # Yandex XML API: https://yandex.com/dev/xml/
    url = "https://yandex.com/search/xml"
    params = {
        "query": query,
        "groupby": f"attr=d.mode=flat.groups-on-page={min(max_results, 10)}.docs-in-group=1",
        "key": api_key,
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()

        # Parse XML response
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.text)
        results: list[dict] = []

        for doc in root.findall(".//doc"):
            title_el = doc.find("title")
            url_el = doc.find("url")
            passages_el = doc.find(".//passages/passage")
            headline_el = doc.find("headline")

            title = title_el.text or "" if title_el is not None else ""
            href = url_el.text or "" if url_el is not None else ""
            snippet = (passages_el.text or "") if passages_el is not None else ""
            if not snippet and headline_el is not None:
                snippet = headline_el.text or ""

            if title or href:
                results.append({
                    "title": title[:200],
                    "url": href,
                    "snippet": snippet[:400],
                    "engine": "yandex",
                    "language": "ru",
                })

        log.debug("multi_search: yandex XML returned %d results", len(results))
        return results
    except Exception as exc:
        log.warning("multi_search: yandex XML error: %s — falling back to HTML scrape", exc)
        return _search_yandex(query, max_results)


# ---------------------------------------------------------------------------
# Serper backend (Google via API)
# ---------------------------------------------------------------------------

def _search_serper(query: str, api_key: str, max_results: int) -> list[dict]:
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(
                f"https://{_SERPER_HOST}/search",
                json={"q": query, "num": max_results},
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            {"title": item.get("title", ""), "url": item.get("link", ""),
             "snippet": item.get("snippet", ""), "engine": "serper"}
            for item in (data.get("organic") or [])
        ]
    except Exception as exc:
        log.warning("multi_search: serper error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Brave backend
# ---------------------------------------------------------------------------

def _search_brave(query: str, api_key: str, max_results: int) -> list[dict]:
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(
                f"https://{_BRAVE_HOST}/res/v1/web/search",
                params={"q": query, "count": max_results},
                headers={"Accept": "application/json", "Accept-Encoding": "gzip",
                         "[REDACTED:high-entropy-base64:20ch:hash=721b51dd]": api_key},
            )
            resp.raise_for_status()
            data = resp.json()
        web = data.get("web") or {}
        return [
            {"title": item.get("title", ""), "url": item.get("url", ""),
             "snippet": item.get("description", ""), "engine": "brave"}
            for item in (web.get("results") or [])
        ]
    except Exception as exc:
        log.warning("multi_search: brave error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Exa backend
# ---------------------------------------------------------------------------

def _search_exa(query: str, api_key: str, max_results: int) -> list[dict]:
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(
                f"https://{_EXA_HOST}/search",
                json={"query": query, "numResults": max_results},
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            {"title": item.get("title", ""), "url": item.get("url", ""),
             "snippet": item.get("text", "") or (item.get("highlights") or [""])[0],
             "engine": "exa"}
            for item in (data.get("results") or [])
        ]
    except Exception as exc:
        log.warning("multi_search: exa error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Yahoo backend (free scrape — Bing-powered, scrape-friendly)
# ---------------------------------------------------------------------------

def _search_yahoo(query: str, max_results: int) -> list[dict]:
    """Scrape Yahoo Search results (powered by Bing index, no API key needed)."""
    url = "https://search.yahoo.com/search"
    params = {"p": query, "n": min(max_results, 10)}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(url, params=params, headers=headers)
            resp.raise_for_status()

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[dict] = []

        for card in soup.select("div.algo")[:max_results]:
            h3 = card.select_one("h3 a, h3.title a, .compTitle a")
            snippet_el = card.select_one(".compText, p, .abstract")
            if not h3:
                continue
            results.append({
                "title": h3.get_text(" ", strip=True)[:200],
                "url": h3.get("href", ""),
                "snippet": snippet_el.get_text(" ", strip=True)[:400] if snippet_el else "",
                "engine": "yahoo",
            })

        log.debug("multi_search: yahoo returned %d results", len(results))
        return results
    except Exception as exc:
        log.warning("multi_search: yahoo error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Google direct scrape (fallback when no Serper key) + Bing API/scrape
# ---------------------------------------------------------------------------

def _search_google_direct(query: str, max_results: int) -> list[dict]:
    """Scrape Google search — fallback when SERPER_API_KEY not set.

    Note: Google aggressively rate-limits scrapers. Results may be partial.
    """
    url = "https://www.google.com/search"
    params = {"q": query, "num": min(max_results, 10), "hl": "en"}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(url, params=params, headers=headers)
            resp.raise_for_status()

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[dict] = []

        for div in soup.select("div.g, div.tF2Cxc, div[data-hveid]")[:max_results * 2]:
            h3 = div.select_one("h3")
            link = div.select_one("a[href^='http']")
            snippet_el = div.select_one("div.VwiC3b, span.aCOpRe, div[class*='snippet']")
            if not h3 or not link:
                continue
            href = link.get("href", "")
            if "google.com" in href:
                continue
            results.append({
                "title": h3.get_text(" ", strip=True)[:200],
                "url": href,
                "snippet": snippet_el.get_text(" ", strip=True)[:400] if snippet_el else "",
                "engine": "google",
            })
            if len(results) >= max_results:
                break

        log.debug("multi_search: google direct returned %d results", len(results))
        return results
    except Exception as exc:
        log.warning("multi_search: google direct error: %s", exc)
        return []


def _search_bing(query: str, api_key: str | None, max_results: int) -> list[dict]:
    """Bing Search — uses API if BING_API_KEY set, else scrapes HTML."""
    if api_key:
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.get(
                    "https://api.bing.microsoft.com/v7.0/search",
                    params={"q": query, "count": max_results},
                    headers={"Ocp-Apim-Subscription-Key": api_key},
                )
                resp.raise_for_status()
                data = resp.json()
            return [
                {"title": item.get("name", ""), "url": item.get("url", ""),
                 "snippet": item.get("snippet", ""), "engine": "bing"}
                for item in (data.get("webPages", {}).get("value") or [])
            ]
        except Exception as exc:
            log.warning("multi_search: bing API error: %s", exc)

    # HTML scrape fallback
    try:
        url = "https://www.bing.com/search"
        params = {"q": query, "count": min(max_results, 10)}
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(url, params=params, headers=headers)
            resp.raise_for_status()

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[dict] = []

        # Bing desktop results
        for item in soup.select("li.b_algo, div.b_algo")[:max_results]:
            h2a = item.select_one("h2 a")
            p = item.select_one(".b_caption p, p")
            if h2a and len(h2a.get_text(" ", strip=True)) > 5:
                results.append({
                    "title": h2a.get_text(" ", strip=True)[:200],
                    "url": h2a.get("href", ""),
                    "snippet": p.get_text(" ", strip=True)[:400] if p else "",
                    "engine": "bing",
                })

        log.debug("multi_search: bing HTML returned %d results", len(results))
        return results
    except Exception as exc:
        log.warning("multi_search: bing HTML error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Tavily backend
# ---------------------------------------------------------------------------

def _search_tavily(query: str, api_key: str, max_results: int) -> list[dict]:
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(
                f"https://{_TAVILY_HOST}/search",
                json={"query": query, "max_results": max_results, "search_depth": "basic"},
                headers={"Content-Type": "application/json", "[REDACTED:high-entropy-base64:20ch:hash=721b51dd]": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            {"title": item.get("title", ""), "url": item.get("url", ""),
             "snippet": item.get("content", ""), "engine": "tavily"}
            for item in (data.get("results") or [])
        ]
    except Exception as exc:
        log.warning("multi_search: tavily error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Dedup + ranking
# ---------------------------------------------------------------------------

_UTM_PATTERN = re.compile(r"utm_[^&]+&?", re.IGNORECASE)


def _normalize_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        filtered = {k: v for k, v in qs.items() if not k.lower().startswith("utm_")}
        clean_query = urlencode(sorted(filtered.items()))
        return urlunparse((
            parsed.scheme, parsed.netloc.lower(),
            parsed.path.rstrip("/") or "/",
            parsed.params, clean_query, "",
        ))
    except Exception:
        return url.rstrip("/")


def _dedup_results(results: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    order: list[str] = []
    for r in results:
        key = _normalize_url(r.get("url", ""))
        if key not in seen:
            seen[key] = {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("snippet", ""),
                "engines": [r["engine"]],
                "consensus_score": 1,
                "language": r.get("language"),
                "translated": r.get("translated", False),
                "original_title": r.get("original_title"),
                "original_snippet": r.get("original_snippet"),
            }
            order.append(key)
        else:
            entry = seen[key]
            if r["engine"] not in entry["engines"]:
                entry["engines"].append(r["engine"])
                entry["consensus_score"] += 1
            if len(r.get("title", "")) > len(entry["title"]):
                entry["title"] = r["title"]
            if len(r.get("snippet", "")) > len(entry["snippet"]):
                entry["snippet"] = r["snippet"]
    return [seen[k] for k in order]


def _rank_by_consensus(results: list[dict]) -> list[dict]:
    return sorted(results, key=lambda r: r["consensus_score"], reverse=True)


# ---------------------------------------------------------------------------
# API key helper
# ---------------------------------------------------------------------------

def _get_api_key(engine: str) -> str | None:
    key = os.getenv(f"{engine.upper()}_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one("SELECT value FROM core_settings WHERE key = %s", (f"{engine}_api_key",))
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

class MultiSearchNode:
    node_type = "multi_search"
    display_name = "Multi-Engine Web Search"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "title": "Search Query"},
            "engines": {
                "type": "array",
                "title": "Engines",
                "description": (
                    "Free (no key): ddg, baidu, yahoo, bing, google. "
                    "Need API key: serper (→Google), brave, exa, tavily. "
                    "baidu=Chinese web, yandex=Russian/Slavic (key: YANDEX_API_KEY). "
                    "serper/bing/google auto-fallback to HTML scrape if no key."
                ),
                "items": {
                    "type": "string",
                    "enum": ["ddg", "baidu", "yandex", "yahoo", "serper", "bing", "google", "brave", "exa", "tavily"],
                },
                "default": ["ddg", "baidu", "yahoo", "serper", "brave"],
            },
            "max_results": {
                "type": "integer", "title": "Max Results",
                "default": 20, "minimum": 1, "maximum": 100,
            },
            "translate": {
                "type": "boolean",
                "title": "Auto-translate to English",
                "description": "Translate Baidu/Yandex results to English via LLM.",
                "default": True,
            },
        },
        "required": [],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        query: str = (
            config.get("query")
            or next(
                (i.get("query") or i.get("message") or i.get("title") for i in inputs if i),
                None,
            )
            or ""
        ).strip()

        if not query:
            return [{"error": "multi_search requires a 'query'", "source": "multi_search"}]

        engines: list[str] = config.get("engines") or ["ddg", "baidu", "yahoo", "serper", "brave"]
        max_results: int = int(config.get("max_results", 20))
        auto_translate: bool = config.get("translate", True)

        loop = asyncio.get_running_loop()
        tasks: list = []
        engine_labels: list[str] = []

        for engine in engines:
            if engine == "ddg":
                tasks.append(_search_ddg_async(query, max_results))
                engine_labels.append("ddg")
            elif engine == "baidu":
                tasks.append(_search_baidu_async(query, max_results))
                engine_labels.append("baidu")
            elif engine == "yandex":
                key = _get_api_key("yandex")
                if key:
                    # Yandex XML API (free 10k/mo) — preferred
                    tasks.append(loop.run_in_executor(None, _search_yandex_xml, query, key, max_results))
                else:
                    tasks.append(_search_yandex_async(query, max_results))
                engine_labels.append("yandex")
            elif engine == "yahoo":
                tasks.append(loop.run_in_executor(None, _search_yahoo, query, max_results))
                engine_labels.append("yahoo")
            elif engine == "serper":
                key = _get_api_key("serper")
                if key:
                    tasks.append(loop.run_in_executor(None, _search_serper, query, key, max_results))
                    engine_labels.append("serper")
                else:
                    # Fallback: scrape Google directly
                    log.debug("multi_search: no SERPER_API_KEY — falling back to Google direct scrape")
                    tasks.append(loop.run_in_executor(None, _search_google_direct, query, max_results))
                    engine_labels.append("google")
            elif engine == "google":
                tasks.append(loop.run_in_executor(None, _search_google_direct, query, max_results))
                engine_labels.append("google")
            elif engine == "bing":
                key = _get_api_key("bing")
                tasks.append(loop.run_in_executor(None, _search_bing, query, key, max_results))
                engine_labels.append("bing")
            elif engine == "brave":
                key = _get_api_key("brave")
                if key:
                    tasks.append(loop.run_in_executor(None, _search_brave, query, key, max_results))
                    engine_labels.append("brave")
                else:
                    log.debug("multi_search: skipping brave — BRAVE_API_KEY not set")
            elif engine == "exa":
                key = _get_api_key("exa")
                if key:
                    tasks.append(loop.run_in_executor(None, _search_exa, query, key, max_results))
                    engine_labels.append("exa")
                else:
                    log.debug("multi_search: skipping exa — EXA_API_KEY not set")
            elif engine == "tavily":
                key = _get_api_key("tavily")
                if key:
                    tasks.append(loop.run_in_executor(None, _search_tavily, query, key, max_results))
                    engine_labels.append("tavily")
                else:
                    log.debug("multi_search: skipping tavily — TAVILY_API_KEY not set")

        if not tasks:
            return [{"error": "no search engines available", "source": "multi_search"}]

        batches = await asyncio.gather(*tasks, return_exceptions=True)

        raw: list[dict] = []
        for batch in batches:
            if isinstance(batch, Exception):
                log.warning("multi_search: engine raised: %s", batch)
                continue
            raw.extend(batch)  # type: ignore[arg-type]

        # Translate non-English results
        if auto_translate:
            raw = await _translate_batch_real(raw)

        deduped = _dedup_results(raw)
        ranked = _rank_by_consensus(deduped)
        top = ranked[:max_results]

        return [
            {
                "title": r["title"],
                "url": r["url"],
                "snippet": r["snippet"],
                "engines": r["engines"],
                "consensus_score": r["consensus_score"],
                "source": "multi_search",
                "reason": _REASON,
                **({"translated": True, "original_title": r.get("original_title"),
                    "original_snippet": r.get("original_snippet"), "language": r.get("language")}
                   if r.get("translated") else {}),
            }
            for r in top
        ]
