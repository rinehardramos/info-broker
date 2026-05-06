"""Clutch/GoodFirms Reviews node — reverse-lookup SME executives via published reviews."""

from __future__ import annotations

import asyncio
import logging
import re

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_CLUTCH_BASE = "https://clutch.co"
_GOODFIRMS_BASE = "https://www.goodfirms.co"


class ClutchGoodfirmsNode:
    node_type = "clutch_goodfirms"
    display_name = "Clutch/GoodFirms Reviews"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "platform": {
                "type": "string",
                "title": "Platform",
                "enum": ["clutch", "goodfirms", "both"],
                "default": "clutch",
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

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        platform = config.get("platform", "clutch")
        location = config.get("location", "Philippines")
        service_type = config.get("service_type", "IT Services")
        max_results = int(config.get("max_results", 20))

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._run_sync, platform, location, service_type, max_results
        )

    def _run_sync(
        self, platform: str, location: str, service_type: str, max_results: int
    ) -> list[dict]:
        import httpx

        results: list[dict] = []

        if platform in ("clutch", "both"):
            try:
                results.extend(
                    _fetch_clutch(location, service_type, max_results)
                )
            except Exception as exc:
                log.warning("ClutchGoodfirmsNode: Clutch fetch failed: %s", exc)
                results.append({"error": str(exc), "source": "clutch"})

        if platform in ("goodfirms", "both"):
            try:
                results.extend(
                    _fetch_goodfirms(location, service_type, max_results)
                )
            except Exception as exc:
                log.warning("ClutchGoodfirmsNode: GoodFirms fetch failed: %s", exc)
                results.append({"error": str(exc), "source": "goodfirms"})

        return results[:max_results]


# ---------------------------------------------------------------------------
# Clutch scraper
# ---------------------------------------------------------------------------

def _fetch_clutch(location: str, service_type: str, max_results: int) -> list[dict]:
    import httpx

    location_slug = location.lower().replace(" ", "-")
    service_slug = service_type.lower().replace(" ", "-")
    url = f"{_CLUTCH_BASE}/{service_slug}/{location_slug}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    log.info("ClutchGoodfirmsNode: fetching Clutch listings from %s", url)
    with httpx.Client(follow_redirects=True, timeout=20) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        html = resp.text

    return _parse_clutch_html(html, url)[:max_results]


def _parse_clutch_html(html: str, base_url: str) -> list[dict]:
    """Extract company listing cards from Clutch HTML."""
    results: list[dict] = []

    # Match company listing blocks — Clutch uses li.provider-row or article blocks
    # Extract company names via typical patterns in their HTML
    company_blocks = re.findall(
        r'<li[^>]+class="[^"]*provider[^"]*"[^>]*>(.*?)</li>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not company_blocks:
        # Fallback: try to grab any structured company data
        company_blocks = re.findall(
            r'<div[^>]+class="[^"]*company-info[^"]*"[^>]*>(.*?)</div>',
            html,
            re.DOTALL | re.IGNORECASE,
        )

    for block in company_blocks:
        name = _extract_text(re.search(r'<h3[^>]*>(.*?)</h3>', block, re.DOTALL))
        if not name:
            name = _extract_text(re.search(r'<a[^>]+class="[^"]*company_info[^"]*"[^>]*>(.*?)</a>', block, re.DOTALL))
        if not name:
            continue

        href_match = re.search(r'href="(/profile/[^"]+)"', block)
        company_url = f"{_CLUTCH_BASE}{href_match.group(1)}" if href_match else ""

        rating_match = re.search(r'(\d+\.\d+)\s*(?:rating|stars?)?', block)
        rating = float(rating_match.group(1)) if rating_match else None

        reviews_match = re.search(r'(\d+)\s*(?:reviews?|ratings?)', block, re.IGNORECASE)
        num_reviews = int(reviews_match.group(1)) if reviews_match else None

        location_match = re.search(r'<span[^>]+class="[^"]*location[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        location = _strip_tags(location_match.group(1)) if location_match else ""

        focus_match = re.search(r'<span[^>]+class="[^"]*focus[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        service_focus = _strip_tags(focus_match.group(1)) if focus_match else ""

        results.append({
            "company": name.strip(),
            "url": company_url,
            "rating": rating,
            "num_reviews": num_reviews,
            "location": location.strip(),
            "service_focus": service_focus.strip(),
            "source": "clutch",
        })

    return results


# ---------------------------------------------------------------------------
# GoodFirms scraper
# ---------------------------------------------------------------------------

def _fetch_goodfirms(location: str, service_type: str, max_results: int) -> list[dict]:
    import httpx

    location_slug = location.lower().replace(" ", "-")
    service_slug = service_type.lower().replace(" ", "-")
    url = f"{_GOODFIRMS_BASE}/it-companies/{location_slug}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    log.info("ClutchGoodfirmsNode: fetching GoodFirms listings from %s", url)
    with httpx.Client(follow_redirects=True, timeout=20) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        html = resp.text

    return _parse_goodfirms_html(html)[:max_results]


def _parse_goodfirms_html(html: str) -> list[dict]:
    """Extract company listing cards from GoodFirms HTML."""
    results: list[dict] = []

    company_blocks = re.findall(
        r'<div[^>]+class="[^"]*company-box[^"]*"[^>]*>(.*?)</div>\s*</div>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not company_blocks:
        company_blocks = re.findall(
            r'<li[^>]+class="[^"]*company[^"]*"[^>]*>(.*?)</li>',
            html,
            re.DOTALL | re.IGNORECASE,
        )

    for block in company_blocks:
        name = _extract_text(re.search(r'<h4[^>]*>(.*?)</h4>', block, re.DOTALL))
        if not name:
            name = _extract_text(re.search(r'<h3[^>]*>(.*?)</h3>', block, re.DOTALL))
        if not name:
            continue

        href_match = re.search(r'href="(/it-companies/[^"]+)"', block)
        company_url = f"{_GOODFIRMS_BASE}{href_match.group(1)}" if href_match else ""

        rating_match = re.search(r'(\d+\.\d+)', block)
        rating = float(rating_match.group(1)) if rating_match else None

        reviews_match = re.search(r'(\d+)\s*(?:reviews?|ratings?)', block, re.IGNORECASE)
        num_reviews = int(reviews_match.group(1)) if reviews_match else None

        location_match = re.search(r'<span[^>]+class="[^"]*location[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        location = _strip_tags(location_match.group(1)) if location_match else ""

        results.append({
            "company": name.strip(),
            "url": company_url,
            "rating": rating,
            "num_reviews": num_reviews,
            "location": location.strip(),
            "service_focus": "",
            "source": "goodfirms",
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
