# Claude Code IS Brain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-execution (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current LLM-based IS orchestrator with Claude Code subprocess that performs recursive tree-search research, auto-discovers tools, and generates reusable pipelines.

**Architecture:** When IS toggle is ON, the backend spawns `claude -p <prompt> --output-format json` with a structured research prompt. Claude Code has info-broker-mcp tools available (pipeline nodes, meta tools). Output is parsed into findings + pipeline + suggestions and stored.

**Tech Stack:** Claude Code CLI (subprocess), Python asyncio, info-broker MCP server, existing pipeline infrastructure.

**Prerequisite:** The info-broker MCP server must be extended with pipeline node tools (run_ddg_search, run_web_crawl, etc.) and meta tools (save_pipeline, save_research_trail, suggest_plugin). That is a separate plan for the mcp-servers project.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `app/is_brain.py` | **New.** Claude Code subprocess orchestrator -- builds prompt, spawns process, parses output |
| `app/is_prompt.py` | **New.** System prompt template for the recursive tree search strategy |
| `app/routers/v3/agent.py` | **Modify.** IS path calls is_brain instead of _build_is_pipeline |
| `tests/test_is_brain.py` | **New.** Unit tests (mock subprocess) |
| `config/is-mcp-config.json` | **New.** MCP config for spawned Claude Code instance |

---

### Task 1: Create IS prompt template

**Files:**
- Create: `app/is_prompt.py`

- [ ] **Step 1: Create the prompt module**

```python
"""System prompt for Claude Code IS brain.

This prompt encodes the recursive tree search strategy:
BOOTSTRAP -> PLAN -> RECURSE -> DELIVER
"""

RESEARCH_PROMPT = """\
You are an intelligent research agent for info-broker. Your mission is to find \
comprehensive, high-confidence information about the user's query using a \
recursive tree search strategy.

QUERY: {query}

{context_section}

## YOUR WORKFLOW

### BOOTSTRAP
Check the knowledge base for a warm start:
- Call get_past_research to find related prior research
- Call search (Qdrant semantic search) for existing data
- Call search_vault for Obsidian notes on this topic

### PLAN
Analyze the query:
1. Determine the ENTITY TYPE (person, company, product, event, concept)
2. Map the INFORMATION LANDSCAPE -- what categories of data exist for this entity type
3. Create an initial BRANCH LIST -- each branch is an avenue of investigation
4. Estimate which branches are most likely to yield results

### RECURSE
For each branch, explore recursively up to depth {max_depth}:
1. Try available MCP tools first (run_ddg_search, run_web_crawl, run_apify_actor, etc.)
2. If a tool doesn't exist but you know the data source: DISCOVER
   - Search the web for APIs, Apify actors, or services
   - Read API documentation via WebFetch
   - LOW RISK (public, read-only, no auth): use immediately via WebFetch/Bash
   - HIGH RISK (requires auth, payment, write access): call suggest_plugin
3. Assess each result:
   - FRUIT: high-confidence finding -- store it
   - DEAD END: no data available -- mark and stop this branch
   - NEEDS DEEPER: promising leads found -- branch again (increase depth)
   - NEEDS TOOL: data exists behind an inaccessible API -- call suggest_plugin
4. Findings from one branch can spawn new branches (e.g., discovering a subsidiary)

### DELIVER
When all branches are resolved (fruit, dead end, or budget exhausted):
1. Call run_summarizer with all findings to create a coherent report
2. Call save_research_trail with the full tree structure
3. Call save_pipeline with the nodes and config that worked (so the user can re-run)

## BUDGET
- Max depth: {max_depth} levels deep per branch
- Max branches: {max_branches} total branches

## OUTPUT FORMAT
Return your final answer as a JSON object with this structure:
{{
  "summary": "Coherent research report (2-3 paragraphs)",
  "entity_type": "person | company | product | event | concept",
  "findings": [
    {{
      "source": "tool_name or adhoc_api",
      "title": "Finding title",
      "content": "Detail text",
      "url": "source URL if applicable",
      "confidence": 85,
      "branch": "branch_name",
      "depth": 2
    }}
  ],
  "tree": {{
    "total_branches": 12,
    "resolved": 9,
    "dead_ends": 2,
    "needs_tool": 1,
    "max_depth_reached": 3,
    "branches": [
      {{
        "name": "branch_name",
        "status": "fruit | dead_end | needs_tool | depth_exhausted",
        "depth": 2,
        "findings_count": 3,
        "tools_used": ["tool1", "tool2"],
        "reason": "why this status (for dead_end/needs_tool)"
      }}
    ],
    "can_go_deeper": true,
    "deeper_leads": ["leads that need further investigation"]
  }},
  "pipeline": {{
    "name": "Research: query_short",
    "nodes": [
      {{"node_type": "ddg_search", "label": "DDG Search", "config": {{}}}},
      {{"node_type": "ai_scoring", "label": "Relevance Filter", "config": {{}}}}
    ],
    "edges": [
      {{"source_index": 0, "target_index": 1}}
    ]
  }},
  "suggested_plugins": [
    {{"name": "plugin-id", "description": "what it does", "reason": "why it is needed"}}
  ],
  "gaps": ["things that could not be found"]
}}
"""


def build_prompt(
    query: str,
    max_depth: int = 3,
    max_branches: int = 20,
    past_research: list[dict] | None = None,
    user_preferences: dict | None = None,
) -> str:
    """Build the full research prompt with context."""
    context_parts = []
    if past_research:
        summaries = []
        for r in past_research[:3]:
            summaries.append(f"- Query: {r.get('query', '?')} | Findings: {len(r.get('findings', []))}")
        context_parts.append("PAST RESEARCH (related):\\n" + "\\n".join(summaries))
    if user_preferences:
        context_parts.append(f"USER PREFERENCES: {user_preferences}")

    context_section = "\\n\\n".join(context_parts) if context_parts else "No prior context available."

    return RESEARCH_PROMPT.format(
        query=query,
        context_section=context_section,
        max_depth=max_depth,
        max_branches=max_branches,
    )
```

