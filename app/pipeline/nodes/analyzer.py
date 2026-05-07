"""Intelligence Analyzer node — multi-stage entity extraction, relationship mapping, and synthesis."""

from __future__ import annotations

import asyncio
import json
import logging
import re

from app.llm_models import reasoning_model
from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_MAP_BATCH_SIZE = 10  # findings per MAP batch
_DIRECT_THRESHOLD = 20  # below this, skip map-reduce


_ANALYZER_ERROR_PATTERNS = [
    "blocked", "403", "404", "422", "not configured", "api_key", "api key",
    "permission error", "timed out", "rate limit", "access denied",
    "unauthorized", "token is not valid", "user was not found",
]


def _filter_errors(items: list[dict], min_confidence: int = 50) -> list[dict]:
    """Remove error-flagged and low-confidence items.

    Also detects errors in legacy findings that lack the error_flagged field
    by scanning title/content for known error patterns.
    """
    filtered = []
    for item in items:
        # Explicit flag from error pre-filter
        if item.get("error_flagged", False):
            continue
        # Below confidence threshold
        if item.get("confidence", 100) < min_confidence:
            continue
        # Legacy findings: detect errors by title only (content may mention errors in passing)
        title = (item.get("title") or "").lower()
        if any(p in title for p in _ANALYZER_ERROR_PATTERNS):
            continue
        filtered.append(item)
    return filtered


def _format_items_for_llm(items: list[dict]) -> str:
    """Format findings into a compact text block for LLM context."""
    parts = []
    for i, item in enumerate(items):
        title = item.get("title") or item.get("query") or f"Item {i+1}"
        content = item.get("content") or item.get("snippet") or item.get("text") or ""
        source = item.get("source") or ""
        url = item.get("url") or ""
        confidence = item.get("confidence", "?")
        parts.append(
            f"[{i+1}] {title}\n"
            f"  Source: {source} | Confidence: {confidence}%\n"
            f"  URL: {url}\n"
            f"  {content[:500]}"
        )
    return "\n\n".join(parts)


def _try_parse_json(text: str) -> dict:
    """Parse JSON from LLM output using multiple fallback strategies.

    1. Direct json.loads
    2. Extract from markdown fenced block (```json ... ```)
    3. Find first { to last } and parse that substring
    """
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


def _parse_json_field(text: str, field: str, default):
    """Parse JSON from LLM output and return a specific field."""
    parsed = _try_parse_json(text)
    return parsed.get(field, default)


_EXTRACT_PROMPT = """\
You are an intelligence analyst. The user's original research question was:
**"{query}"**

Extract ALL entities from these research findings that are RELEVANT to answering the research question.
Focus on entities that help answer the question — skip tangential mentions.

Entity types: person, company, organization, role/title, location, technology, service, event.

For each entity, provide:
- name: exact name as found
- type: entity type
- attributes: key-value pairs (role, company, location, etc.)
- relevance: how this entity relates to the research question (1 sentence)
- evidence: list of finding numbers [1], [2] etc. that mention this entity

**Findings:**
{findings}

**Output valid JSON only:**
{{"entities": [{{"name": "...", "type": "person|company|...", "attributes": {{}}, "relevance": "why this matters to the query", "evidence": [1, 3]}}]}}
"""

_RELATE_PROMPT = """\
You are an intelligence analyst. The user's original research question was:
**"{query}"**

Given these extracted entities, identify relationships between them that are relevant to the research question.

Relationship types: works_at, founded, uses_service, outsources_to, competes_with, partners_with, reports_to, located_in, provides_service.

**Entities:**
{entities}

**Original findings context:**
{findings_summary}

**Output valid JSON only:**
{{"relationships": [{{"from": "entity_name", "to": "entity_name", "type": "relationship_type", "evidence": "brief explanation"}}]}}
"""

_SYNTHESIZE_PROMPT = """\
You are an intelligence analyst. The user's original research question was:
**"{query}"**

Based on these entities and relationships, produce actionable intelligence that DIRECTLY answers the research question.
Your insights and recommendations must be specific to what the user asked — not generic observations.

**Entities ({entity_count}):**
{entities}

**Relationships ({rel_count}):**
{relationships}

{context_prompt}

**Output valid JSON only:**
{{
  "insights": ["specific insight that answers the research question"],
  "recommendations": [{{"action": "specific next step", "reason": "how this helps answer the question", "priority": "high|medium|low"}}],
  "research_gaps": [{{"entity": "name", "missing": "what data is still needed to answer the question", "suggested_tool": "run_tool_name"}}],
  "enrichment_targets": [{{"entity": "name", "action": "tool to call", "reason": "why this enrichment helps answer the question"}}]
}}
"""


