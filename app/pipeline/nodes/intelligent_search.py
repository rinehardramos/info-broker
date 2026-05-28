"""Intelligent Search node — LLM-powered agentic research loop.

This node receives items from upstream (typically agent_input), uses an LLM
with tool-use to dynamically search across connected datastores and built-in
tools, and returns enriched items with research findings.

The research trail (queries, tool calls, findings) is persisted for future
reference and audit.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt for the research agent
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an intelligent research agent. Your job is to gather comprehensive
information about the user's query using the tools available to you.

**How to work:**
1. Analyze the query to determine the ENTITY TYPE (person, company, product,
   location, event, concept, etc.).
2. Based on the entity type, reason about WHERE this entity might have data
   (e.g., a person → LinkedIn, Facebook, Instagram, email, phone directories,
   local contacts; a company → Crunchbase, SEC filings, news, social media).
3. Start with local datastores (files, notes, databases) for quick hits.
4. Expand to web search and crawling for broader coverage.
5. For each finding, assess RELEVANCE — is this actually about the right entity?
6. Drill deeper on promising leads (follow URLs, search related terms).
7. If you need a data source that's not available as a tool, use request_plugin
   to notify the user.

**When to stop:**
- You've exhausted your tool budget
- You've gathered enough high-confidence findings
- Further searches are unlikely to yield new information

**Output format:**
When done, provide a structured JSON summary with your findings. Use the
`finish_research` tool to submit your final results.

{research_goal}
"""


class IntelligentSearchNode:
    node_type = "intelligent_search"
    display_name = "Intelligent Search"
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
            "research_goal": {
                "type": "string",
                "title": "Research Goal",
                "description": (
                    "What the LLM should find for each item. "
                    "Supports {{agent_input}} variable."
                ),
            },
            "max_tool_calls": {
                "type": "integer",
                "title": "Max Tool Calls",
                "default": 20,
                "minimum": 1,
                "maximum": 100,
            },
            "max_depth": {
                "type": "integer",
                "title": "Max Depth",
                "default": 3,
                "minimum": 1,
                "maximum": 10,
                "description": "Max drill-down iterations per item",
            },
        },
        "required": ["research_goal"],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        # 1. Auto-discover all registered nodes as tools
        tool_defs, tool_handlers = _resolve_tools(context)

        # 2. Check for prior research on similar queries
        # (future: semantic lookup in research_trails via Qdrant)

        # 3. When IS runs as a standalone orchestrator (no upstream inputs),
        # synthesize a single input item from the research_goal config.
        if not inputs:
            query = config.get("research_goal", "")
            inputs = [{"query": query, "content": query}]

        # 4. Process each input item through the agentic loop
        results = []
        for item in inputs:
            enriched = await _research_item(item, config, tool_defs, tool_handlers, context)
            results.append(enriched)

        return results


# ---------------------------------------------------------------------------
# Tool resolution — auto-discovers all registered nodes as tools
# ---------------------------------------------------------------------------

