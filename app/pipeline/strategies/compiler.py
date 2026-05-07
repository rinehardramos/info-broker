"""Strategy compiler — merges seed strategy with learned overlays from DB."""

from __future__ import annotations
import logging
from typing import Any

from app.pipeline.strategies import get_strategy

log = logging.getLogger(__name__)


async def compile_strategy(entity_type: str) -> str:
    """Load seed strategy + DB overlays, merge into final strategy text."""
    seed = get_strategy(entity_type)
    if not seed:
        return ""

    overlays = _fetch_overlays(entity_type)
    if not overlays:
        return seed

    return _merge_overlays(seed, overlays)


def _fetch_overlays(entity_type: str) -> list[dict]:
    """Fetch active overlays from DB. Threshold: run_count >= 2."""
    try:
        from app.routers.v3.db import fetch_all
        rows = fetch_all(
            """SELECT pivot_pattern, overlay_type, yield_rate, run_count, selector_type,
                      category, pinned
            FROM investigation_strategy_overlays
            WHERE entity_type = %s AND run_count >= 2
            ORDER BY yield_rate DESC""",
            (entity_type,),
        )
        return rows or []
    except Exception as exc:
        log.debug("Failed to fetch overlays: %s", exc)
        return []


def _merge_overlays(seed: str, overlays: list[dict]) -> str:
    """Pure function: annotate seed strategy with overlay signals."""
    result = seed
    discovered: list[dict] = []

    for overlay in overlays:
        pivot = overlay["pivot_pattern"]
        otype = overlay["overlay_type"]
        yield_pct = f"{overlay.get('yield_rate', 0) * 100:.0f}%"
        run_count = overlay.get("run_count", 0)

        # Extract the tool name from pivot pattern (e.g., "email -> hibp_lookup" -> "hibp_lookup")
        tool_name = pivot.split(" -> ")[-1] if " -> " in pivot else pivot

        if otype == "reinforce":
            annotation = f" [HIGH PRIORITY - yield {yield_pct}, {run_count} runs]"
            result = _annotate_tool_line(result, tool_name, annotation)

        elif otype == "prune":
            annotation = f" [LOW PRIORITY - yield {yield_pct}, {run_count} runs]"
            result = _annotate_tool_line(result, tool_name, annotation)

        elif otype == "discover":
            discovered.append(overlay)

        elif otype == "upgrade":
            annotation = f" [SENTINEL - high value when found, {run_count} runs]"
            result = _annotate_tool_line(result, tool_name, annotation)

    # Append discovered pivots section
    if discovered:
        result += "\n\n## DISCOVERED PIVOTS (learned from past runs)\n"
        for d in discovered:
            sel = d.get("selector_type", "unknown")
            tool = d["pivot_pattern"].split(" -> ")[-1] if " -> " in d["pivot_pattern"] else d["pivot_pattern"]
            yield_pct = f"{d.get('yield_rate', 0) * 100:.0f}%"
            result += f"- {sel} -> run_{tool} (yield {yield_pct})\n"

    return result


def _annotate_tool_line(text: str, tool_name: str, annotation: str) -> str:
    """Find lines containing the tool name and append annotation (first occurrence only)."""
    lines = text.split("\n")
    annotated = []
    done = False
    for line in lines:
        if not done and tool_name in line and annotation not in line:
            line = line.rstrip() + annotation
            done = True
        annotated.append(line)
    return "\n".join(annotated)