class AnalyzerNode:
    node_type = "analyzer"
    display_name = "Intelligence Analyzer"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "analysis_type": {
                "type": "string",
                "title": "Analysis Type",
                "enum": ["comprehensive", "entity_extraction", "competitive", "risk_assessment"],
                "default": "comprehensive",
            },
            "min_confidence": {
                "type": "integer",
                "title": "Min Confidence",
                "default": 50,
                "minimum": 0,
                "maximum": 100,
                "description": "Only analyze findings with confidence >= this threshold",
            },
            "model": {
                "type": "string",
                "title": "Model",
                "default": "claude-opus-4-7",
            },
            "context_prompt": {
                "type": "string",
                "title": "Analysis Context",
                "description": "Additional context for analysis (e.g., 'Focus on IT outsourcing needs')",
            },
        },
        "required": [],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        min_confidence = int(config.get("min_confidence", 50))
        model = config.get("model") or reasoning_model()
        context_prompt = config.get("context_prompt", "")

        # Separate errors from valid findings
        valid = _filter_errors(inputs, min_confidence)
        error_count = len(inputs) - len(valid)
        error_tools = list({item.get("source", "") for item in inputs if item.get("error_flagged")})

        if not valid:
            return [{
                "source": "analyzer",
                "analysis_type": config.get("analysis_type", "comprehensive"),
                "entities": [],
                "relationships": [],
                "insights": ["No valid findings to analyze — all results were errors or below confidence threshold."],
                "recommendations": [],
                "research_gaps": [],
                "enrichment_targets": [],
                "error_summary": {
                    "total_errors": error_count,
                    "tools_failing": error_tools,
                    "action_needed": "Configure API keys in Settings > Node Health",
                },
                "stats": {
                    "findings_analyzed": 0,
                    "findings_filtered_as_errors": error_count,
                    "entities_extracted": 0,
                    "relationships_found": 0,
                },
            }]

        # The original research query — critical for keeping analysis on-topic
        query = config.get("query", "") or config.get("context_prompt", "") or ""

        # Choose strategy based on dataset size
        if len(valid) <= _DIRECT_THRESHOLD:
            entities = await self._extract_entities(valid, model, query)
        else:
            entities = await self._map_reduce_extract(valid, model, query)

        relationships = await self._map_relationships(entities, valid, model, query)
        synthesis = await self._synthesize(entities, relationships, context_prompt, model, query)

        return [{
            "source": "analyzer",
            "analysis_type": config.get("analysis_type", "comprehensive"),
            "entities": entities,
            "relationships": relationships,
            **synthesis,
            "error_summary": {
                "total_errors": error_count,
                "tools_failing": error_tools,
                "action_needed": "Configure API keys in Settings > Node Health" if error_tools else None,
            },
            "stats": {
                "findings_analyzed": len(valid),
                "findings_filtered_as_errors": error_count,
                "entities_extracted": len(entities),
                "relationships_found": len(relationships),
            },
        }]

    async def _extract_entities(self, items: list[dict], model: str, query: str = "") -> list[dict]:
        """Single-pass entity extraction for small datasets."""
        prompt = _EXTRACT_PROMPT.format(findings=_format_items_for_llm(items), query=query or "General research")
        raw = await _call_llm(prompt, model)
        log.info("Analyzer extract: LLM returned %d chars, first 200: %s", len(raw), raw[:200])
        entities = _parse_json_field(raw, "entities", [])
        log.info("Analyzer extract: parsed %d entities", len(entities))
        return entities

    async def _map_reduce_extract(self, items: list[dict], model: str, query: str = "") -> list[dict]:
        """Map-reduce entity extraction for large datasets."""
        # MAP: extract entities from batches in parallel
        batches = [items[i:i + _MAP_BATCH_SIZE] for i in range(0, len(items), _MAP_BATCH_SIZE)]
        tasks = [self._extract_entities(batch, model, query) for batch in batches]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # REDUCE: merge and deduplicate entities
        all_entities: dict[tuple, dict] = {}
        for result in batch_results:
            if isinstance(result, Exception):
                log.warning("Analyzer MAP batch failed: %s", result)
                continue
            for entity in result:
                key = (entity.get("name", "").lower(), entity.get("type", ""))
                if key in all_entities:
                    # Merge attributes and evidence
                    existing = all_entities[key]
                    existing["attributes"].update(entity.get("attributes", {}))
                    existing["evidence"] = list(set(existing.get("evidence", []) + entity.get("evidence", [])))
                else:
                    all_entities[key] = entity

        return list(all_entities.values())

    async def _map_relationships(self, entities: list[dict], items: list[dict], model: str, query: str = "") -> list[dict]:
        """Map relationships between extracted entities."""
        if not entities:
            return []
        entities_text = json.dumps(entities, indent=2)[:3000]
        findings_summary = _format_items_for_llm(items[:10])  # truncate for context
        prompt = _RELATE_PROMPT.format(entities=entities_text, findings_summary=findings_summary, query=query or "General research")
        raw = await _call_llm(prompt, model)
        return _parse_json_field(raw, "relationships", [])

    async def _synthesize(self, entities: list[dict], relationships: list[dict], context_prompt: str, model: str, query: str = "") -> dict:
        """Produce actionable insights from entities and relationships."""
        entities_text = json.dumps(entities, indent=2)[:3000]
        rels_text = json.dumps(relationships, indent=2)[:2000]
        ctx = f"\n**Additional context:** {context_prompt}" if context_prompt else ""
        prompt = _SYNTHESIZE_PROMPT.format(
            entity_count=len(entities),
            entities=entities_text,
            rel_count=len(relationships),
            relationships=rels_text,
            context_prompt=ctx,
            query=query or "General research",
        )
        raw = await _call_llm(prompt, model)
        parsed = _try_parse_json(raw)
        return {
            "insights": parsed.get("insights", []),
            "recommendations": parsed.get("recommendations", []),
            "research_gaps": parsed.get("research_gaps", []),
            "enrichment_targets": parsed.get("enrichment_targets", []),
        }


