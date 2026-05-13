# Claude Code as Intelligent Search Brain

**Date:** 2026-05-06
**Status:** Approved
**Scope:** Replace the current LLM-based IS orchestrator with Claude Code subprocess as the research brain

## Problem

The current Intelligent Search implementation uses a custom agentic loop in `intelligent_search.py` that calls LLMs via API. It works but is limited:
- Fixed tool set (only registered pipeline nodes)
- No web browsing capability (only DDG search wrapper)
- No ability to discover new tools/services on the fly
- No ability to assess and use unvetted web APIs
- Cannot generate reusable pipelines from research patterns
- Limited reasoning compared to Claude Code's full agentic capabilities

## Decision

Use Claude Code (subscription CLI) as the IS brain via subprocess invocation. Claude Code natively provides web access, file I/O, tool discovery, and sophisticated multi-step reasoning. Info-broker's pipeline nodes are exposed as MCP tools so Claude Code can call them during research.

## Architecture

```
info-broker UI (AgentChat, IS toggle ON)
  |
  v
IS Orchestrator (app/is_brain.py)
  |
  |-- 1. Build prompt (query + knowledge base context)
  |-- 2. Spawn: claude -p <prompt> --output-format json
  |-- 3. Parse output -> findings + pipeline + suggestions
  |-- 4. Store results, save pipeline, push to UI
  |
  v
Claude Code (subprocess)
  |
  |-- MCP: info-broker-mcp (pipeline nodes + data tools)
  |-- MCP: obsidian-vault-mcp (knowledge base)
  |-- Built-in: WebSearch, WebFetch, Bash, Read/Write
  |
  |-- Recursive tree search (LATS-inspired):
  |   BOOTSTRAP: warm start from knowledge base
  |   PLAN: map information landscape, create branch list
  |   RECURSE: explore branches, deepen or prune
  |   DISCOVER: find new tools/APIs on the fly
  |   DELIVER: summarize, save pipeline, report gaps
  |
  v
Structured JSON output -> info-broker stores and displays
```

### Key properties

- **Subprocess per query** -- each invocation is stateless. Claude externalizes memory through MCP tools (Qdrant, Postgres, Obsidian vault, memory files).
- **Full internet access** -- Claude Code has native WebSearch and WebFetch. It can browse, scrape, follow links, and discover APIs autonomously.
- **Pipeline generation** -- Claude outputs a reusable pipeline definition (nodes + edges + config) that info-broker saves and users can re-run without Claude Code.
- **Risk-based discovery** -- when Claude finds a useful tool on the web:
  - Low risk (public API, read-only, no auth): use immediately via WebFetch
  - High risk (requires auth, payment, write access): call suggest_plugin() to notify the user

## MCP Tools Surface

The info-broker MCP server is extended with pipeline node tools:

### Existing tools (unchanged)
- search -- Qdrant semantic search over ingested profiles
- get_profile / list_profiles -- profile data
- ingest -- pull profiles from Apify
- research -- run research agent on profiles
- get_news / get_weather / get_joke -- media tools

### New: Pipeline node tools
Each registered pipeline node is exposed as an MCP tool:

| MCP Tool | Pipeline Node | Purpose |
|----------|--------------|---------|
| run_ddg_search | ddg_search | Web search via DuckDuckGo |
| run_qdrant_search | qdrant_search | Semantic vector search |
| run_rss_monitor | rss_monitor | Fetch RSS/Atom feeds |
| run_apify_actor | apify_actor | Run Apify actors (LinkedIn, etc.) |
| run_ai_scoring | ai_scoring | LLM-based relevance scoring |
| run_ai_provider | ai_provider | Custom LLM prompts |
| run_summarizer | summarizer | Condense findings into report |
| run_web_crawl | web_crawl | Crawl websites with depth control |
| search_obsidian | obsidian_vault | Semantic search in Obsidian vault |
| search_local_files | local_files | Keyword search in local files |
| run_manual_scoring | manual_scoring | Rule-based scoring |

### New: Meta tools
| MCP Tool | Purpose |
|----------|---------|
| save_pipeline | Save a reusable pipeline definition (nodes, edges, config) |
| save_research_trail | Persist research findings to database |
| suggest_plugin | Create a plugin request notification for the user |
| get_past_research | Query research_trails for related prior research |
| get_user_preferences | Read user preferences and settings |

## Research Model: Recursive Tree Search

The research is NOT a linear pipeline. It is a **recursive tree** that branches and deepens until it reaches data (the "fruit") or hits dead ends.

