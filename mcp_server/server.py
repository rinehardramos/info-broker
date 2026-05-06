"""FastMCP server — pipeline node tools for Claude Code IS brain."""
from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from mcp_server.client import api_call

mcp = FastMCP("info-broker")

# ---------------------------------------------------------------------------
# Pipeline node tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def run_ddg_search(query: str, max_results: int = 10) -> str:
    """Search the web using DuckDuckGo. Returns a list of results with title, url, and snippet."""
    result = await api_call(
        "POST",
        "/v3/nodes/ddg_search/execute",
        json={"query": query, "max_results": max_results},
    )
    return json.dumps(result)


@mcp.tool()
async def run_qdrant_search(
    query: str,
    collection: str = "search_results",
    limit: int = 20,
) -> str:
    """Semantic vector search over Qdrant collections.

    collection: 'search_results' or 'linkedin_profiles'
    """
    result = await api_call(
        "POST",
        "/v3/nodes/qdrant_search/execute",
        json={"query": query, "collection": collection, "limit": limit},
    )
    return json.dumps(result)


@mcp.tool()
async def run_rss_monitor(feed_url: str, max_items: int = 20) -> str:
    """Fetch and parse an RSS/Atom feed. Returns recent items with title, url, and summary."""
    result = await api_call(
        "POST",
        "/v3/nodes/rss_monitor/execute",
        json={"feed_url": feed_url, "max_items": max_items},
    )
    return json.dumps(result)


@mcp.tool()
async def run_apify_actor(
    actor_id: str = "harvestapi~linkedin-profile-search",
    search_url: str = "",
    max_items: int = 50,
) -> str:
    """Run an Apify actor (e.g. LinkedIn scraper). Returns structured profile results."""
    result = await api_call(
        "POST",
        "/v3/nodes/apify_actor/execute",
        json={"actor_id": actor_id, "searchUrl": search_url, "max_items": max_items},
    )
    return json.dumps(result)


@mcp.tool()
async def run_ai_scoring(
    items: str,
    criteria: str,
    score_field: str = "ai_score",
    model: str = "claude-haiku-4-5-20251001",
    threshold: int = 50,
) -> str:
    """Score a list of research items against given criteria using an LLM.

    items: JSON array of item objects.
    criteria: description of what makes an item high-quality.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/ai_scoring/execute",
        json={
            "items": json.loads(items),
            "criteria": criteria,
            "score_field": score_field,
            "model": model,
            "threshold": threshold,
        },
    )
    return json.dumps(result)


@mcp.tool()
async def run_ai_provider(
    prompt: str,
    model: str = "claude-haiku-4-5-20251001",
    system_prompt: str = "",
) -> str:
    """Send a prompt to an LLM provider and return the response text."""
    result = await api_call(
        "POST",
        "/v3/nodes/ai_provider/execute",
        json={"prompt": prompt, "model": model, "system_prompt": system_prompt},
    )
    return json.dumps(result)


@mcp.tool()
async def run_summarizer(
    items: str,
    instructions: str = "Summarize the key findings.",
    model: str = "claude-haiku-4-5-20251001",
) -> str:
    """Condense a list of research items into a structured summary.

    items: JSON array of item objects.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/summarizer/execute",
        json={"items": json.loads(items), "instructions": instructions, "model": model},
    )
    return json.dumps(result)


@mcp.tool()
async def run_web_crawl(
    urls: str,
    max_pages: int = 10,
    scrape_depth: int = 1,
) -> str:
    """Crawl one or more web pages and return their parsed text content.

    urls: JSON array of URL strings.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/web_crawl/execute",
        json={"urls": json.loads(urls), "max_pages": max_pages, "scrape_depth": scrape_depth},
    )
    return json.dumps(result)


@mcp.tool()
async def search_obsidian(query: str, collection: str = "obsidian_vault", top_k: int = 10) -> str:
    """Semantic search over an Obsidian vault stored in Qdrant. Returns note chunks ranked by relevance."""
    result = await api_call(
        "POST",
        "/v3/nodes/obsidian_vault/tool-invoke",
        json={"query": query, "collection": collection, "top_k": top_k},
    )
    return json.dumps(result)


@mcp.tool()
async def search_local_files(
    query: str,
    base_path: str,
    glob_pattern: str = "**/*.{md,txt}",
    max_files: int = 50,
) -> str:
    """Search local text/document files by content. base_path must be an absolute directory path."""
    result = await api_call(
        "POST",
        "/v3/nodes/local_files/tool-invoke",
        json={
            "query": query,
            "base_path": base_path,
            "glob_pattern": glob_pattern,
            "max_files": max_files,
        },
    )
    return json.dumps(result)


@mcp.tool()
async def run_manual_scoring(items: str, criteria: str = "") -> str:
    """Queue items for manual human scoring. Returns items tagged with a pending_review flag.

    items: JSON array of item objects.
    """
    result = await api_call(
        "POST",
        "/v3/nodes/manual_scoring/execute",
        json={"items": json.loads(items), "criteria": criteria},
    )
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Meta tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def save_pipeline(name: str, description: str, nodes: str, edges: str) -> str:
    """Save a reusable pipeline definition to the database.

    nodes: JSON array of pipeline node objects.
    edges: JSON array of pipeline edge objects.
    """
    result = await api_call(
        "POST",
        "/v3/pipelines",
        json={
            "name": name,
            "description": description,
            "nodes": json.loads(nodes),
            "edges": json.loads(edges),
        },
    )
    return json.dumps(result)


@mcp.tool()
async def save_research_trail(
    query: str,
    entity_type: str,
    findings: str,
    trail: str,
) -> str:
    """Persist research findings and the reasoning trail to the database.

    findings: JSON array of result items.
    trail: JSON object describing the research steps taken.
    """
    result = await api_call(
        "POST",
        "/v3/research-trails",
        json={
            "query": query,
            "entity_type": entity_type,
            "findings": json.loads(findings),
            "trail": json.loads(trail),
        },
    )
    return json.dumps(result)


@mcp.tool()
async def get_past_research(query: str, limit: int = 5) -> str:
    """Find related prior research by semantic similarity to the given query."""
    result = await api_call(
        "GET",
        "/v3/research-trails",
        params={"query": query, "limit": limit},
    )
    return json.dumps(result)


@mcp.tool()
async def suggest_plugin(name: str, description: str, reason: str) -> str:
    """Suggest a new plugin or tool that should be built into info-broker.

    Use this when you encounter a research task that is not supported by any existing tool.
    """
    result = await api_call(
        "POST",
        "/v3/plugin-requests",
        json={"name": name, "description": description, "reason": reason},
    )
    return json.dumps(result)
