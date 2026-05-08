# Technique Catalog + Multi-Engine Meta-Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:[REDACTED:high-entropy-base64:27ch:hash=88f76bb3] (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-engine meta-search node, structured technique catalog, and plugin request DB cleanup.

**Architecture:** Multi-search dispatches to DDG + optional Serper/Brave/Exa in parallel with URL dedup and consensus ranking. Technique catalog is a Python registry mapping tactics to tool sequences, injected into the IS brain prompt. DB cleanup script rejects/approves existing plugin requests.

**Tech Stack:** Python 3.11, httpx, asyncio, pytest

---

## Tasks

### Task 1: Multi-Engine Meta-Search Node
- Create: `app/pipeline/nodes/multi_search.py`
- Test: `tests/pipeline/nodes/test_multi_search.py`
- TDD: test node metadata, DDG backend, dedup by URL, consensus scoring, execute with mocked backends

### Task 2: Register Multi-Search + Update Prompt
- Modify: `app/pipeline/nodes/__init__.py` — register MultiSearchNode
- Modify: `app/is_prompt.py` — add run_multi_search to static tools

### Task 3: Technique Catalog
- Create: `app/pipeline/techniques.py` — TECHNIQUES list + `format_techniques_for_prompt()`
- Test: `tests/pipeline/test_techniques.py`
- TDD: test catalog has entries, format produces readable text, all referenced tools exist

### Task 4: Inject Techniques into IS Brain Prompt
- Modify: `app/is_prompt.py` — add `{techniques_section}` placeholder between entity_strategy and strategies_section
- Modify: `app/is_prompt.py:build_prompt()` — add `techniques_section` param
- Modify: `app/routers/v3/agent.py` — load and pass techniques

### Task 5: Plugin Request DB Cleanup Script
- Create: `scripts/cleanup_plugin_requests.sql`
- SQL to reject duplicates, approve high-value, merge related

### Task 6: Integration Test
- Verify: multi_search registered, techniques in prompt, full flow