async def _call_llm(prompt: str, model: str = "") -> str:
    """Call Claude via Claude Code CLI (uses subscription, no API key needed).

    Falls back to Anthropic SDK if Claude Code is unavailable.
    """
    import os
    import shutil

    if not model:
        model = reasoning_model()

    # Primary: Claude Code CLI (uses subscription — no rate limits)
    claude_bin = shutil.which("claude") or "/usr/local/bin/claude"
    if os.path.isfile(claude_bin):
        try:
            proc = await asyncio.create_subprocess_exec(
                claude_bin, "-p", prompt,
                "--output-format", "text",
                "--model", model,
                "--max-turns", "1",
                "--no-input",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "CLAUDE_CODE_HEADLESS": "1"},
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode == 0 and stdout:
                result = stdout.decode().strip()
                log.info("Analyzer: Claude Code returned %d chars", len(result))
                return result
            else:
                log.warning("Analyzer: Claude Code exit %s, falling back to API", proc.returncode)
        except asyncio.TimeoutError:
            log.warning("Analyzer: Claude Code timed out, falling back to API")
        except Exception as exc:
            log.warning("Analyzer: Claude Code failed (%s), falling back to API", exc)

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
        log.warning("Analyzer: no Claude Code and no API key, returning empty")
        return "{}"

    from app.llm_models import general_model

    loop = asyncio.get_running_loop()
    client = anthropic.Anthropic(api_key=api_key, max_retries=0)

    models_to_try = [model]
    fallback = general_model()
    if fallback != model:
        models_to_try.append(fallback)
    if "haiku" not in model and "haiku" not in fallback:
        models_to_try.append("claude-haiku-4-5-20251001")

    for current_model in models_to_try:
        for attempt in range(3):
            try:
                response = await loop.run_in_executor(
                    None,
                    lambda m=current_model: client.messages.create(
                        model=m,
                        max_tokens=4096,
                        messages=[{"role": "user", "content": prompt}],
                    ),
                )
                return response.content[0].text
            except anthropic.RateLimitError:
                wait = 2 ** (attempt + 1)
                log.warning("Analyzer: rate limited on %s, retry %d in %ds", current_model, attempt + 1, wait)
                await asyncio.sleep(wait)
            except Exception as exc:
                log.error("Analyzer LLM call failed (%s): %s", current_model, exc)
                break

    log.error("Analyzer: all methods exhausted")
    return "{}"
