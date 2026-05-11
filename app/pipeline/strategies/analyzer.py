"""Post-run pivot analyzer — maps tool calls to pivot patterns and generates overlay signals."""
from __future__ import annotations

import asyncio
import json
import logging
import re
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
    "multi_search": "full_name",
    "ddg_search": "full_name",     # deprecated alias
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


async def analyze_run_pivots(
    run_id: str, query: str, result: dict[str, Any], entity_type: str = "person"
) -> list[dict]:
    """
    Main entry point. Analyze tool calls from a research run,
    map to pivot patterns, generate overlay signals, upsert to DB.

    For person entities the static PIVOT_TOOL_MAP path is used (proven, no LLM call).
    For all other categories, tool calls are classified via LLM.
    """
    tree = result.get("tree", {})
    branches = tree.get("branches", [])

    if not branches:
        log.debug("analyze_run_pivots: no branches in result tree")
        return []

    overlays: list[dict] = []

    if entity_type == "person":
        # Existing static path — unchanged, no LLM involved
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
    else:
        # LLM classification path for non-person categories
        classified = await classify_tool_calls_llm(entity_type, query, branches)
        for item in classified:
            findings_count = item.get("findings_count", 0)
            yield_rate = calculate_yield_rate(findings_count, 1)
            overlay_type = determine_overlay_type(item.get("yield_rate", yield_rate), findings_count)
            if overlay_type:
                overlay = {
                    "entity_type": entity_type,
                    "selector_type": item["selector_type"],
                    "pivot_pattern": item["pivot_pattern"],
                    "overlay_type": overlay_type,
                    "yield_rate": item.get("yield_rate", yield_rate),
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


# ---------------------------------------------------------------------------
# LLM-based tool call classification (non-person categories)
# ---------------------------------------------------------------------------

def _extract_json_array(text: str) -> list | None:
    """Extract a JSON array from raw LLM text, trying multiple strategies."""
    text = text.strip()
    # Strategy 1: direct parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    # Strategy 2: markdown fenced block
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence_match:
        try:
            parsed = json.loads(fence_match.group(1).strip())
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    # Strategy 3: first [ to last ]
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    return None


async def _call_llm_for_classification(prompt: str) -> str:
    """Call Claude via Claude Code CLI (uses subscription, no API key needed).

    Falls back to Anthropic SDK if Claude Code is unavailable.
    Uses general_model (Sonnet) — classification does not need a reasoning model.
    """
    import os
    import shutil

    from app.llm_models import general_model

    model = general_model()

    # Primary: Claude Code CLI
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

            cmd_args = [claude_bin, "--output-format", "text", "--model", model, "--max-turns", "1"]
            if fresh_key:
                cmd_args.append("--bare")
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                env=spawn_env,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode()), timeout=60
            )
            if proc.returncode == 0 and stdout:
                return stdout.decode().strip()
            log.warning("Classifier: Claude Code exit %s, falling back to API", proc.returncode)
        except asyncio.TimeoutError:
            log.warning("Classifier: Claude Code timed out, falling back to API")
        except Exception as exc:
            log.warning("Classifier: Claude Code failed (%s), falling back to API", exc)

    # Fallback: Anthropic API SDK
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        try:
            from app.routers.v3.db import fetch_one
            row = fetch_one("SELECT value FROM core_settings WHERE key = 'anthropic_api_key'", ())
            if row:
                api_key = row["value"]
        except Exception:
            pass

    if not api_key:
        log.warning("Classifier: no Claude Code and no API key, returning empty")
        return "[]"

    loop = asyncio.get_running_loop()
    client = anthropic.Anthropic(api_key=api_key, max_retries=0)
    fallback_model = general_model()
    for current_model in [model, fallback_model]:
        try:
            response = await loop.run_in_executor(
                None,
                lambda m=current_model: client.messages.create(
                    model=m,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                ),
            )
            return response.content[0].text
        except Exception as exc:
            log.warning("Classifier: API model %s failed: %s", current_model, exc)

    return "[]"


async def classify_tool_calls_llm(
    entity_type: str,
    query: str,
    tool_calls: list[dict],
) -> list[dict]:
    """Classify tool calls by which research selector they were serving.

    Uses an LLM to infer the mapping for non-person categories where the static
    PIVOT_TOOL_MAP is not meaningful.

    Args:
        entity_type: Research category (e.g. "generation", "prediction").
        query: The original research query string.
        tool_calls: List of dicts with keys "tool", "result_count", optionally "params".

    Returns:
        List of dicts: {"tool", "selector_type", "pivot_pattern", "findings_count"}.
        Falls back to the first selector in the category list on any LLM failure.
    """
    if not tool_calls:
        return []

    from app.pipeline.strategies.selectors import get_selectors

    selectors = get_selectors(entity_type)
    first_selector = selectors[0]

    def _fallback_classifications() -> list[dict]:
        return [
            {
                "tool": tc["tool"],
                "selector_type": first_selector,
                "pivot_pattern": f"{first_selector} -> {tc['tool']}",
                "findings_count": int(tc.get("result_count", 0)),
            }
            for tc in tool_calls
        ]

    # Build numbered tool call lines for the prompt
    lines = []
    for i, tc in enumerate(tool_calls, start=1):
        tool_name = tc.get("tool", "")
        result_count = int(tc.get("result_count", 0))
        params_query = (tc.get("params") or {}).get("query", "")
        if params_query:
            lines.append(f'{i}. {tool_name} (query="{params_query}", results={result_count})')
        else:
            lines.append(f"{i}. {tool_name} (results={result_count})")

    valid_selectors_str = ", ".join(selectors)
    tool_calls_block = "\n".join(lines)

    prompt = (
        "Classify each tool call by which research selector it was serving.\n"
        f"Category: {entity_type}\n"
        f"Query: {query}\n"
        f"Valid selectors: {valid_selectors_str}\n"
        "\n"
        "Tool calls:\n"
        f"{tool_calls_block}\n"
        "\n"
        "Return ONLY a JSON array:\n"
        '[{"tool": "ddg_search", "selector_type": "problem_statement", "confidence": 0.9}]'
    )

    try:
        raw = await _call_llm_for_classification(prompt)
    except Exception as exc:
        log.warning("classify_tool_calls_llm: LLM call failed (%s), using fallback", exc)
        return _fallback_classifications()

    parsed = _extract_json_array(raw)
    if parsed is None:
        log.warning(
            "classify_tool_calls_llm: could not parse LLM response as JSON array, using fallback"
        )
        return _fallback_classifications()

    # Build a lookup from the LLM result: tool_name -> selector_type
    llm_map: dict[str, str] = {}
    for item in parsed:
        if isinstance(item, dict) and "tool" in item and "selector_type" in item:
            llm_map[item["tool"]] = item["selector_type"]

    results: list[dict] = []
    for tc in tool_calls:
        tool_name = tc.get("tool", "")
        findings_count = int(tc.get("result_count", 0))
        raw_selector = llm_map.get(tool_name, first_selector)
        # Validate — if LLM returned something not in the category, fall back to first
        selector_type = raw_selector if raw_selector in selectors else first_selector
        results.append(
            {
                "tool": tool_name,
                "selector_type": selector_type,
                "pivot_pattern": f"{selector_type} -> {tool_name}",
                "findings_count": findings_count,
            }
        )

    return results
