"""Evidence helpers — OpenGraph unfurl for richer link previews in the UI.

Lazy-fetches an arbitrary URL, parses og: / twitter: / standard meta tags, and
returns a compact preview payload. Used by the EvidenceModal in the frontend
so text-link evidence (e.g. allkpop articles) renders with a thumbnail + title
instead of a bare URL.

Safety:
  * Allow-list http/https only.
  * Block private/loopback IPs after DNS resolution (basic SSRF guard).
  * 8s timeout, 2 MB response cap, follow up to 3 redirects.
  * In-memory LRU cache (1024 entries, 1h TTL) keyed by URL.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
import time
from html import unescape
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.routers.v3.auth import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v3/evidence", tags=["v3-evidence"])

_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL_SECS = 3600
_CACHE_MAX = 1024

_TIMEOUT = httpx.Timeout(8.0, connect=4.0)
_MAX_BYTES = 2 * 1024 * 1024
_UA = "info-broker-evidence-preview/1.0"


def _is_safe_url(url: str) -> bool:
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return False
    if not p.hostname:
        return False
    try:
        addrs = socket.getaddrinfo(p.hostname, None)
    except socket.gaierror:
        return False
    for info in addrs:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    return True


_META_RE = re.compile(
    r"<meta\s+[^>]*?(?:property|name)\s*=\s*[\"\']([^\"\']+)[\"\'][^>]*?content\s*=\s*[\"\']([^\"\']*)[\"\']",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _parse_html(html: str, base_url: str) -> dict[str, Any]:
    metas: dict[str, str] = {}
    for m in _META_RE.finditer(html):
        key = m.group(1).strip().lower()
        val = unescape(m.group(2).strip())
        if key not in metas:
            metas[key] = val

    def first(*keys: str) -> str | None:
        for k in keys:
            if k in metas and metas[k]:
                return metas[k]
        return None

    title = first("og:title", "twitter:title")
    if not title:
        m = _TITLE_RE.search(html)
        if m:
            title = unescape(re.sub(r"\s+", " ", m.group(1)).strip())

    description = first(
        "og:description", "twitter:description", "description",
    )
    image = first("og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src")
    site_name = first("og:site_name", "application-name")

    host = urlparse(base_url).hostname or ""
    return {
        "url":          base_url,
        "title":        title,
        "description":  (description or "")[:600] or None,
        "image":        image,
        "site_name":    site_name or host,
    }


async def _fetch_preview(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(
        timeout=_TIMEOUT,
        follow_redirects=True,
        max_redirects=3,
        headers={"User-Agent": _UA, "Accept": "text/html,*/*;q=0.5"},
    ) as client:
        async with client.stream("GET", url) as resp:
            if resp.status_code >= 400:
                raise HTTPException(status_code=502, detail=f"Upstream {resp.status_code}")
            ctype = (resp.headers.get("content-type") or "").lower()
            if "html" not in ctype and "xml" not in ctype:
                # Non-HTML resource (image, pdf, etc.) — let the client render it
                # directly. We still return the URL so the modal can show it.
                return {"url": str(resp.url), "title": None, "description": None,
                        "image": str(resp.url) if "image" in ctype else None,
                        "site_name": urlparse(str(resp.url)).hostname or ""}
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes():
                chunks.append(chunk)
                total += len(chunk)
                if total > _MAX_BYTES:
                    break
            body = b"".join(chunks).decode("utf-8", errors="replace")
            return _parse_html(body, str(resp.url))


@router.get("/preview")
async def preview(
    url: str = Query(..., min_length=8, max_length=2048),
    _user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    if not _is_safe_url(url):
        raise HTTPException(status_code=400, detail="URL not allowed")
    now = time.time()
    cached = _CACHE.get(url)
    if cached and now - cached[0] < _CACHE_TTL_SECS:
        return cached[1]
    try:
        data = await asyncio.wait_for(_fetch_preview(url), timeout=10.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Upstream timeout")
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("evidence preview failed for %s: %s", url, exc)
        raise HTTPException(status_code=502, detail="Could not fetch preview")
    # Trim cache when it grows too large
    if len(_CACHE) >= _CACHE_MAX:
        oldest_key = min(_CACHE, key=lambda k: _CACHE[k][0])
        _CACHE.pop(oldest_key, None)
    _CACHE[url] = (now, data)
    return data


# ---------------------------------------------------------------------------
# Per-candidate "physical profile" enrichment (images, links, geo)
# ---------------------------------------------------------------------------

import hashlib
import json
from pydantic import BaseModel, Field

from app.routers.v3.db import execute, fetch_one
from app.lib.rate_limit import limiter


class EntityProfileIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    context: str = Field("", max_length=2048)
    run_id: str | None = None
    # Source URLs from the candidate's existing evidence. Used by the
    # enrichment cascade to harvest og:image previews per source.
    evidence_urls: list[str] = Field(default_factory=list, max_length=12)


def _context_hash(context: str) -> str:
    return hashlib.sha256((context or "").strip().lower().encode("utf-8")).hexdigest()[:32]


_CACHE_TTL_DAYS = 30


@router.post("/entity-profile")
@limiter.limit("10/minute")
async def entity_profile(
    request: Request,
    response: Response,
    body: EntityProfileIn,
    _user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    name = body.name.strip()
    ctx_hash = _context_hash(body.context)

    cached = fetch_one(
        """SELECT entity_type, payload, created_at
             FROM entity_profiles
            WHERE name = %s AND context_hash = %s
              AND created_at > now() - interval %s""",
        (name, ctx_hash, f"{_CACHE_TTL_DAYS} days"),
    )
    if cached:
        try:
            payload = cached["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            return payload
        except Exception:
            log.warning("entity_profile cache parse failed for %s, recomputing", name)

    from app.services.entity_enrichment import build_profile
    try:
        payload = await asyncio.wait_for(
            build_profile(name=name, context=body.context, evidence_urls=body.evidence_urls),
            timeout=45.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Enrichment timeout")
    except Exception as exc:  # pragma: no cover
        log.warning("entity_profile build failed for %s: %s", name, exc)
        raise HTTPException(status_code=502, detail="Enrichment failed")

    try:
        execute(
            """INSERT INTO entity_profiles (name, context_hash, entity_type, payload)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (name, context_hash) DO UPDATE
                 SET entity_type = EXCLUDED.entity_type,
                     payload     = EXCLUDED.payload,
                     created_at  = now()""",
            (name, ctx_hash, payload.get("entity_type"), json.dumps(payload)),
        )
    except Exception as exc:
        log.warning("entity_profile cache write failed (non-fatal): %s", exc)

    return payload
