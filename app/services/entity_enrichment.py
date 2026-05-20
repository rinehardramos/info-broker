"""Lazy enrichment of a candidate name into a "physical profile" payload.

Cascade strategy: each free provider is best-effort and additive. We fire them
in parallel and union the results, then optionally boost with Serper if a key
is configured. The point is to give a useful payload even with zero API keys.

Public API:
    classify_entity_type(name, context) -> str
    build_profile(name, context, entity_type=None, evidence_urls=None) -> dict

Profile shape:
    {
        "entity_type": "person|place|item|event|other",
        "images":   [{"url", "alt"?, "source"?}],
        "links":    {"social": [...], "official": [...]},
        "geo":      None | {"lat", "lng", "address"?},
        "fetched_at": iso8601,
    }
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote, urlparse

import httpx

log = logging.getLogger(__name__)

_VALID_TYPES = {"person", "place", "item", "event", "other"}
_HTTP_TIMEOUT = httpx.Timeout(6.0, connect=3.0)
_UA = "info-broker/1.0 (research; +https://github.com/anthropics/info-broker)"
# Nominatim ToS requires a real contact; we honor by setting a UA. Heavy users
# should configure their own ENRICHMENT_UA env var.
_NOMINATIM_UA = os.getenv("ENRICHMENT_UA", _UA)

_SOCIAL_DOMAINS = {
    "twitter.com":      "twitter",
    "x.com":            "twitter",
    "instagram.com":    "instagram",
    "facebook.com":     "facebook",
    "linkedin.com":     "linkedin",
    "tiktok.com":       "tiktok",
    "youtube.com":      "youtube",
    "youtu.be":         "youtube",
    "reddit.com":       "reddit",
    "github.com":       "github",
    "threads.net":      "threads",
}

_OFFICIAL_HINTS = (
    "wikipedia.org", "wiki/",
    "imdb.com", "tmdb.org",
    "britannica.com",
    "official",
)


# ---------------------------------------------------------------------------
# Entity-type classification (unchanged — small LLM call)
# ---------------------------------------------------------------------------

_CLASSIFY_PROMPT = """\
Classify the following entity into one of these categories, output ONLY the single word category:
  person, place, item, event, other

Definitions:
- person: a named individual (musician, politician, athlete, fictional character)
- place: a named geographic location (city, landmark, venue, building)
- item: a tangible product, brand, artwork, vehicle, food, song/album, film
- event: a named happening (concert, war, treaty, conference, championship)
- other: abstract concepts, organizations, theories, generic terms