def _resolve_tools(
    context: RunContext,
) -> tuple[list[dict], dict[str, Any]]:
    """Auto-discover all registered nodes as LLM tools.

    Returns:
        tool_defs: list of Claude tool-use schema dicts
        tool_handlers: mapping of tool name → async callable(params) → result
    """
    from app.pipeline.nodes import NodeRegistry
    NodeRegistry.auto_discover()

    tool_defs: list[dict] = []
    tool_handlers: dict[str, Any] = {}

    for node in NodeRegistry.all():
        # Skip agent_input — it's the entry point, not a callable tool
        if node.node_type == "agent_input":
            continue
        # Skip intelligent_search itself — would cause infinite recursion
        if node.node_type == "intelligent_search":
            continue

        if hasattr(node, "tool_schema") and hasattr(node, "tool_invoke"):
            # Nodes implementing the ToolCallable protocol (e.g. datastores)
            schema = node.tool_schema()
            tool_defs.append(schema)
            tool_name = schema["name"]
            tool_handlers[tool_name] = lambda params, n=node: n.tool_invoke(params, context)
        else:
            # Wrap regular pipeline nodes as generic tools using their config_schema
            tool_name = f"run_{node.node_type}"
            props: dict[str, dict] = {}
            if hasattr(node, "config_schema"):
                schema_props = node.config_schema.get("properties", {})
                for key, val in schema_props.items():
                    props[key] = {
                        "type": val.get("type", "string"),
                        "description": val.get("description", val.get("title", key)),
                    }
            tool_defs.append({
                "name": tool_name,
                "description": (
                    f"Execute the {node.display_name} pipeline node. "
                    f"Category: {node.category}."
                ),
                "input_schema": {"type": "object", "properties": props},
            })

            async def _run_node(params: dict, n=node) -> Any:
                cfg = dict(params)
                return await n.execute(cfg, [], context)

            tool_handlers[tool_name] = _run_node

    # Built-in: web search (always available)
    tool_defs.append({
        "name": "web_search",
        "description": (
            "Search the web using DuckDuckGo. Returns titles, URLs, and snippets."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {
                    "type": "integer",
                    "description": "Max results (default 10)",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    })

    # Built-in: follow URL
    tool_defs.append({
        "name": "follow_url",
        "description": (
            "Fetch and extract text content from a web page URL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
            },
            "required": ["url"],
        },
    })

    # Built-in: mark for review (non-blocking manual scoring)
    tool_defs.append({
        "name": "mark_for_review",
        "description": (
            "Mark a finding as needing human review. Use when you're unsure "
            "about relevance or authenticity."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_summary": {"type": "string", "description": "Brief summary of the finding"},
                "reason": {"type": "string", "description": "Why human review is needed"},
            },
            "required": ["item_summary", "reason"],
        },
    })

    # Built-in: request plugin
    tool_defs.append({
        "name": "request_plugin",
        "description": (
            "Request a new data source plugin that doesn't exist yet. "
            "Use when you need access to a specific service or API."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Plugin name (e.g., 'linkedin_scraper', 'shodan_scan')",
                },
                "description": {
                    "type": "string",
                    "description": "What data this plugin would provide",
                },
                "expected_api": {
                    "type": "string",
                    "description": "Known API endpoint or service URL (if any)",
                },
                "data_format": {
                    "type": "string",
                    "description": "Expected output format (e.g., 'JSON list of profiles')",
                },
            },
            "required": ["name", "description"],
        },
    })

    # Built-in: finish research
    tool_defs.append({
        "name": "finish_research",
        "description": (
            "Submit final research findings. Call this when you've gathered "
            "enough information or exhausted your search options."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Brief summary of what was found",
                },
                "entity_type": {
                    "type": "string",
                    "description": "Detected entity type (person, company, product, etc.)",
                },
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string"},
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                            "url": {"type": "string"},
                            "confidence": {
                                "type": "number",
                                "description": "0-100 confidence that this is relevant",
                            },
                        },
                    },
                    "description": "List of research findings",
                },
                "needs_review": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Items flagged for human review",
                },
                "missing_sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Data sources that would be useful but aren't available",
                },
            },
            "required": ["summary", "findings"],
        },
    })

    return tool_defs, tool_handlers


# ---------------------------------------------------------------------------
# Agentic research loop
# ---------------------------------------------------------------------------