- [ ] **Step 2: Commit**

```bash
git add app/is_prompt.py
git commit -m "feat: add IS brain system prompt template"
```

---

### Task 2: Write IS brain tests (RED)

**Files:**
- Create: `tests/test_is_brain.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_is_brain.py` with 5 tests:

1. `test_build_prompt_includes_query` -- call `build_prompt("test query")`, assert "test query" appears in result
2. `test_build_prompt_includes_depth` -- call `build_prompt("q", max_depth=5)`, assert "5" appears
3. `test_run_research_parses_json_output` -- mock `asyncio.create_subprocess_exec` to return valid JSON stdout, call `run_research("query", "user-1")`, assert findings are parsed
4. `test_run_research_handles_claude_error` -- mock subprocess to return non-zero exit code, assert `run_research` returns error result (not raises)
5. `test_run_research_handles_invalid_json` -- mock subprocess stdout with non-JSON text, assert `run_research` returns fallback result with raw text as summary

All tests mock the subprocess -- no real Claude Code invocation.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_is_brain.py -v`
Expected: FAIL -- ModuleNotFoundError for app.is_brain

- [ ] **Step 3: Commit**

```bash
git add tests/test_is_brain.py
git commit -m "test: add failing tests for IS brain orchestrator"
```

---

### Task 3: Implement IS brain orchestrator (GREEN)

**Files:**
- Create: `app/is_brain.py`

- [ ] **Step 1: Write the orchestrator**

```python
"""IS Brain -- Claude Code subprocess orchestrator.

Spawns Claude Code with a recursive tree search prompt and
info-broker MCP tools. Parses structured JSON output into
findings, pipeline definition, and plugin suggestions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from app.is_prompt import build_prompt

log = logging.getLogger(__name__)

# Path to MCP config for spawned Claude Code instance
_MCP_CONFIG = Path(__file__).parent.parent / "config" / "is-mcp-config.json"

# Claude Code binary
_CLAUDE_BIN = os.getenv("CLAUDE_CODE_BIN", "claude")


async def run_research(
    query: str,
    user_id: str,
    max_depth: int = 3,
    max_branches: int = 20,
    past_research: list[dict] | None = None,
    user_preferences: dict | None = None,
) -> dict[str, Any]:
    """Run a research query via Claude Code subprocess.

    Returns a dict with: summary, findings, tree, pipeline,
    suggested_plugins, gaps. On error, returns a minimal result
    with the error in summary.
    """
    prompt = build_prompt(
        query=query,
        max_depth=max_depth,
        max_branches=max_branches,
        past_research=past_research,
        user_preferences=user_preferences,
    )

    cmd = [_CLAUDE_BIN, "-p", prompt, "--output-format", "json"]

    # Add MCP config if it exists
    if _MCP_CONFIG.exists():
        cmd.extend(["--mcp-config", str(_MCP_CONFIG)])

    log.info("IS Brain: spawning Claude Code for query: %s", query[:80])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "CLAUDE_CODE_HEADLESS": "1"},
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=int(os.getenv("IS_BRAIN_TIMEOUT", "300")),
        )

        if proc.returncode != 0:
            err_msg = stderr.decode(errors="replace").strip()
            log.error("IS Brain: Claude Code exited %d: %s", proc.returncode, err_msg)
            return _error_result(query, f"Claude Code error (exit {proc.returncode}): {err_msg}")

        return _parse_output(query, stdout.decode(errors="replace"))

    except asyncio.TimeoutError:
        log.error("IS Brain: timed out after %ss", os.getenv("IS_BRAIN_TIMEOUT", "300"))
        return _error_result(query, "Research timed out")
    except FileNotFoundError:
        log.error("IS Brain: claude binary not found at %s", _CLAUDE_BIN)
        return _error_result(query, f"Claude Code not found at {_CLAUDE_BIN}")
    except Exception as exc:
        log.error("IS Brain: unexpected error: %s", exc)
        return _error_result(query, str(exc))


def _parse_output(query: str, raw: str) -> dict[str, Any]:
    """Parse Claude Code JSON output into research results."""
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("IS Brain: non-JSON output, using raw text as summary")
        return _fallback_result(query, raw)

    # Claude Code wraps output in {"result": "...", "type": "result", ...}
    result_text = envelope.get("result", "")

    # The result field may itself be JSON (our structured output)
    try:
        research = json.loads(result_text)
        if isinstance(research, dict) and "findings" in research:
            return research
    except (json.JSONDecodeError, TypeError):
        pass

    # If result is plain text, wrap it
    return _fallback_result(query, result_text or raw)


def _fallback_result(query: str, text: str) -> dict[str, Any]:
    """Wrap unstructured text into the expected output format."""
    return {
        "summary": text[:2000],
        "entity_type": "unknown",
        "findings": [],
        "tree": {"total_branches": 0, "resolved": 0, "dead_ends": 0,
                 "needs_tool": 0, "max_depth_reached": 0, "branches": [],
                 "can_go_deeper": False, "deeper_leads": []},
        "pipeline": None,
        "suggested_plugins": [],
        "gaps": ["Research output was unstructured"],
    }


def _error_result(query: str, error: str) -> dict[str, Any]:
    """Return error as a research result."""
    return {
        "summary": f"Research failed: {error}",
        "entity_type": "unknown",
        "findings": [],
        "tree": {"total_branches": 0, "resolved": 0, "dead_ends": 0,
                 "needs_tool": 0, "max_depth_reached": 0, "branches": [],
                 "can_go_deeper": False, "deeper_leads": []},
        "pipeline": None,
        "suggested_plugins": [],
        "gaps": [error],
    }
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_is_brain.py -v`
Expected: All 5 pass

- [ ] **Step 3: Commit**

```bash
git add app/is_brain.py
git commit -m "feat: implement IS brain Claude Code subprocess orchestrator"
```

---

### Task 4: Create MCP config for spawned Claude Code

**Files:**
- Create: `config/is-mcp-config.json`

- [ ] **Step 1: Create the config**

This config tells the spawned Claude Code instance where to find the info-broker MCP server. It mirrors the existing `~/.claude/settings.json` config but is self-contained:

```json
{
  "mcpServers": {
    "info-broker-mcp": {
      "command": "/usr/local/bin/docker",
      "args": [
        "run", "--rm", "-i",
        "--network", "host",
        "-e", "INFO_BROKER_URL",
        "-e", "INFO_BROKER_API_KEY",
        "mcp-servers:latest",
        "python", "-m", "info_broker_mcp"
      ]
    }
  }
}
```

Note: `INFO_BROKER_URL` and `INFO_BROKER_API_KEY` are inherited from the parent process environment (the Docker `-e VAR` syntax without `=value` passes the parent's value).

- [ ] **Step 2: Commit**

```bash
git add config/is-mcp-config.json
git commit -m "feat: add MCP config for IS brain Claude Code subprocess"
```

---

### Task 5: Wire IS brain into agent endpoint

**Files:**
- Modify: `app/routers/v3/agent.py`

- [ ] **Step 1: Replace _build_is_pipeline with is_brain call**

In `agent.py`, modify the IS branch in `send_message()`. Instead of building a single-node pipeline and launching via Temporal, call `is_brain.run_research()` directly and store the results:

Replace the IS-on block (currently lines 149-161):

```python
    if body.use_intelligent_search:
        from app.is_brain import run_research
        from app.routers.v3.db import execute, fetch_one

        # Create pipeline_run for tracking
        fetch_one(
            """
            INSERT INTO pipeline_runs (id, pipeline_id, user_id, temporal_workflow_id, status, trigger_type)
            VALUES (%s, %s, %s, %s, 'running', 'agent_is')
            RETURNING *
            """,
            (run_id, pipeline_id, uid, workflow_id),
        )

        # Run research via Claude Code (async, may take minutes)
        try:
            result = await run_research(
                query=body.message,
                user_id=uid,
                max_depth=3,
                max_branches=20,
            )

            # Store research trail
            execute(
                """
                INSERT INTO research_trails (id, user_id, run_id, query, entity_type, trail, findings, tool_calls)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid.uuid4()), uid, run_id, body.message,
                    result.get("entity_type", "unknown"),
                    json.dumps(result.get("tree", {})),
                    json.dumps(result.get("findings", [])),
                    result.get("tree", {}).get("total_branches", 0),
                ),
            )

            # Create pipeline from output if one was generated
            if result.get("pipeline"):
                # Save via pipelines API (reuse existing create logic)
                pass  # TODO: wire to createPipeline in a follow-up task

            # Create plugin requests
            for plugin in result.get("suggested_plugins", []):
                execute(
                    "INSERT INTO plugin_requests (id, user_id, spec, status) VALUES (%s, %s, %s, 'pending')",
                    (str(uuid.uuid4()), uid, json.dumps(plugin)),
                )

            # Mark run as succeeded
            execute(
                "UPDATE pipeline_runs SET status = 'succeeded', finished_at = now() WHERE id = %s",
                (run_id,),
            )

        except Exception as exc:
            log.error("IS Brain failed: %s", exc)
            execute(
                "UPDATE pipeline_runs SET status = 'failed', finished_at = now() WHERE id = %s",
                (run_id,),
            )

        return AgentMessageOut(job_id=run_id)
