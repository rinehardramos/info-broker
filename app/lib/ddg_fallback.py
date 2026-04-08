"""Global DuckDuckGo web-search fallback.

Reusable last-resort provider for every adapter whose primary API key is
missing, revoked, or returning garbage. The flow is:

    ddg_search(query)         →   list[{title, url, snippet}]
    scrape_url(url)           →   clean main-body text
    summarize(text, hint)     →   one-paragraph summary
    ddg_fallback_summary(q)   →   {summary, sources, raw_excerpts}

All outbound HTTP goes through ``security.safe_fetch_url`` so SSRF,
redirects, oversized bodies, and non-HTML content-types are blocked by
the same guard the keyed providers use.

Summarization is pluggable:
  - If ``SUMMARIZER_URL`` is set (OpenAI-compatible /v1 endpoint, e.g.
    LM Studio at http://host.docker.internal:1234/v1), call it.
  - Otherwise fall back to an extractive summary (first N sentences of
    the highest-ranked scraped page) so the function never fails.

Intentionally does NOT cache — callers already cache the full adapter
response at the router layer, so double-caching would stale twice.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from bs4 import BeautifulSoup

from security import HTML_CONTENT_TYPES, safe_fetch_url

log = logging.getLogger(__name__)


class DdgFallbackUnavailable(Exception):
    """Raised when search returns nothing scrapeable."""


# ── Search ───────────────────────────────────────────────────────────────────


def ddg_search(query: str, *, max_results: int = 5) -> list[dict[str, str]]:
    """Return up to ``max_results`` web results via the ``ddgs`` library.

    Each item: ``{"title": str, "url": str, "snippet": str}``. Empty list on
    failure — callers should check and escalate to the next fallback tier.
    """
    query = (query or "").strip()
    if not query:
        return []
    try:
        from ddgs import DDGS  # imported lazily — heavy + network-y
    except Exception as exc:  # noqa: BLE001
        log.warning("ddgs import failed (%s)", exc)
        return []

    results: list[dict[str, str]] = []
    try:
        with DDGS() as ddgs:
            for hit in ddgs.text(query, max_results=max_results) or []:
                url = hit.get("href") or hit.get("url") or ""
                title = (hit.get("title") or "").strip()
                snippet = (hit.get("body") or hit.get("snippet") or "").strip()
                if url and title:
                    results.append({"title": title, "url": url, "snippet": snippet})
    except Exception as exc:  # noqa: BLE001 — fallback chain by design
        log.warning("ddg_search(%r) failed: %s", query, exc)
        return []
    return results


# ── Scrape ───────────────────────────────────────────────────────────────────

_WHITESPACE_RE = re.compile(r"\s+")
_MAX_SCRAPED_CHARS = 6000  # plenty for a summarizer, bounded so prompts stay small


def scrape_url(url: str, *, timeout: int = 8) -> str:
    """Fetch ``url`` and return cleaned main-body text.

    Drops script/style/nav/footer/aside/form. Returns up to
    ``_MAX_SCRAPED_CHARS`` characters. Empty string on any failure — the
    caller is responsible for falling forward to the next result.
    """
    try:
        resp = safe_fetch_url(
            url,
            timeout=timeout,
            allowed_content_types=HTML_CONTENT_TYPES,
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("scrape_url(%s) fetch failed: %s", url, exc)
        return ""

    try:
        soup = BeautifulSoup(resp.text, "lxml")
    except Exception as exc:  # noqa: BLE001
        log.debug("scrape_url(%s) parse failed: %s", url, exc)
        return ""

    for tag in soup(["script", "style", "nav", "footer", "aside", "form", "noscript"]):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text(separator=" ", strip=True)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text[:_MAX_SCRAPED_CHARS]


# ── Summarize ────────────────────────────────────────────────────────────────

_DEFAULT_SUMMARIZER_PROMPT = (
    "You are a terse factual summarizer. Given raw web page text, write a "
    "single short paragraph (≤ 80 words) covering only the facts directly "
    "relevant to the user's question. No fluff, no opinions, no links."
)


def summarize(text: str, *, context_hint: str = "") -> str:
    """Return a short summary of ``text``.

    Tries the LLM at ``SUMMARIZER_URL`` first; on any failure (no env,
    timeout, bad JSON) falls back to an extractive summary (first 3
    sentences, capped at 500 chars) so callers never get an empty string
    when they had scraped text.
    """
    text = (text or "").strip()
    if not text:
        return ""

    llm_url = os.getenv("SUMMARIZER_URL", "").strip()
    if llm_url:
        try:
            return _summarize_llm(text, context_hint=context_hint, base_url=llm_url)
        except Exception as exc:  # noqa: BLE001
            log.warning("LLM summarize failed (%s); using extractive", exc)

    return _extractive_summary(text)


def _summarize_llm(text: str, *, context_hint: str, base_url: str) -> str:
    from openai import OpenAI  # lazy import — optional in CI

    model = os.getenv("SUMMARIZER_MODEL", "gpt-4o-mini")
    api_key = os.getenv("SUMMARIZER_API_KEY", "not-needed")
    client = OpenAI(base_url=base_url.rstrip("/"), api_key=api_key, timeout=15.0)

    user = (
        f"User question: {context_hint}\n\n"
        f"Web page text (may be truncated):\n{text[:4000]}"
        if context_hint
        else f"Web page text:\n{text[:4000]}"
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _DEFAULT_SUMMARIZER_PROMPT},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=200,
    )
    content = (resp.choices[0].message.content or "").strip()
    if not content:
        raise DdgFallbackUnavailable("LLM returned empty content")
    return content


def _extractive_summary(text: str, *, max_sentences: int = 3, max_chars: int = 500) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    picked: list[str] = []
    for s in sentences:
        s = s.strip()
        if len(s) < 20:  # skip nav-crumbs and ultra-short fragments
            continue
        picked.append(s)
        if len(picked) >= max_sentences:
            break
    summary = " ".join(picked) if picked else text[:max_chars]
    return summary[:max_chars].strip()


# ── High-level helper ────────────────────────────────────────────────────────


def ddg_fallback_summary(
    query: str,
    *,
    context_hint: str = "",
    max_results: int = 3,
) -> dict[str, Any]:
    """Search → scrape top N → summarize the first scrapeable result.

    Returns ``{"summary": str, "sources": [{title,url}], "raw_excerpt": str}``.
    Raises :class:`DdgFallbackUnavailable` if search returned nothing or
    every scrape came back empty — callers should then fall through to
    their bundled evergreen tier.
    """
    hits = ddg_search(query, max_results=max_results)
    if not hits:
        raise DdgFallbackUnavailable(f"ddg search empty for {query!r}")

    sources: list[dict[str, str]] = []
    chosen_text = ""
    for hit in hits:
        sources.append({"title": hit["title"], "url": hit["url"]})
        if chosen_text:
            continue  # still record the source, but only scrape the first good one
        body = scrape_url(hit["url"])
        if body:
            chosen_text = body

    if not chosen_text:
        # Last-ditch: stitch snippets together so we at least return something.
        chosen_text = " ".join(h.get("snippet", "") for h in hits).strip()

    if not chosen_text:
        raise DdgFallbackUnavailable(f"no scrapeable content for {query!r}")

    summary = summarize(chosen_text, context_hint=context_hint or query)
    return {
        "summary": summary,
        "sources": sources,
        "raw_excerpt": chosen_text[:1000],
    }