async def _research_item(
    item: dict,
    config: dict,
    tool_defs: list[dict],
    tool_handlers: dict[str, Any],
    context: RunContext,
) -> dict:
    """Run the LLM agentic loop for a single input item."""
    provider = config.get("provider", "claude")
    model = config.get("model", "claude-sonnet-4-6")
    max_calls = int(config.get("max_tool_calls", 20))
    research_goal = config.get("research_goal", "")

    # Build the query from the item
    query = item.get("query") or item.get("content") or item.get("title") or str(item)

    # Format system prompt
    goal_section = f"\n**Research goal:** {research_goal}" if research_goal else ""
    system = _SYSTEM_PROMPT.format(research_goal=goal_section)

    # Build user message
    user_msg = f"Research this query: {query}\n\nItem context: {json.dumps(item, default=str)[:2000]}"

    messages: list[dict] = [{"role": "user", "content": user_msg}]
    trail: list[dict] = []  # research trail for persistence
    call_count = 0
    depth = 0              # LLM turn count (each turn can have multiple tool calls)
    final_findings: dict = {}
    review_items: list[str] = []
    # Track parent→child relationships: the last tool_call_id from previous turn
    # is the "parent" for calls in the next turn (LLM saw those results and decided to dig deeper)
    last_turn_call_ids: list[str] = []

    # Notify frontend that research has started
    _try_push(context, {
        "type": "intelligent_search.started",
        "run_id": context.run_id,
        "node_id": context.node_id,
        "query": query[:500],
        "max_calls": max_calls,
    })

    while call_count < max_calls:
        depth += 1
        # Call LLM
        response = await _call_llm(provider, model, system, messages, tool_defs)

        if not response:
            break

        # Append assistant message
        messages.append({"role": "assistant", "content": response["content"]})

        # Check for tool use
        tool_calls = [
            block for block in (response.get("content") or [])
            if isinstance(block, dict) and block.get("type") == "tool_use"
        ]

        if not tool_calls:
            # LLM finished without calling finish_research — extract text
            break

        # Process tool calls
        tool_results: list[dict] = []
        current_turn_call_ids: list[str] = []
        # Parent is the first call from the previous turn (the call whose results triggered this turn)
        parent_call_id = last_turn_call_ids[0] if last_turn_call_ids else None

        for tc in tool_calls:
            call_count += 1
            tool_name = tc["name"]
            tool_input = tc.get("input", {})
            tool_id = tc["id"]
            call_id = str(uuid.uuid4())
            current_turn_call_ids.append(call_id)

            # Stream tool_call event with tree info
            _try_push(context, {
                "type": "intelligent_search.tool_call",
                "run_id": context.run_id,
                "node_id": context.node_id,
                "call_id": call_id,
                "parent_call_id": parent_call_id,
                "tool": tool_name,
                "params": {k: str(v)[:200] for k, v in tool_input.items()},
                "call_count": call_count,
                "max_calls": max_calls,
                "depth": depth,
            })

            # Record in trail
            trail.append({
                "call_id": call_id,
                "parent_call_id": parent_call_id,
                "tool": tool_name,
                "params": tool_input,
                "call_number": call_count,
                "depth": depth,
            })

            # Execute tool
            result = await _execute_tool(
                tool_name, tool_input, tool_handlers, context, review_items
            )

            # Compute result count
            result_count = len(result) if isinstance(result, list) else (1 if result else 0)

            # Check if this is the finish_research tool
            if tool_name == "finish_research":
                final_findings = tool_input
                # Stream tool_result
                _try_push(context, {
                    "type": "intelligent_search.tool_result",
                    "run_id": context.run_id,
                    "call_id": call_id,
                    "tool": tool_name,
                    "status": "succeeded",
                    "result_count": 0,
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps({"status": "research_complete"}),
                })
                break
            else:
                # Truncate large results to stay within context
                result_str = json.dumps(result, default=str)[:8000]
                trail[-1]["result_preview"] = result_str[:500]
                trail[-1]["result_count"] = result_count

                # Stream tool_result event
                _try_push(context, {
                    "type": "intelligent_search.tool_result",
                    "run_id": context.run_id,
                    "call_id": call_id,
                    "tool": tool_name,
                    "status": "succeeded",
                    "result_count": result_count,
                    "result_preview": result_str[:200],
                })

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result_str,
                })

        last_turn_call_ids = current_turn_call_ids

        # Append tool results to messages
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

        # If finish_research was called, we're done
        if final_findings:
            break

    # Persist research trail
    await _persist_trail(context, query, final_findings, trail, call_count)

    # Build enriched output item
    findings = final_findings.get("findings", [])
    return {
        **item,
        "research_summary": final_findings.get("summary", ""),
        "entity_type": final_findings.get("entity_type", ""),
        "research_findings": findings,
        "research_tool_calls": call_count,
        "needs_review": review_items + final_findings.get("needs_review", []),
        "missing_sources": final_findings.get("missing_sources", []),
    }


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

async def _execute_tool(
    tool_name: str,
    params: dict,
    tool_handlers: dict[str, Any],
    context: RunContext,
    review_items: list[str],
) -> Any:
    """Dispatch a tool call to the appropriate handler."""

    # Built-in tools that need special handling (side-effects / state mutation)
    if tool_name == "web_search":
        return await _builtin_web_search(params)

    if tool_name == "follow_url":
        return await _builtin_follow_url(params)

    if tool_name == "mark_for_review":
        summary = params.get("item_summary", "")
        reason = params.get("reason", "")
        review_items.append(f"{summary} — {reason}")
        return {"status": "marked_for_review"}

    if tool_name == "request_plugin":
        return await _builtin_request_plugin(params, context)

    if tool_name == "finish_research":
        return {"status": "research_complete"}

    # Auto-discovered node tools (registered via _resolve_tools)
    handler = tool_handlers.get(tool_name)
    if handler:
        return await handler(params)

    return {"error": f"Unknown tool: {tool_name}"}