```
Query: "Find info about Company X"
 |
 |-- depth 0: PLAN (what do we need?)
 |    |-- branch: company financials
 |    |   |-- depth 1: WebSearch "Company X funding"
 |    |   |-- depth 1: discover Crunchbase API
 |    |   |   |-- depth 2: read API docs, create ad-hoc accessor
 |    |   |   |-- depth 2: fetch funding data
 |    |   |   |-- FRUIT: $50M Series B
 |    |   |-- depth 1: run_ddg_search "Company X SEC filings"
 |    |       |-- depth 2: WebFetch SEC page
 |    |       |-- DEAD END: no public filings
 |    |
 |    |-- branch: company people (parallel with above)
 |    |   |-- depth 1: run_apify_actor (LinkedIn company search)
 |    |   |   |-- depth 2: found 3 executives
 |    |   |   |-- depth 2: for each exec -> branch deeper
 |    |   |       |-- depth 3: WebSearch "CTO name background"
 |    |   |       |-- FRUIT: CTO profile
 |    |   |-- depth 1: search_vault (local contacts)
 |    |       |-- FRUIT: existing notes on CEO
 |    |
 |    |-- branch: company product/tech
 |        |-- depth 1: run_web_crawl(companyx.com)
 |        |   |-- depth 2: analyze product pages
 |        |   |-- FRUIT: product descriptions
 |        |-- depth 1: get_news "Company X"
 |            |-- FRUIT: 3 recent articles
 |
 |-- ASSESS: have enough? need deeper?
 |    |-- signal: "social media presence unknown" -> go deeper
 |    |-- signal: "financials covered" -> stop this branch
 |    |-- signal: "need court records API" -> suggest_plugin()
 |
 |-- DELIVER: summarize, save pipeline, report gaps
```

### Key properties of the tree search

1. **Branching** -- at each node, Claude identifies multiple avenues to explore and pursues them. Each avenue is a branch that can itself branch further.

2. **Depth control** -- the brain tracks current depth and has a max_depth budget. At each level it assesses: "is there more data out there worth pursuing, or have I hit a dead end?"

3. **Parallel exploration** -- branches at the same depth are conceptually independent. Claude can explore company financials while simultaneously exploring company people. (In practice, Claude Code runs sequentially but reasons about them as parallel threads.)

4. **Dead end detection** -- when a branch yields no results or only low-confidence data, Claude marks it as a dead end and stops drilling. It doesn't waste tool budget on dry wells.

5. **Depth signaling** -- after each depth level, Claude reports:
   - `go_deeper`: "I found leads that need further investigation"
   - `sufficient`: "I have high-confidence data on this branch"
   - `dead_end`: "No data available through accessible sources"
   - `needs_tool`: "Data exists but I need a tool/API I don't have" -> suggest_plugin()

6. **Ad-hoc tool creation** -- when Claude discovers an API (e.g., reads Crunchbase API docs via WebFetch), it can create a one-off accessor using Bash/WebFetch to query it immediately, without needing a permanent plugin. If the API proves useful, it ALSO calls suggest_plugin() for permanent integration.

7. **Iterative refinement** -- findings from one branch inform other branches. If the financials branch reveals a subsidiary, Claude spawns a new branch to investigate it.

### Depth budget and termination

Claude receives a `max_depth` parameter (default 3, max 10) and a `max_branches` parameter (default 20, max 50). It terminates when:
- All branches are resolved (fruit or dead end)
- Depth budget exhausted
- Branch budget exhausted
- Claude assesses diminishing returns

At termination, Claude reports:
- Branches explored vs dead ends
- Depth reached per branch
- Whether deeper exploration would likely yield more data (for user to decide "go deeper")

### System prompt structure

The prompt encodes the tree search strategy:

**BOOTSTRAP** -- check knowledge base (get_past_research, search_vault, get_user_preferences) for warm start

**PLAN** -- analyze query, determine entity type, map the information landscape (what categories of data exist for this entity type), create initial branch list

**RECURSE** -- for each branch:
  1. Try available tools first (MCP tools, built-in WebSearch/WebFetch)
  2. If tool doesn't exist but data source is known: DISCOVER (search web for APIs, read docs, create ad-hoc accessor)
  3. Assess results: fruit (store), dead end (mark), or needs deeper (branch again)
  4. Report depth signal

**DELIVER** -- when tree is resolved:
  1. run_summarizer() on all findings
  2. save_research_trail() with full tree structure
  3. save_pipeline() with the successful branches as reusable nodes
  4. Return structured JSON with tree metadata

## Output Format

Claude Code returns structured JSON with tree metadata:

```json
{
  "summary": "Coherent research report",
  "entity_type": "person | company | product | event | concept",
  "findings": [
    {
      "source": "ddg_search | web_crawl | apify | adhoc_api | ...",
      "title": "Finding title",
      "content": "Detail text",
      "url": "source URL if applicable",
      "confidence": 85,
      "branch": "company_financials",
      "depth": 2
    }
  ],
  "tree": {
    "total_branches": 12,
    "resolved": 9,
    "dead_ends": 2,
    "needs_tool": 1,
    "max_depth_reached": 3,
    "branches": [
      {
        "name": "company_financials",
        "status": "fruit",
        "depth": 2,
        "findings_count": 3,
        "tools_used": ["WebSearch", "run_web_crawl"]
      },
      {
        "name": "sec_filings",
        "status": "dead_end",
        "depth": 2,
        "reason": "No public filings found"
      },
      {
        "name": "court_records",
        "status": "needs_tool",
        "depth": 1,
        "reason": "Requires PACER API access",
        "suggested_plugin": "pacer-court-records"
      }
    ],
    "can_go_deeper": true,
    "deeper_leads": ["Subsidiary 'SubCo' mentioned in filings - not yet investigated"]
  },
  "pipeline": {
    "name": "Research: <query_short>",
    "nodes": [...],
    "edges": [...]
  },
  "suggested_plugins": [
    {"name": "pacer-court-records", "description": "US court records via PACER", "reason": "Branch 'court_records' hit dead end - data exists behind this API"}
  ],
  "gaps": ["Social media presence unconfirmed", "No access to court records"]
}
```