Entity name: {name}
Context (the user's original question): {context}

Reply with one word only:"""


async def _llm_classify(prompt: str, model: str) -> str:
    claude_bin = shutil.which("claude") or "/usr/local/bin/claude"
    if os.path.isfile(claude_bin):
        try:
            spawn_env = {**os.environ, "CLAUDE_CODE_HEADLESS": "1"}
            fresh_key = ""
            try:
                from app.routers.v3.db import fetch_one as _fetch
                _row = _fetch("SELECT value FROM core_settings WHERE key = 'anthropic_api_key'", ())
                if _row and _row["value"] and _row["value"].startswith("sk-ant-api"):
                    fresh_key = _row["value"]
            except Exception:
                pass
            if not fresh_key:
                env_key = os.getenv("ANTHROPIC_API_KEY", "")
                if env_key.startswith("sk-ant-api"):
                    fresh_key = env_key
            if fresh_key:
                spawn_env["ANTHROPIC_API_KEY"] = fresh_key
            else:
                spawn_env.pop("ANTHROPIC_API_KEY", None)
            cmd = [claude_bin, "--output-format", "text", "--model", model, "--max-turns", "1"]
            if fresh_key:
                cmd.append("--bare")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                env=spawn_env,
            )
            out, _err = await asyncio.wait_for(proc.communicate(input=prompt.encode()), timeout=45)
            if proc.returncode == 0 and out:
                return out.decode().strip()
        except Exception as exc:
            log.warning("entity_enrichment: Claude Code failed: %s", exc)

    try:
        import anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            try:
                from app.routers.v3.db import fetch_one
                row = fetch_one("SELECT value FROM core_settings WHERE key = 'anthropic_api_key'", ())
                if row and row.get("value"):
                    api_key = row["value"]
            except Exception:
                pass
        if not api_key:
            return ""
        client = anthropic.Anthropic(api_key=api_key)
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, lambda: client.messages.create(
            model=model, max_tokens=20,
            messages=[{"role": "user", "content": prompt}],
        ))
        return (resp.content[0].text if resp.content else "").strip()
    except Exception as exc:
        log.warning("entity_enrichment: Anthropic SDK failed: %s", exc)
        return ""


async def classify_entity_type(name: str, context: str) -> str:
    try:
        from app.llm_models import general_model
        model = general_model()
    except Exception:
        model = "claude-sonnet-4-6"
    prompt = _CLASSIFY_PROMPT.format(name=name[:120], context=(context or "")[:280])
    raw = (await _llm_classify(prompt, model)).strip().lower()
    for token in re.findall(r"[a-z]+", raw):
        if token in _VALID_TYPES:
            return token
    return "other"


# ---------------------------------------------------------------------------
# Free-tier providers — best-effort, no keys required
# ---------------------------------------------------------------------------

async def _wiki_resolve_title(client: httpx.AsyncClient, name: str) -> Optional[str]:
    """Resolve a free-form name to a canonical Wikipedia title via opensearch.

    The REST summary endpoint is title-exact, so "Jang Wonyoung" misses the
    actual page "Jang Won-young". Opensearch is forgiving and returns the
    closest match.
    """
    try:
        r = await client.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "opensearch",
                "search": name,
                "limit": 1,
                "namespace": 0,
                "format": "json",
            },
            headers={"User-Agent": _UA},
        )
        if r.status_code != 200:
            return None
        data = r.json() or []
        titles = data[1] if len(data) > 1 else []
        return titles[0] if titles else None
    except Exception:
        return None


async def _wiki_summary(client: httpx.AsyncClient, name: str) -> dict:
    """Wikipedia REST summary. Returns thumbnail + page URL + extract."""
    try:
        canonical = await _wiki_resolve_title(client, name)
        title_raw = canonical or name
        title = quote(title_raw.strip().replace(" ", "_"))
        r = await client.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}",
            headers={"User-Agent": _UA},
        )
        if r.status_code != 200:
            return {}
        data = r.json() or {}
        out: dict = {}
        thumb = (data.get("originalimage") or {}).get("source") or (data.get("thumbnail") or {}).get("source")
        if thumb:
            out["images"] = [{"url": thumb, "alt": data.get("title", name), "source": "wikipedia"}]
        page_url = (data.get("content_urls") or {}).get("desktop", {}).get("page")
        if page_url:
            out["official"] = [{"label": "Wikipedia", "url": page_url, "title": data.get("title", name)}]
        if data.get("extract"):
            out["extract"] = data["extract"]
        return out
    except Exception as exc:
        log.debug("wiki_summary failed for %s: %s", name, exc)
        return {}


async def _nominatim_geo(client: httpx.AsyncClient, name: str) -> Optional[dict]:
    """OpenStreetMap geocoder. Returns lat/lng/address + native/English names.

    `namedetails=1` adds the multilingual name table so we can surface both
    the place's native script and an English transliteration (e.g. "天安门"
    + "Tiananmen Square").
    """
    try:
        r = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": name,
                "format": "json",
                "limit": 1,
                "accept-language": "en",
                "namedetails": "1",
            },
            headers={"User-Agent": _NOMINATIM_UA},
        )
        if r.status_code != 200:
            return None
        rows = r.json() or []
        if not rows:
            return None
        row = rows[0]
        try:
            lat = float(row["lat"])
            lng = float(row["lon"])
        except (KeyError, ValueError):
            return None

        names = row.get("namedetails") or {}
        # Prefer `name:en` for the English label, fall back to the default name.
        english_name = names.get("name:en") or names.get("name") or row.get("display_name")
        # Native: the unprefixed `name` field (in the place's primary script).
        # Only surface as "native" if it differs from the English label.
        native_name = names.get("name")
        if native_name and english_name and native_name.strip() == (english_name or "").strip():
            native_name = None

        return {
            "lat": lat,
            "lng": lng,
            "address":     row.get("display_name"),
            "name_en":     english_name,
            "name_native": native_name,
        }
    except Exception as exc:
        log.debug("nominatim failed for %s: %s", name, exc)
        return None


async def _ddg_instant(client: httpx.AsyncClient, name: str) -> dict:
    """DuckDuckGo Instant Answer. Returns image + abstract + a few related links."""
    try:
        r = await client.get(
            "https://api.duckduckgo.com/",
            params={"q": name, "format": "json", "no_html": "1", "skip_disambig": "1"},
            headers={"User-Agent": _UA},
        )
        if r.status_code != 200:
            return {}
        data = r.json() or {}
        out: dict = {}
        if data.get("Image"):
            img = data["Image"]
            if img.startswith("/"):
                img = "https://duckduckgo.com" + img
            out["images"] = [{"url": img, "alt": data.get("Heading", name), "source": "ddg"}]
        if data.get("AbstractURL"):
            out["official"] = [{
                "label": data.get("AbstractSource") or "DuckDuckGo",
                "url":   data["AbstractURL"],
                "title": data.get("Heading", name),
            }]
        return out
    except Exception as exc:
        log.debug("ddg failed for %s: %s", name, exc)
        return {}


def _classify_link(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower().lstrip("www.")
    except Exception:
        return ""
    for dom in _SOCIAL_DOMAINS:
        if dom in host:
            return "social"
    for hint in _OFFICIAL_HINTS:
        if hint in url.lower():
            return "official"
    return ""


def _social_platform(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().lstrip("www.")
    for dom, platform in _SOCIAL_DOMAINS.items():
        if dom in host:
            return platform
    return "link"


def _official_label(url: str) -> str:
    if "wikipedia.org" in url:
        return "Wikipedia"
    if "imdb.com" in url:
        return "IMDb"
    if "britannica.com" in url:
        return "Britannica"
    return urlparse(url).hostname or "Official"


async def _og_image_for_url(client: httpx.AsyncClient, url: str) -> Optional[dict]:
    """Reuse the existing /v3/evidence/preview endpoint logic. We hit it
    via http rather than re-import its parser to keep this module decoupled.
    Falls back to direct HEAD if the preview endpoint fails.
    """
    # Reuse the in-process preview helpers directly — same code path as the
    # frontend would use, avoids a self-loopback HTTP call.
    try:
        from app.routers.v3.evidence import _fetch_preview as _direct_preview
        data = await _direct_preview(url)
        out: dict = {}
        if data.get("image"):
            out["images"] = [{"url": data["image"], "alt": data.get("title", ""), "source": "og"}]
        return out
    except Exception as exc:
        log.debug("og_image preview failed for %s: %s", url, exc)
        return None


async def _aggregate_og_images(client: httpx.AsyncClient, evidence_urls: list[str]) -> dict:
    """For each evidence URL, fetch its og:image. Cap at first 4 unique."""
    if not evidence_urls:
        return {}
    seen: set[str] = set()
    images: list[dict] = []
    # Fire in parallel but cap concurrency loosely; httpx client handles pooling.
    coros = [_og_image_for_url(client, u) for u in evidence_urls[:6]]
    results = await asyncio.gather(*coros, return_exceptions=True)
    for r in results:
        if not isinstance(r, dict) or not r:
            continue
        for img in r.get("images") or []:
            url = img.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            images.append(img)
            if len(images) >= 4:
                break
    return {"images": images}


# ---------------------------------------------------------------------------
# Optional booster: Serper images (paid, only used if a key is configured)
# ---------------------------------------------------------------------------

def _serper_sync(query: str, max_results: int) -> list[dict]:
    try:
        from app.pipeline.nodes.serper_search import _resolve_api_key, _search_serper
    except Exception:
        return []
    key = _resolve_api_key()
    if not key:
        return []
    try:
        return _search_serper(query, key, max_results, search_type="images") or []
    except Exception as exc:
        log.debug("serper images failed: %s", exc)
        return []


async def _serper_booster(name: str, hint: str) -> dict:
    loop = asyncio.get_running_loop()
    q = f"{name} {hint}".strip()
    rows = await loop.run_in_executor(None, _serper_sync, q, 6)
    images: list[dict] = []
    web_links: list[dict] = []
    for r in rows:
        url = r.get("url")
        if not url:
            continue
        # Image search returns imageUrl in url field already (per _map_result)
        images.append({"url": url, "alt": r.get("title", ""), "source": "serper_images"})
    return {"images": images, "web": web_links}


# ---------------------------------------------------------------------------
# Merge + cap helpers
# ---------------------------------------------------------------------------

def _dedupe_by_url(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for it in items:
        url = it.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(it)
    return out


def _categorize_links(urls: list[str]) -> tuple[list[dict], list[dict]]:
    """Split a flat URL list into (social_chips, official_chips)."""
    social: list[dict] = []
    official: list[dict] = []
    for url in urls:
        kind = _classify_link(url)
        if kind == "social":
            social.append({"platform": _social_platform(url), "url": url})
        elif kind == "official":
            official.append({"label": _official_label(url), "url": url})
    return _dedupe_by_url(social)[:6], _dedupe_by_url(official)[:6]


# ---------------------------------------------------------------------------
# Public entry — cascade
# ---------------------------------------------------------------------------

async def build_profile(
    name: str,
    context: str,
    entity_type: str | None = None,
    evidence_urls: list[str] | None = None,
) -> dict[str, Any]:
    """Cascade free providers, optionally boost with Serper. Stable shape."""
    if not entity_type:
        entity_type = await classify_entity_type(name, context)

    hint = {
        "person": "portrait",
        "place":  "landmark photo",
        "item":   "product photo",
        "event":  "event photo",
    }.get(entity_type, "")

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        coros: list = [
            _wiki_summary(client, name),
            _ddg_instant(client, name),
            _aggregate_og_images(client, evidence_urls or []),
        ]
        if entity_type == "place":
            coros.append(_nominatim_geo(client, name))
        else:
            coros.append(asyncio.sleep(0, result=None))  # placeholder slot

        # Run the free cascade in parallel + Serper booster (also async-safe).
        free_results = await asyncio.gather(*coros, return_exceptions=True)
        serper_result = await _serper_booster(name, hint)

    wiki, ddg, og, geo_or_none = (r if not isinstance(r, BaseException) else {} for r in free_results)
    geo = geo_or_none if isinstance(geo_or_none, dict) else None

    # Merge images: wiki > og > ddg > serper. Cap at 8 unique.
    all_images: list[dict] = []
    for src in (wiki, og, ddg, serper_result):
        all_images.extend((src or {}).get("images") or [])
    images = _dedupe_by_url(all_images)[:8]

    # Merge official links from wiki + ddg.
    flat_official_urls: list[str] = []
    for src in (wiki, ddg):
        for entry in (src or {}).get("official") or []:
            flat_official_urls.append(entry["url"])
    social_chips, official_chips = _categorize_links(flat_official_urls)
    # If wiki/ddg provided no explicit official with label, fall back to the
    # entries' own metadata (preserves the human-readable label).
    if not official_chips:
        for src in (wiki, ddg):
            for entry in (src or {}).get("official") or []:
                official_chips.append({"label": entry.get("label") or "Official", "url": entry["url"]})
        official_chips = _dedupe_by_url(official_chips)[:6]

    return {
        "entity_type": entity_type,
        "images":      images,
        "links": {
            "social":   social_chips,
            "official": official_chips,
        },
        "geo":        geo,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