```

Keep the `else` branch unchanged (normal pipeline flow).

- [ ] **Step 2: Add json import if not present**

Ensure `import json` is at the top of agent.py.

- [ ] **Step 3: Remove _build_is_pipeline function**

Delete the `_build_is_pipeline` function (lines 109-127) -- it's no longer used.

- [ ] **Step 4: Run existing agent tests**

Run: `uv run pytest tests/v3/test_agent.py -v`
Expected: Existing tests pass (they don't use IS toggle)

- [ ] **Step 5: Commit**

```bash
git add app/routers/v3/agent.py
git commit -m "feat: wire IS brain into agent endpoint, bypass Temporal for IS"
```

---

### Task 6: End-to-end test

**No new files -- manual verification against live stack.**

- [ ] **Step 1: Rebuild API**

```bash
cd /Users/rinehardramos/Projects/info-broker
docker compose up -d --build info-broker-api
```

- [ ] **Step 2: Test IS via API**

```bash
TOKEN=$(curl -s http://localhost:8000/v3/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s http://localhost:8000/v3/agent/message \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message":"find info about OpenBao secrets manager","use_intelligent_search":true}'
```

Expected: 202 with job_id. After 30-120 seconds, the run status should be `succeeded` with findings in research_trails.

- [ ] **Step 3: Verify results stored**

```bash
RUN_ID=<job_id_from_step_2>
curl -s "http://localhost:8000/v3/pipelines/runs/$RUN_ID" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Expected: `status: succeeded`, `trigger_type: agent_is`

- [ ] **Step 4: Check research trail**

```bash
docker exec info-broker-postgres-1 psql -U user -d info_broker -c \
  "SELECT query, entity_type, tool_calls, created_at FROM research_trails ORDER BY created_at DESC LIMIT 3;"
```

Expected: Row with query "find info about OpenBao secrets manager"
