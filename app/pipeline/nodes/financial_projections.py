"""Financial Projections Builder node — LLM-powered financial projection analysis."""

from __future__ import annotations

import asyncio
import json
import logging
import re

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_PROJECTION_PROMPT = """\
You are a financial analyst. Based on the research findings below, produce a structured financial projection.

**Projection type:** {projection_type}
**Time horizon:** {time_horizon}

**Research findings:**
{findings}

Produce a JSON response with this exact structure:
{{
  "assumptions": [
    "assumption 1",
    "assumption 2"
  ],
  "projections": [
    {{
      "period": "Q1 2025",
      "metric": "Revenue",
      "value": "500000",
      "confidence": 70
    }}
  ],
  "risks": [
    "risk 1",
    "risk 2"
  ],
  "methodology": "Brief description of the analytical approach used"
}}

Guidelines by projection type:
- revenue_forecast: project revenue growth across periods, include growth rate assumptions
- cost_analysis: break down cost categories, fixed vs variable, margins
- market_sizing: TAM/SAM/SOM with market penetration assumptions
- break_even: identify break-even point, unit economics, contribution margin

Output valid JSON only. Do not include any text before or after the JSON object.
"""


def _format_findings(items: list[dict]) -> str:
    """Format input findings into a compact text block for LLM context."""
    parts = []
    for i, item in enumerate(items):
        title = item.get("title") or item.get("query") or f"Finding {i + 1}"
        content = item.get("content") or item.get("snippet") or item.get("text") or ""
        source = item.get("source") or ""
        confidence = item.get("confidence", "?")
        parts.append(
            f"[{i + 1}] {title}\n"
            f"  Source: {source} | Confidence: {confidence}%\n"
            f"  {content[:600]}"
        )
    return "\n\n".join(parts) if parts else "No structured findings provided."


def _try_parse_json(text: str) -> dict:
    """Parse JSON from LLM output with multiple fallback strategies."""
    text = text.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: markdown fenced block
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Strategy 3: first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return {}


class FinancialProjectionsNode:
    node_type = "financial_projections"
    display_name = "Financial Projections Builder"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "projection_type": {
                "type": "string",
                "title": "Projection Type",
                "enum": ["revenue_forecast", "cost_analysis", "market_sizing", "break_even"],
                "default": "revenue_forecast",
            },
            "model": {
                "type": "string",
                "title": "Model",
                "default": "claude-haiku-4-5-20251001",
            },
            "time_horizon": {
                "type": "string",
                "title": "Time Horizon",
                "default": "12 months",
                "description": "e.g. '12 months', '3 years', 'Q1-Q4 2025'",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        projection_type = config.get("projection_type", "revenue_forecast")
        model = config.get("model", "claude-haiku-4-5-20251001")
        time_horizon = config.get("time_horizon", "12 months")

        findings_text = _format_findings(inputs)
        prompt = _PROJECTION_PROMPT.format(
            projection_type=projection_type,
            time_horizon=time_horizon,
            findings=findings_text,
        )

        raw = await _call_llm(prompt, model)
        parsed = _try_parse_json(raw)

        if not parsed:
            log.warning("financial_projections: failed to parse LLM response")
            return [{
                "source": "financial_projections",
                "projection_type": projection_type,
                "time_horizon": time_horizon,
                "assumptions": [],
                "projections": [],
                "risks": ["LLM returned unparseable output"],
                "methodology": "Unable to generate projections — check API key and inputs",
                "error": "Failed to parse LLM response",
            }]

        return [{
            "source": "financial_projections",
            "projection_type": projection_type,
            "time_horizon": time_horizon,
            "assumptions": parsed.get("assumptions", []),
            "projections": parsed.get("projections", []),
            "risks": parsed.get("risks", []),
            "methodology": parsed.get("methodology", ""),
        }]


async def _call_llm(prompt: str, model: str = "claude-haiku-4-5-20251001") -> str:
    """Call Claude API for financial projections analysis."""
    import os

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
        log.warning("financial_projections: no ANTHROPIC_API_KEY, returning empty")
        return "{}"

    loop = asyncio.get_running_loop()
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = await loop.run_in_executor(
            None,
            lambda: client.messages.create(
                model=model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            ),
        )
        return response.content[0].text
    except Exception as exc:
        log.error("financial_projections: LLM call failed: %s", exc)
        return "{}"