async def _builtin_web_search(params: dict) -> list[dict]:
    """DDG web search via existing plugin."""
    try:
        from app.search_engine.plugins.ddg import DdgPlugin
        plugin = DdgPlugin()
        results = await plugin.search(
            params.get("query", ""),
            max_results=int(params.get("max_results", 10)),
        )
        return [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet,
                "source": "web_search",
            }
            for r in results
        ]
    except Exception as exc:
        log.warning("web_search failed: %s", exc)
        return [{"error": str(exc), "source": "web_search"}]


async def _builtin_follow_url(params: dict) -> list[dict]:
    """Fetch and parse a URL."""
    url = params.get("url", "")
    if not url:
        return [{"error": "No URL provided"}]
    try:
        loop = asyncio.get_running_loop()
        from app.lib.ddg_fallback import scrape_url
        text = await loop.run_in_executor(None, scrape_url, url)
        return [{"url": url, "content": (text or "")[:6000], "source": "web_crawl"}]
    except Exception as exc:
        return [{"error": str(exc), "url": url, "source": "web_crawl"}]


async def _builtin_request_plugin(params: dict, context: RunContext) -> dict:
    """Store a structured plugin request and notify the user."""
    spec = {
        "name": params.get("name", ""),
        "description": params.get("description", ""),
        "expected_api": params.get("expected_api", ""),
        "data_format": params.get("data_format", ""),
        "requested_by_run": context.run_id,
        "requested_by_node": context.node_id,
    }
    try:
        from app.routers.v3.db import execute as db_execute
        req_id = str(uuid.uuid4())
        db_execute(
            "INSERT INTO plugin_requests (id, user_id, spec, status) VALUES (%s, %s, %s::jsonb, 'pending')",
            (req_id, context.user_id, json.dumps(spec)),
        )
    except Exception as exc:
        log.warning("Failed to persist plugin request: %s", exc)

    _try_push(context, {
        "type": "plugin_request.created",
        "run_id": context.run_id,
        "spec": spec,
    })

    return {"status": "requested", "message": f"Plugin '{spec['name']}' has been requested"}


# ---------------------------------------------------------------------------
# LLM call — supports Claude (primary), OpenAI-compatible providers
# ---------------------------------------------------------------------------

async def _call_llm(
    provider: str,
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict],
) -> dict | None:
    """Call the LLM with tool-use support. Returns raw response dict."""

    if provider == "claude":
        return await _call_claude(model, system, messages, tools)

    # OpenAI-compatible providers (openai, openrouter, gemini)
    return await _call_openai_compat(provider, model, system, messages, tools)


