# Fast + Thorough Parallel Research — Design Spec

**Date:** 2026-05-10
**Status:** Draft

## Problem Statement

Currently the IS brain runs a single research pass that takes 1-4 minutes. The user waits with no results until it finishes. If the research is shallow (common), the user gets poor results after waiting. If thorough, the wait is long.

## Solution: Two-Phase Parallel Research

Every research query triggers TWO runs in parallel:

1. **Fast Run** (~15-30 seconds) — shallow search, limited tools, max depth 1, max 5 tool calls. Returns immediate results so the user sees something fast.

2. **Thorough Run** (1-4 minutes) — full strategy, all tools, max depth 3+, max 20+ tool calls. Runs in background while the user reviews fast results.

When the thorough run completes:
- The brain **analyzes both result sets** and selects the most feasible/complete answer
- All results from both runs are shown (thorough results added below fast results)
- A "confidence upgrade" indicator shows which findings were confirmed by the deeper search

## Architecture

```
User Query
    ↓
Research Orchestrator
    ├── Fast Run (spawn immediately)
    │   ├── max_depth: 1
    │   ├── max_branches: 5
    │   ├── tools: run_multi_search, run_ddg_search only
    │   ├── strategy: minimal (no full strategy injection)
    │   └── Returns in ~15-30s → display immediately
    │
    └── Thorough Run (spawn simultaneously)
        ├── max_depth: 3
        ├── max_branches: 20
        ├── tools: all 70+ registered nodes
        ├── strategy: full compiled strategy + technique catalog
        └── Returns in 1-4 min → merge with fast results

When thorough completes:
    ↓
Analysis Phase:
    ├── Deduplicate findings across both runs
    ├── Mark which fast-run findings were confirmed by thorough run
    ├── Identify new findings from thorough run not in fast run
    ├── Rank by feasibility to the user's prompt
    └── Present: fast results (with confirmation badges) + thorough-only results
```

## Implementation

### Backend Changes

**New config in IS brain runner** (`app/routers/v3/agent.py`):

```python
# In _run_is_research():
# Phase 1: Fast run
fast_result = await run_research(
    query=query,
    max_depth=1,
    max_branches=5,
    entity_strategy="",  # No strategy injection for speed
    techniques_section="",  # Skip technique catalog
    strategies_section="",  # Skip procedural memory
)
# Push fast results to frontend immediately via WebSocket

# Phase 2: Thorough run (already running in parallel via asyncio.create_task)
thorough_result = await thorough_task

# Phase 3: Merge
merged = merge_research_results(fast_result, thorough_result, query)
```

**New function: `merge_research_results()`** in `app/pipeline/fusion/merger.py`:

```python
def merge_research_results(fast: dict, thorough: dict, query: str) -> dict:
    """Merge fast and thorough results, dedup, mark confirmations."""
    fast_findings = fast.get("findings", [])
    thorough_findings = thorough.get("findings", [])
    
    # Deduplicate by URL/title similarity
    merged = []
    for ff in fast_findings:
        confirmed = any(similar(ff, tf) for tf in thorough_findings)
        ff["confirmed_by_thorough"] = confirmed
        ff["phase"] = "fast"
        merged.append(ff)
    
    for tf in thorough_findings:
        if not any(similar(tf, ff) for ff in fast_findings):
            tf["phase"] = "thorough"
            tf["confirmed_by_thorough"] = True
            merged.append(tf)
    
    return {
        "findings": merged,
        "fast_count": len(fast_findings),
        "thorough_count": len(thorough_findings),
        "merged_count": len(merged),
        "confirmed_count": sum(1 for f in merged if f.get("confirmed_by_thorough")),
    }
```

### Frontend Changes

**Two-phase display in Agent chat:**

Phase 1 (fast results arrive):
```
┌─────────────────────────────────────────┐
│ ● Fast Results (5 findings in 18s)      │
│                                         │
│ [B2] LinkedIn profile found...          │
│ [C3] Web search result...               │
│                                         │
│ ⏳ Thorough research in progress...     │
│ ████████░░░░░░░░ 45%                    │
└─────────────────────────────────────────┘
```

Phase 2 (thorough results arrive):
```
┌─────────────────────────────────────────┐
│ ● Fast Results (5 findings in 18s)      │
│                                         │
│ [B2] LinkedIn profile found... ✓ confirmed│
│ [C3] Web search result...     ✓ confirmed│
│                                         │
│ ● Thorough Results (+12 findings, 2m)   │
│                                         │
│ [A1] HIBP breach confirmed...  NEW      │
│ [A1] SEC filing verified...    NEW      │
│ [B2] Instagram profile...      NEW      │
│ ... 9 more                              │
│                                         │
│ Investigation Breakdown         [B]     │
└─────────────────────────────────────────┘
```

### Settings

- `fast_thorough_mode`: toggle in core_settings (default: "true")
- When disabled, only the thorough run executes (current behavior)
- Fast run timeout: 30 seconds max
- Fast run never triggers post-run hooks (no scorecard, no overlays, no KG write — only thorough run does)

### WebSocket Events

New events for the two-phase flow:
- `research.fast.started` — fast run begins
- `research.fast.completed` — fast results ready (includes findings)
- `research.thorough.started` — thorough run begins
- `research.thorough.progress` — progress updates (tool calls, branch count)
- `research.thorough.completed` — thorough results ready (includes merged findings)

## Implementation Phases

### Phase A: Result Merger (backend)
- `app/pipeline/fusion/merger.py` — merge + dedup + confirmation badges
- Tests for merging, dedup, confirmation marking

### Phase B: Parallel Execution (backend)
- Modify `agent.py` to spawn fast + thorough in parallel
- Fast run with reduced params
- WebSocket events for two-phase updates

### Phase C: Two-Phase UI (frontend)
- Update ResultsPanel to show fast results → progress bar → thorough results
- Confirmation badges ("✓ confirmed" vs "NEW")
- Progressive rendering

## Key Design Decisions

1. **Fast run has NO strategy injection** — pure speed, just web search
2. **Only thorough run triggers post-run hooks** — scorecard, overlays, KG, skill creation
3. **Merge is done server-side** — not in the frontend, so the merged result is consistent
4. **Settings-gated** — can be toggled off for users who prefer single thorough run
