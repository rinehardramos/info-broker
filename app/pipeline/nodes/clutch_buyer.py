"""Clutch Buyer Reviews node — scrape reviewer (buyer/client) info from Clutch company pages."""

from __future__ import annotations

import asyncio
import logging
import re

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "Clutch buyer reviews reveal real SME executives who purchased IT services — direct proof of outsourcing need"
_CLUTCH_BASE = "https://clutch.co"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class ClutchBuyerNode:
    node_type = "clutch_buyer"
    display_name = "Clutch Buyer Reviews"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "company_url": {
                "type": "string",
                "title": "Clutch Company Profile URL",
                "description": (
                    "Full Clutch profile URL, e.g. https://clutch.co/profile/acme-corp. "
                    "Leave blank to search by location/service_type instead."
                ),
            },
            "location": {
                "type": "string",
                "title": "Location",
                "default": "Philippines",
            },
            "service_type": {
                "type": "string",
                "title": "Service Type",
                "default": "IT Services",
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 20,
                "minimum": 1,
                "maximum": 100,
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        company_url = config.get("company_url", "").strip()
        location = config.get("location", "Philippines")
        service_type = config.get("service_type", "IT Services")
        max_results = int(config.get("max_results", 20))

        loop = asyncio.get_running_loop()

        # If a direct company URL is given, scrape it; otherwise scrape reviews
        # across the top companies for the given location/service_type.
        if company_url:
            profile_urls = [company_url]
        else:
            # Resolve profile URLs from the listing page
            profile_urls = await loop.run_in_executor(
                None, _resolve_profile_urls, location, service_type, max_results
            )

        results: list[dict] = []
        for url in profile_urls:
            reviews = await loop.run_in_executor(
                None, _fetch_reviews_for_profile, url, max_results
            )
            results.extend(reviews)
            if len(results) >= max_results:
                break

        return results[:max_results]


# ---------------------------------------------------------------------------
# Profile URL discovery
# ---------------------------------------------------------------------------

def _resolve_profile_urls(location: str, service_type: str, max_results: int) -> list[str]:
    """Fetch the Clutch listing page and collect company profile URLs."""
    import httpx

    location_slug = location.lower().replace(" ", "-")
    service_slug = service_type.lower().replace(" ", "-")
    listing_url = f"{_CLUTCH_BASE}/{service_slug}/{location_slug}"

    log.info("clutch_buyer: fetching listing page %s", listing_url)
    try:
        with httpx.Client(follow_redirects=True, timeout=20) as client:
            resp = client.get(listing_url, headers=_BROWSER_HEADERS)
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:
        log.warning("clutch_buyer: failed to fetch listing page: %s", exc)
        return []

    # Extract /profile/... URLs
    profile_paths = re.findall(r'href="(/profile/[^"#?]+)"', html)
    seen: set[str] = set()
    urls: list[str] = []
    for path in profile_paths:
        full = f"{_CLUTCH_BASE}{path}"
        if full not in seen:
            seen.add(full)
            urls.append(full)
        if len(urls) >= max_results:
            break

    return urls


# ---------------------------------------------------------------------------
# Review scraper
# ---------------------------------------------------------------------------

def _fetch_reviews_for_profile(profile_url: str, max_results: int) -> list[dict]:
    """Scrape buyer reviews from a Clutch company profile page."""
    import httpx

    reviews_url = profile_url.rstrip("/") + "#reviews"
    log.info("clutch_buyer: scraping reviews from %s", reviews_url)

    try:
        with httpx.Client(follow_redirects=True, timeout=25) as client:
            resp = client.get(reviews_url, headers=_BROWSER_HEADERS)
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:
        log.warning("clutch_buyer: failed to fetch reviews from %s: %s", profile_url, exc)
        return [{"error": str(exc), "source": "clutch_buyer", "profile_url": profile_url}]

    return _parse_review_html(html, profile_url)[:max_results]


def _parse_review_html(html: str, profile_url: str) -> list[dict]:
    """Extract reviewer (buyer) info from Clutch profile review HTML."""
    results: list[dict] = []

    # Clutch review blocks are typically <div class="review..."> or <li class="review...">
    review_blocks = re.findall(
        r'<(?:div|li|article)[^>]+class="[^"]*review[^"]*"[^>]*>(.*?)</(?:div|li|article)>',
        html,
        re.DOTALL | re.IGNORECASE,
    )

    if not review_blocks:
        # Broader fallback: any block that contains reviewer info signals
        review_blocks = re.findall(
            r'<div[^>]+class="[^"]*reviewer[^"]*"[^>]*>(.*?)</div>',
            html,
            re.DOTALL | re.IGNORECASE,
        )

    for block in review_blocks:
        reviewer_name = _extract_text(
            re.search(r'<span[^>]+class="[^"]*reviewer[_-]?name[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        ) or _extract_text(
            re.search(r'<strong[^>]*>(.*?)</strong>', block, re.DOTALL)
        )

        reviewer_title = _extract_text(
            re.search(r'<span[^>]+class="[^"]*reviewer[_-]?title[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        ) or _extract_text(
            re.search(r'<p[^>]+class="[^"]*title[^"]*"[^>]*>(.*?)</p>', block, re.DOTALL)
        )

        reviewer_company = _extract_text(
            re.search(r'<span[^>]+class="[^"]*reviewer[_-]?company[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        ) or _extract_text(
            re.search(r'<span[^>]+class="[^"]*company[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        )

        reviewer_industry = _extract_text(
            re.search(r'<span[^>]+class="[^"]*industry[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        )

        project_summary = _extract_text(
            re.search(r'<p[^>]+class="[^"]*summary[^"]*"[^>]*>(.*?)</p>', block, re.DOTALL)
        ) or _extract_text(
            re.search(r'<div[^>]+class="[^"]*project[^"]*"[^>]*>(.*?)</div>', block, re.DOTALL)
        )

        rating_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:/\s*5)?(?:\s*stars?)?', block)
        rating = float(rating_match.group(1)) if rating_match else None

        date_match = re.search(
            r'<span[^>]+class="[^"]*date[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL
        ) or re.search(r'(\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})', block)
        review_date = _strip_tags(date_match.group(1)) if date_match else ""

        # Skip empty blocks
        if not reviewer_name and not reviewer_company:
            continue

        results.append({
            "reviewer_name": reviewer_name.strip(),
            "reviewer_title": reviewer_title.strip(),
            "reviewer_company": reviewer_company.strip(),
            "reviewer_industry": reviewer_industry.strip(),
            "project_summary": project_summary.strip(),
            "rating": rating,
            "review_date": review_date.strip(),
            "profile_url": profile_url,
            "source": "clutch_buyer",
        })

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_text(match: re.Match | None) -> str:
    if match is None:
        return ""
    return _strip_tags(match.group(1))


def _strip_tags(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
