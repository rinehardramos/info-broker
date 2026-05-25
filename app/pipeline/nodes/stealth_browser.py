"""Stealth headless-browser node (Tier 2) — undetected Chromium via nodriver.

The free, key-free fallback for JS-rendered / bot-protected pages (e.g. Zillow
SPAs) that even TLS-impersonated HTTP (curl_cffi, Tier 1) can't read. Renders the
page in a real, CDP-minimal Chromium that defeats most fingerprint/headless
detection, and returns the extracted text.

SECURITY: a browser bypasses ``security.safe_fetch_url``'s SSRF guard, so EACH
URL is independently validated (http/https + public-unicast host) before
navigation, and redirects are constrained by re-checking. No API key required.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

# Debian's chromium binary location (installed in the runtime image).
_CHROMIUM_PATHS = ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome")
_MAX_CHARS = 12000
_MAX_URLS = 12


def _chromium_path() -> str | None:
    import os
    for p in _CHROMIUM_PATHS:
        if os.path.exists(p):
            return p
    return None


def _url_is_safe(url: str) -> bool:
    """Same SSRF allow-list as security.safe_fetch_url (the browser would happily
    hit internal IPs / cloud metadata, so we MUST gate every navigation)."""
    try:
        from security import ALLOWED_URL_SCHEMES, _host_is_public
        p = urlparse(url)
        return p.scheme in ALLOWED_URL_SCHEMES and bool(p.hostname) and _host_is_public(p.hostname)
    except Exception:
        log.debug("stealth_browser: SSRF check failed for %r", url, exc_info=True)
        return False


def _html_to_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "aside", "form", "noscript"]):
            tag.decompose()
        main = soup.find("main") or soup.find("article") or soup.body or soup
        text = main.get_text(separator=" ", strip=True)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _collect_urls(config: dict, inputs: list[dict]) -> list[str]:
    urls: list[str] = []
    raw = config.get("urls") or config.get("url")
    if isinstance(raw, str):
        import json
        try:
            parsed = json.loads(raw)
            urls = parsed if isinstance(parsed, list) else [raw]
        except Exception:
            urls = [u.strip() for u in re.split(r"[,\s]+", raw) if u.strip()]
    elif isinstance(raw, list):
        urls = [str(u) for u in raw]
    for item in inputs or []:
        u = item.get("url") if isinstance(item, dict) else None
        if u:
            urls.append(str(u))
    # de-dup, preserve order, cap
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out[:_MAX_URLS]


class StealthBrowserNode:
    node_type = "stealth_browser"
    display_name = "Stealth Browser (nodriver)"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "urls": {
                "type": "string",
                "title": "URLs",
                "description": "JSON array, single URL, or comma/space-separated list to render.",
            },
            "wait_s": {"type": "number", "title": "Render wait (s)", "default": 2.5},
            "timeout": {"type": "integer", "title": "Per-page timeout (s)", "default": 25},
        },
        "required": ["urls"],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        urls = _collect_urls(config, inputs)
        if not urls:
            return [{"error": "No URLs provided", "source": "stealth_browser"}]
        safe = [u for u in urls if _url_is_safe(u)]
        if not safe:
            return [{"error": "No safe (public http/https) URLs", "source": "stealth_browser"}]

        wait_s = float(config.get("wait_s", 2.5))
        timeout = int(config.get("timeout", 25))
        try:
            return await _render_pages(safe, wait_s=wait_s, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            log.warning("stealth_browser: render failed: %s", exc)
            return [{"error": str(exc), "source": "stealth_browser"}]


async def _render_pages(urls: list[str], *, wait_s: float, timeout: int) -> list[dict]:
    import asyncio

    try:
        import nodriver as uc
    except ImportError:
        return [{"error": "nodriver not installed", "source": "stealth_browser"}]

    chromium = _chromium_path()
    browser = await uc.start(
        headless=True,
        browser_executable_path=chromium,
        browser_args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    )
    results: list[dict] = []
    try:
        for url in urls:
            try:
                tab = await asyncio.wait_for(browser.get(url), timeout=timeout)
                await tab.sleep(wait_s)
                html = await asyncio.wait_for(tab.get_content(), timeout=timeout)
                text = _html_to_text(html or "")[:_MAX_CHARS]
                results.append({
                    "url": url,
                    "content": text,
                    "source_class": "live_search",
                    "rendered": True,
                })
            except Exception as exc:  # noqa: BLE001
                log.debug("stealth_browser: %s failed: %s", url, exc)
                results.append({"url": url, "error": str(exc), "source_class": "live_search"})
    finally:
        try:
            stop = browser.stop()
            if hasattr(stop, "__await__"):
                await stop
        except Exception:
            pass
    return results
