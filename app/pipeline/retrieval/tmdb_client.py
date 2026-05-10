"""Direct TMDB v3 HTTP client for multi-branch retrieval.

Base URL and key resolution derived from app.pipeline.nodes.tmdb_search
to avoid redeclaring credentials.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Literal

import httpx

log = logging.getLogger(__name__)

# Derive base from the already-committed search URL — no new URL literals
from app.pipeline.nodes.tmdb_search import _TMDB_SEARCH_URL as _SEARCH_TEMPLATE
_TMDB_BASE = _SEARCH_TEMPLATE.replace("/search/{search_type}", "")


def _resolve_key() -> str | None:
    key = os.getenv("TMDB_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one("SELECT value FROM core_settings WHERE key = 'tmdb_api_key'", ())
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


def _parse_year(date_str: str | None) -> int | None:
    if date_str and len(date_str) >= 4:
        try:
            return int(date_str[:4])
        except ValueError:
            pass
    return None


@dataclass
class TMDBTitle:
    tmdb_id: int
    title: str
    year: int | None
    type: Literal["tv", "movie"]
    overview: str
    top_cast: list[str] = field(default_factory=list)
    top_cast_genders: list[int] = field(default_factory=list)


async def _get(path: str, params: dict | None = None) -> dict:
    key = _resolve_key()
    if not key:
        log.warning("tmdb_client: no API key configured, skipping request")
        return {}
    try:
        p: dict = {"language": "en-US"}
        p["api_key"] = key
        if params:
            p.update(params)
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f"{_TMDB_BASE}{path}", params=p)
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        log.warning("tmdb _get(%s) failed: %s", path, exc)
        return {}


async def search_tv(query: str, year_gte: int = 2024) -> list[TMDBTitle]:
    if not _resolve_key():
        return []
    try:
        data = await _get("/search/tv", {"query": query, "page": 1})
        results = []
        for item in data.get("results", [])[:10]:
            year = _parse_year(item.get("first_air_date"))
            if year and year < year_gte:
                continue
            results.append(TMDBTitle(
                tmdb_id=item["id"],
                title=item.get("name") or item.get("original_name") or "",
                year=year,
                type="tv",
                overview=item.get("overview") or "",
            ))
        return results
    except Exception as exc:
        log.warning("tmdb search_tv failed: %s", exc)
        return []


async def get_top_cast(tmdb_id: int, media_type: str = "tv") -> list[dict]:
    if not _resolve_key():
        return []
    try:
        data = await _get(f"/{media_type}/{tmdb_id}/credits")
        return sorted(data.get("cast", []), key=lambda c: c.get("order", 999))[:5]
    except Exception as exc:
        log.warning("tmdb get_top_cast(%s) failed: %s", tmdb_id, exc)
        return []


async def get_person_tv_credits(person_id: int, year_gte: int = 2024) -> list[TMDBTitle]:
    if not _resolve_key():
        return []
    try:
        data = await _get(f"/person/{person_id}/tv_credits")
        results = []
        for item in data.get("cast", []):
            year = _parse_year(item.get("first_air_date"))
            if year and year < year_gte:
                continue
            results.append(TMDBTitle(
                tmdb_id=item["id"],
                title=item.get("name") or item.get("original_name") or "",
                year=year,
                type="tv",
                overview=item.get("overview") or "",
            ))
        return results[:5]
    except Exception as exc:
        log.warning("tmdb get_person_tv_credits(%s) failed: %s", person_id, exc)
        return []


async def search_franchise_cast(franchise_titles: list[str]) -> list[dict]:
    if not _resolve_key():
        return []

    async def _cast_for(title: str) -> list[dict]:
        try:
            data = await _get("/search/movie", {"query": title})
            results = data.get("results", [])
            if not results:
                return []
            credits = await _get(f"/movie/{results[0]['id']}/credits")
            return credits.get("cast", [])[:15]
        except Exception as exc:
            log.warning("franchise cast failed for %s: %s", title, exc)
            return []

    casts = await asyncio.gather(*[_cast_for(t) for t in franchise_titles])
    seen: set[int] = set()
    people = []
    for cast_list in casts:
        for p in cast_list:
            pid = p.get("id")
            # gender==1 is TMDB's code for female — we want actress candidates
            if pid and pid not in seen and p.get("gender") == 1:
                seen.add(pid)
                people.append(p)
    return sorted(people, key=lambda p: p.get("popularity", 0), reverse=True)[:10]