async def _call_claude(
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict],
) -> dict | None:
    """Call Claude via Anthropic SDK with tool-use."""
    import time as _time_mod

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        loop = asyncio.get_running_loop()

        _t0 = _time_mod.monotonic_ns()
        response = await loop.run_in_executor(
            None,
            lambda: client.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                messages=messages,
                tools=tools,
            ),
        )
        _duration_ms = int((_time_mod.monotonic_ns() - _t0) / 1_000_000)

        # Extract usage tokens
        _usage: dict[str, int] = {
            "input_tokens": getattr(response.usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(response.usage, "output_tokens", 0) or 0,
            "cache_creation_input_tokens": (
                getattr(response.usage, "cache_creation_input_tokens", 0) or 0
            ),
            "cache_read_input_tokens": (
                getattr(response.usage, "cache_read_input_tokens", 0) or 0
            ),
        }

        # Fail-open: emit usage telemetry; never block the main path
        try:
            from app.observability import usage_emitter_ref as _ue_mod
            from app.observability import pricing_ref as _pr_mod

            _emitter = _ue_mod._emitter
            if _emitter is not None:
                _resolver = _pr_mod._resolver
                if _resolver is not None:
                    _price = await _resolver.get(model)
                else:
                    _price = None

                if _price is not None:
                    _cost_usd, _cost_source, _pricing_id = _price.cost_for(_usage)
                else:
                    _cost_usd, _cost_source, _pricing_id = None, "unknown_model", None

                import time as _ts_mod
                _ts = int(_ts_mod.time() * 1000)

                asyncio.create_task(
                    _emitter.emit_llm_call(
                        ts=_ts,
                        model=model,
                        provider="anthropic",
                        status="ok",
                        input_tokens=_usage["input_tokens"],
                        output_tokens=_usage["output_tokens"],
                        cache_creation_tokens=_usage["cache_creation_input_tokens"],
                        cache_read_tokens=_usage["cache_read_input_tokens"],
                        duration_ms=_duration_ms,
                        total_cost_usd=_cost_usd,
                        cost_source=_cost_source,
                        pricing_id=_pricing_id,
                        actor={},
                    )
                )
        except Exception:
            log.debug(
                "_call_claude: emit_llm_call failed (swallowed)", exc_info=True
            )

        return {
            "content": [_block_to_dict(b) for b in response.content],
            "stop_reason": response.stop_reason,
        }
    except Exception as exc:
        log.error("Claude call failed: %s", exc)
        return None


def _block_to_dict(block: Any) -> dict:
    """Convert an Anthropic content block to a plain dict."""
    if hasattr(block, "type"):
        if block.type == "text":
            return {"type": "text", "text": block.text}
        if block.type == "tool_use":
            return {
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            }
    return {"type": "text", "text": str(block)}


async def _call_openai_compat(
    provider: str,
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict],
) -> dict | None:
    """Call OpenAI-compatible providers with function-calling."""
    try:
        from openai import OpenAI

        # Resolve API key and base URL
        key, base_url = _resolve_openai_provider(provider)
        client = OpenAI(api_key=key, base_url=base_url)

        # Convert Claude-style messages to OpenAI format
        oai_messages = [{"role": "system", "content": system}]
        for msg in messages:
            oai_messages.append(_to_openai_message(msg))

        # Convert Claude tool schemas to OpenAI function format
        oai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            }
            for t in tools
        ]

        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=model,
                messages=oai_messages,
                tools=oai_tools if oai_tools else None,
                max_tokens=4096,
            ),
        )

        choice = response.choices[0]
        content: list[dict] = []

        if choice.message.content:
            content.append({"type": "text", "text": choice.message.content})

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": json.loads(tc.function.arguments),
                })

        return {
            "content": content,
            "stop_reason": "tool_use" if choice.message.tool_calls else "end_turn",
        }
    except Exception as exc:
        log.error("OpenAI-compat call failed (%s): %s", provider, exc)
        return None


def _resolve_openai_provider(provider: str) -> tuple[str, str | None]:
    """Return (api_key, base_url) for an OpenAI-compatible provider."""
    if provider == "openai":
        return os.getenv("OPENAI_API_KEY", ""), None
    if provider == "openrouter":
        return os.getenv("OPENROUTER_API_KEY", ""), "https://openrouter.ai/api/v1"
    if provider == "gemini":
        return os.getenv("GEMINI_API_KEY", ""), "https://generativelanguage.googleapis.com/v1beta/openai/"
    return "", None


def _to_openai_message(msg: dict) -> dict:
    """Convert a Claude-style message to OpenAI format."""
    role = msg.get("role", "user")
    content = msg.get("content", "")

    if isinstance(content, str):
        return {"role": role, "content": content}

    if isinstance(content, list):
        # Check if it's tool results
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            # OpenAI expects tool results as separate messages
            # For simplicity, concatenate them
            parts = []
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    parts.append(f"[Tool result for {b.get('tool_use_id', '?')}]: {b.get('content', '')}")
            return {"role": "tool", "content": "\n".join(parts)}

        # Text + tool_use blocks
        text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return {"role": role, "content": " ".join(text_parts)}

    return {"role": role, "content": str(content)}


# ---------------------------------------------------------------------------
# Research trail persistence
# ---------------------------------------------------------------------------

async def _persist_trail(
    context: RunContext,
    query: str,
    findings: dict,
    trail: list[dict],
    call_count: int,
) -> None:
    """Save the research trail to the database for future reference."""
    try:
        from app.routers.v3.db import execute as db_execute
        trail_id = str(uuid.uuid4())
        db_execute(
            """INSERT INTO research_trails
               (id, user_id, run_id, node_id, query, entity_type, trail, findings, tool_calls)
               VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)""",
            (
                trail_id,
                context.user_id,
                context.run_id,
                context.node_id,
                query[:1000],
                findings.get("entity_type", ""),
                json.dumps(trail),
                json.dumps(findings.get("findings", [])),
                call_count,
            ),
        )
    except Exception as exc:
        log.warning("Failed to persist research trail: %s", exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _try_push(context: RunContext, event: dict) -> None:
    """Best-effort push_event (sync or async)."""
    try:
        result = context.push_event(event)
        if asyncio.iscoroutine(result):
            asyncio.create_task(result)
    except Exception:
        pass
