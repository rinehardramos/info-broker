"""Summarizer node — condenses single or aggregated input items into a coherent summary."""

from __future__ import annotations

import asyncio
import json
import logging
import os

from app.llm_models import general_model
from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_SUMMARIZE_PROMPT = """\
You are a research summarizer. Given the following data items, produce a clear,
coherent, human-readable summary.

**Instructions:**
{instructions}

**Data to summarize ({item_count} items):**
{data}

**Output format:**
Provide a structured summary with:
1. A brief overview paragraph
2. Key findings (bullet points)
3. Sources referenced
4. Any gaps or areas needing more investigation

Write in clear, professional prose. Be concise but comprehensive.
"""


class SummarizerNode:
    node_type = "summarizer"
    display_name = "Summarizer"
    category = "enrich"
    config_schema = {
        "type": "object",
        "properties": {
            "provider": {
                "type": "string",
                "title": "LLM Provider",
                "enum": ["claude", "openai", "openrouter", "gemini"],
                "default": "claude",
            },
            "model": {
                "type": "string",
                "title": "Model",
                "default": "claude-sonnet-4-6",
            },
            "instructions": {
                "type": "string",
                "title": "Summary Instructions",
                "description": "Additional instructions for the summarizer (e.g., 'Focus on financial data'). Supports {{agent_input}}.",
                "default": "Summarize all findings into a coherent report.",
            },
            "max_input_items": {
                "type": "integer",
                "title": "Max Input Items",
                "default": 50,
                "minimum": 1,
                "maximum": 200,
                "description": "Cap items to avoid exceeding context window",
            },
            "output_field": {
                "type": "string",
                "title": "Output Field",
                "default": "summary",
                "description": "Field name to store the summary in output items",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        if not inputs:
            return []

        provider = config.get("provider", "claude")
        model = config.get("model") or general_model()
        instructions = config.get("instructions", "Summarize all findings into a coherent report.")
        max_items = int(config.get("max_input_items", 50))
        output_field = config.get("output_field", "summary")

        # Truncate inputs to max_items
        items_to_summarize = inputs[:max_items]

        # Build data representation for the LLM
        data_str = _format_items(items_to_summarize)

        prompt = _SUMMARIZE_PROMPT.format(
            instructions=instructions,
            item_count=len(items_to_summarize),
            data=data_str[:12000],  # cap to stay within context
        )

        # Call LLM
        summary = await _call_provider(provider, model, prompt)

        # Return: a single summary item wrapping all inputs
        return [{
            output_field: summary,
            "item_count": len(items_to_summarize),
            "source": "summarizer",
            # Preserve the original items as nested data
            "source_items": [
                {k: v for k, v in item.items() if k != "source_items"}
                for item in items_to_summarize
            ],
        }]


def _format_items(items: list[dict]) -> str:
    """Format items into a readable text block for the LLM."""
    parts: list[str] = []
    for i, item in enumerate(items, 1):
        lines = [f"--- Item {i} ---"]
        for key in ("title", "query", "content", "snippet", "url", "source",
                     "research_summary", "research_findings", "ai_response"):
            val = item.get(key)
            if val:
                # Truncate long values
                val_str = str(val)[:500]
                lines.append(f"  {key}: {val_str}")
        # Include any other non-internal fields
        for key, val in item.items():
            if key.startswith("_") or key in ("title", "query", "content", "snippet", "url",
                                                "source", "research_summary", "research_findings",
                                                "ai_response", "source_items"):
                continue
            val_str = str(val)[:200]
            lines.append(f"  {key}: {val_str}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


async def _call_provider(provider: str, model: str, prompt: str) -> str:
    """Call the LLM provider to generate the summary."""
    loop = asyncio.get_running_loop()

    if provider == "claude":
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
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
            log.error("Summarizer Claude call failed: %s", exc)
            return f"Summary generation failed: {exc}"

    # OpenAI-compatible providers
    try:
        from openai import OpenAI
        key, base_url = _resolve_provider(provider)
        client = OpenAI(api_key=key, base_url=base_url)
        response = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
            ),
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        log.error("Summarizer %s call failed: %s", provider, exc)
        return f"Summary generation failed: {exc}"


def _resolve_provider(provider: str) -> tuple[str, str | None]:
    if provider == "openai":
        return os.getenv("OPENAI_API_KEY", ""), None
    if provider == "openrouter":
        return os.getenv("OPENROUTER_API_KEY", ""), "https://openrouter.ai/api/v1"
    if provider == "gemini":
        return os.getenv("GEMINI_API_KEY", ""), "https://generativelanguage.googleapis.com/v1beta/openai/"
    return "", None
