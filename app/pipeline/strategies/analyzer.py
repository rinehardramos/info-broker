"""Post-run pivot analyzer — maps tool calls to pivot patterns and generates overlay signals."""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# Import DB helpers at module level so patch targets resolve correctly in tests.
# Falls back to no-ops if the DB layer is unavailable (e.g. unit-test environments).
try:
    from app.routers.v3.db import execute, fetch_one
except Exception:  # pragma: no cover
    def execute(query: str, params: tuple = ()) -> None:  # type: ignore[misc]
        log.warning("execute stub called — DB not available")

    def fetch_one(query: str, params: tuple = ()) -> dict | None:  # type: ignore[misc]
        log.warning("fetch_one stub called — DB not available")
        return None

# Maps tool names to the selector type they pivot FROM
PIVOT_TOOL_MAP: dict[str, str] = {
    "linkedin_profile": "full_name",
    "apollo_zoominfo": "full_name",
    "facebook_pages": "full_name",
    "instagram_profile": "full_name",
    "twitter_search": "full_name",
    "ddg_search": "full_name",
    "web_crawl": "full_name",
    "web_search_fetch": "full_name",
    "google_news": "full_name",
    "hunter_io": "domain",
    "whois_lookup": "domain",
    "shodan_search": "domain",
    "hibp_lookup": "email",
    "smtp_verifier": "email",
    "email_enumerator": "full_name",
    "reverse_lookup": "email",
    "username_enumerator": "username",
    "phone_osint": "phone",
    "messaging_check": "phone",
    "pep_sanctions_screen": "full_name",
    "adverse_media": "full_name",
    "exif_extractor": "photo",
    "document_search": "full_name",
    "face_search": "photo",
    "crypto_tracer": "crypto_wallet",
    "ph_sec_dti": "full_name",
    "opencorporates": "full_name",
    "sec_edgar": "full_name",
}


def map_tool_to_pivot(tool_name: str) -> tuple[str, str]:
    """Return (selector_type, pivot_pattern_string) for a tool."""
    clean = tool_name.replace("run_", "")
    selector = PIVOT_TOOL_MAP.get(clean, "unknown")
    return selector, f"{selector} -> {clean}"


def calculate_yield_rate(findings_count: int, tool_calls: int) -> float:
    """findings_count / max(tool_calls, 1)."""
    return findings_count / max(tool_calls, 1)


def determine_overlay_type(yield_rate: float, findings_count: int) -> str | None:
    """
    Determine the overlay signal type based on yield and findings.
    Returns 'reinforce', 'prune', 'discover', or None (no signal).
    """
    if yield_rate >= 0.5 and findings_count >= 2:
        return "reinforce"
    if yield_rate == 0.0 and findings_count == 0:
        return "prune"
    # Weak positive signal — not enough to reinforce, but worth noting
    if findings_count == 1 and yield_rate > 0:
        return "discover"
    return None


async def analyze_run_pivots(run_id: str, query: str, result: dict[str, Any]) -> list[dict]:
    """
    Main entry point. Analyze tool calls from a research run,
    map to pivot patterns, generate overlay signals, upsert to DB.
    """
    entity_type = result.get("entity_type", "person")
    tree = result.get("tree", {})
    branches = tree.get("branches", [])

    if not branches:
        log.debug("analyze_run_pivots: no branches in result tree")
        return []

    overlays: list[dict] = []

    for branch in branches:
        tool_name = branch.get("tool", "")
        result_count = int(branch.get("result_count", 0))

        if not tool_name:
            continue

        selector_type, pivot_pattern = map_tool_to_pivot(tool_name)
        yield_rate = calculate_yield_rate(result_count, 1)  # 1 call per branch entry
        overlay_type = determine_overlay_type(yield_rate, result_count)

        if overlay_type is None:
            continue

        overlay = {
            "entity_type": entity_type,
            "selector_type": selector_type,
            "pivot_pattern": pivot_pattern,
            "overlay_type": overlay_type,
            "yield_rate": yield_rate,
            "run_count": 1,
        }
        overlays.append(overlay)
        _upsert_overlay(overlay)

    return overlays


def _upsert_overlay(overlay: dict) -> None:
    """Upsert an overlay signal to the database using select-then-update/insert pattern."""
    try:
        existing = fetch_one(
            """SELECT id, yield_rate, run_count FROM investigation_strategy_overlays
            WHERE entity_type = %s AND selector_type = %s AND pivot_pattern = %s""",
            (overlay["entity_type"], overlay["selector_type"], overlay["pivot_pattern"]),
        )
        if existing:
            new_yield = 0.7 * existing["yield_rate"] + 0.3 * overlay["yield_rate"]
            execute(
                """UPDATE investigation_strategy_overlays
                SET yield_rate = %s, overlay_type = %s,
                    run_count = run_count + 1, last_validated = now(), updated_at = now()
                WHERE id = %s""",
                (new_yield, overlay["overlay_type"], str(existing["id"])),
            )
        else:
            execute(
                """INSERT INTO investigation_strategy_overlays
                    (entity_type, selector_type, pivot_pattern, overlay_type, yield_rate, run_count)
                VALUES (%s, %s, %s, %s, %s, 1)""",
                (overlay["entity_type"], overlay["selector_type"], overlay["pivot_pattern"],
                 overlay["overlay_type"], overlay["yield_rate"]),
            )
    except Exception as exc:
        log.warning("Overlay upsert failed: %s", exc)