The `tree` metadata enables the UI to:
- Show a visual branch tree (like ResearchFlow but tree-structured)
- Let the user click "Go Deeper" on specific branches
- See which branches bore fruit vs dead ends
- Understand why plugins are being suggested

### "Go Deeper" flow

When `can_go_deeper` is true, the UI shows a "Go Deeper" button with the `deeper_leads` list. Clicking it spawns a new Claude Code subprocess with:
- The original query
- The existing research trail (so Claude doesn't repeat work)
- A focused prompt: "Continue investigating these leads: {deeper_leads}"
- Higher depth budget (previous max_depth + 2)

Results merge into the existing research trail and pipeline.

## Model Strategy

Claude Code (Opus) serves as the tree navigator and orchestrator. Cheaper models handle leaf-node work via MCP tool calls:

| Role | Model | Rationale |
|------|-------|-----------|
| Tree navigation, branching decisions, API discovery | Claude Opus (via Claude Code) | Best agentic reasoning, handles complex multi-step planning |
| DDG search, web crawl, RSS fetch | No LLM needed | Direct API/scrape calls |
| Relevance scoring | Haiku 4.5 (via run_ai_scoring) | Simple classification, cheapest |
| Synthesis / summarization | Sonnet 4.6 (via run_summarizer) | Good writing quality, moderate cost |
| Ad-hoc API analysis | Claude Opus (via Claude Code) | Needs to read docs and reason about API structure |

Claude Code naturally handles the model cascade -- it uses Opus for its own reasoning but delegates tool calls to the MCP server, where each tool can use whatever model is configured in the node's config.

## Backend Integration

### New file: app/is_brain.py

The IS orchestrator:

1. Receives query from agent endpoint (when IS toggle is on)
2. Builds context: queries past research trails, user preferences
3. Constructs the system prompt with query and context
4. Spawns Claude Code: `claude -p <prompt> --output-format json --mcp-config <path>`
5. Parses JSON output
6. Stores findings in research_trails table
7. Creates pipeline from output (via pipelines API)
8. Creates plugin requests from suggested_plugins
9. Pushes results to frontend via WebSocket

### Modified: app/routers/v3/agent.py

When `use_intelligent_search=True`:
- Calls `is_brain.run_research(message, user_id)` instead of building a pipeline
- Creates a pipeline_run record for tracking
- Returns job_id to frontend

### MCP server extension

The info-broker MCP server (likely in a separate process or the existing one) adds tool handlers for each pipeline node. Each handler:
1. Instantiates the node from NodeRegistry
2. Creates a RunContext
3. Calls node.execute(config, inputs, context)
4. Returns results

For ToolCallable nodes (datastores), calls tool_invoke() directly.

## Knowledge Base Bootstrap

Claude Code starts each session by checking:
1. **Past research** -- get_past_research(query) finds related prior work via semantic similarity
2. **User preferences** -- get_user_preferences() returns scoring criteria, preferred sources, entity type hints
3. **Obsidian vault** -- search_vault(query) for any notes/knowledge on the topic
4. **Memory files** -- Claude's native memory system for patterns learned across sessions

This gives Claude a "warm start" even though each subprocess is stateless.

## Frontend Changes

Minimal:
- IS toggle behavior unchanged (sends use_intelligent_search=true)
- Results display unchanged (findings render in run tab)
- New: "Suggested Plugins" notification badge when suggest_plugin is called
- New: Generated pipeline appears in Pipeline tab after research completes

## File Changes Summary

| File | Change |
|------|--------|
| app/is_brain.py | **New** -- Claude Code subprocess orchestrator |
| app/routers/v3/agent.py | Modify -- IS path calls is_brain instead of building pipeline |
| info-broker-mcp tools | **New** -- pipeline node tools + meta tools |
| config/is-mcp-config.json | **New** -- MCP config for spawned Claude Code instance |
| frontend (minimal) | Suggested plugins notification |

## Testing

- **Unit**: Mock subprocess, verify prompt construction, output parsing, error handling
- **Integration**: Spawn real Claude Code with test MCP config, verify tool calls work
- **E2E**: Send IS query from UI, verify results appear, pipeline is saved, suggestions shown

## Future Enhancements (not in scope)

- Streaming: pipe Claude Code stdout for real-time progress events
- Cost tracking: parse total_cost_usd from Claude Code JSON output
- Multi-model: let Claude Code choose between models (Opus for complex, Haiku for simple)
- Parallel research: spawn multiple Claude Code instances for different aspects of a query
- Learning loop: Claude Code reviews its own pipeline outputs and refines for next run
