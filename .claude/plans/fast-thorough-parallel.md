# Fast + Thorough Parallel Research — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:[REDACTED:high-entropy-base64:27ch:hash=88f76bb3] to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every IS research query spawns two parallel runs — a fast preview (~15-30s, depth 1, 5 branches) and a thorough run (full strategy, depth 3+). Fast results display immediately; thorough results merge in when done, marking confirmed findings and surfacing new ones.

**Architecture:** `merger.py` handles server-side deduplication and confidence marking; `_run_is_research` in `agent.py` uses `asyncio.gather` for parallel execution; new WebSocket events drive two-phase frontend display in `ResultsPanel.tsx`. Settings gate allows opting out.

**Tech Stack:** Python 3.14, asyncio, FastAPI, pytest; TypeScript/React (ResultsPanel)

---

## Background — current code shape

- `_run_is_research(run_id, uid, pipeline_id, query, ...)` at `app/routers/v3/agent.py:355` is the background task; it calls `run_research(...)` at line 562
- `app/pipeline/fusion/` has `ach.py`, `pir.py`, `scorecard.py` etc but **no** `merger.py`
- WebSocket events pushed via `push_event(uid, {...})` from `app/routers/v3/stream`
- `run_research` returns `dict` with `findings: list[dict]`, `summary: str`, etc.
- Each finding has at minimum: `url`, `title`, `confidence`, `branch`, `source_class`

---

## Phase A — Backend merger (standalone, mergeable independently)

**Files:**
- Create: `app/pipeline/fusion/merger.py`
- Create: `tests/pipeline/fusion/test_merger.py`

### Task A1: Write failing tests first

- [ ] **Step A1.1: Create test file**

```python
"""TDD tests for app.pipeline.fusion.merger."""
import pytest
from app.pipeline.fusion.merger import merge_research_results, _findings_similar

FINDING_A = {
    "url": "https://example.com/profile/alice",
    "title": "Alice Johnson — LinkedIn",
    "confidence": 75,
    "branch": "linkedin",
    "source_class": "B2",
}
FINDING_B = {
    "url": "https://example.com/profile/alice",
    "title": "Alice Johnson | LinkedIn Profile",
    "confidence": 80,
    "branch": "deep_search",
    "source_class": "B2",
}
FINDING_C = {
    "url": "https://news.example.com/article/acme-corp",
    "title": "Acme Corp raises funding",
    "confidence": 85,
    "branch": "news",
    "source_class": "A1",
}
FAST_RESULT  = {"findings": [FINDING_A], "summary": "Fast result"}
THOROUGH_RESULT = {"findings": [FINDING_B, FINDING_C], "summary": "Thorough result"}


# --- _findings_similar ---

def test_same_url_is_similar():
    assert _findings_similar(FINDING_A, FINDING_B) is True

def test_different_url_different_title_not_similar():
    assert _findings_similar(FINDING_A, FINDING_C) is False

def test_similar_title_no_url_match():
    a = {"url": "https://a.example.com/x", "title": "Alice Johnson Senior Engineer"}
    b = {"url": "https://b.example.com/y", "title": "Alice Johnson — Senior Engineer"}
    assert _findings_similar(a, b) is True   # title similarity >= threshold

def test_unrelated_titles_not_similar():
    a = {"url": "https://a.example.com/x", "title": "Acme Corp Funding Round"}
    b = {"url": "https://b.example.com/y", "title": "Bob Smith Career History"}
    assert _findings_similar(a, b) is False


# --- merge_research_results ---

def test_fast_finding_confirmed_when_thorough_has_similar():
    merged = merge_research_results(FAST_RESULT, THOROUGH_RESULT, "alice johnson")
    fast_f = next(f for f in merged["findings"] if f["phase"] == "fast")
    assert fast_f["confirmed_by_thorough"] is True

def test_thorough_only_finding_marked_new():
    merged = merge_research_results(FAST_RESULT, THOROUGH_RESULT, "alice johnson")
    thorough_only = [f for f in merged["findings"] if f["phase"] == "thorough"]
    # FINDING_C (news) has no match in fast → should appear as thorough-only
    assert any(f["url"] == FINDING_C["url"] for f in thorough_only)

def test_counts_are_correct():
    merged = merge_research_results(FAST_RESULT, THOROUGH_RESULT, "alice johnson")
    assert merged["fast_count"] == 1
    assert merged["thorough_count"] == 2
    assert merged["merged_count"] == len(merged["findings"])

def test_confirmed_count():
    merged = merge_research_results(FAST_RESULT, THOROUGH_RESULT, "alice johnson")
    assert merged["confirmed_count"] == sum(
        1 for f in merged["findings"] if f.get("confirmed_by_thorough")
    )

def test_empty_fast_result_all_thorough():
    merged = merge_research_results(
        {"findings": [], "summary": ""},
        THOROUGH_RESULT,
        "query",
    )
    assert all(f["phase"] == "thorough" for f in merged["findings"])
    assert merged["confirmed_count"] == len(merged["findings"])

def test_empty_thorough_result_fast_unconfirmed():
    merged = merge_research_results(
        FAST_RESULT,
        {"findings": [], "summary": ""},
        "query",
    )
    fast_f = merged["findings"][0]
    assert fast_f["confirmed_by_thorough"] is False
    assert fast_f["phase"] == "fast"
```

- [ ] **Step A1.2: Run to confirm RED**

```bash
.venv/bin/python -m pytest tests/pipeline/fusion/test_merger.py -v 2>&1 | tail -10
```
Expected: `ModuleNotFoundError: No module named 'app.pipeline.fusion.merger'`

### Task A2: Implement merger.py

- [ ] **Step A2.1: Create `app/pipeline/fusion/merger.py`**

```python
from __future__ import annotations

import re


def _normalize_title(title: str) -> set[str]:
    """Return lowercase word tokens, stripped of stopwords."""
    stopwords = {"the", "a", "an", "and", "or", "in", "on", "at", "of", "for",
                 "to", "with", "by", "is", "are", "was", "were"}
    tokens = re.findall(r"[a-z0-9]+", title.lower())
    return {t for t in tokens if t not in stopwords and len(t) > 1}


def _findings_similar(a: dict, b: dict) -> bool:
    """Return True if two findings refer to the same source.

    Identical URL is an exact match.
    Shared word overlap ≥ 0.7 of the shorter title's tokens is a near-match.
    """
    url_a = (a.get("url") or "").strip().rstrip("/")
    url_b = (b.get("url") or "").strip().rstrip("/")
    if url_a and url_b and url_a == url_b:
        return True

    tokens_a = _normalize_title(a.get("title") or "")
    tokens_b = _normalize_title(b.get("title") or "")
    if not tokens_a or not tokens_b:
        return False

    overlap = tokens_a & tokens_b
    shorter = min(len(tokens_a), len(tokens_b))
    return len(overlap) / shorter >= 0.7


def merge_research_results(fast: dict, thorough: dict, query: str) -> dict:
    """Merge fast and thorough IS research results.

    - Fast findings are marked confirmed_by_thorough=True when a similar
      finding exists in the thorough run.
    - Thorough findings that have no fast counterpart are appended as
      phase='thorough' with confirmed_by_thorough=True (they are the
      authoritative deeper result).

    Returns the merged dict with added metadata counts.
    """
    fast_findings = list(fast.get("findings") or [])
    thorough_findings = list(thorough.get("findings") or [])

    merged: list[dict] = []

    for ff in fast_findings:
        confirmed = any(_findings_similar(ff, tf) for tf in thorough_findings)
        merged.append({**ff, "phase": "fast", "confirmed_by_thorough": confirmed})

    for tf in thorough_findings:
        if not any(_findings_similar(tf, ff) for ff in fast_findings):
            merged.append({**tf, "phase": "thorough", "confirmed_by_thorough": True})

    confirmed_count = sum(1 for f in merged if f.get("confirmed_by_thorough"))

    return {
        **thorough,                          # base: use thorough summary/metadata
        "findings": merged,
        "fast_count": len(fast_findings),
        "thorough_count": len(thorough_findings),
        "merged_count": len(merged),
        "confirmed_count": confirmed_count,
    }
```

- [ ] **Step A2.2: Run to confirm GREEN**

```bash
.venv/bin/python -m pytest tests/pipeline/fusion/test_merger.py -v 2>&1 | tail -15
```
Expected: all 10 tests pass.

- [ ] **Step A2.3: Commit**

```bash
git add app/pipeline/fusion/merger.py tests/pipeline/fusion/test_merger.py
git commit -m "feat(merger): merge_research_results — dedup, phase tagging, confirmation marking (10 tests)"
```

---

## Phase B — Parallel execution in agent.py

**Files:**
- Modify: `app/routers/v3/agent.py` (lines 355–900 area)
- Modify: `app/routers/v3/db.py` (add fast_thorough_mode to core_settings migration)

### Task B1: Settings gate

- [ ] **Step B1.1: Add fast_thorough_mode to core_settings schema in `app/routers/v3/db.py`**

Find the `core_settings` INSERT/default block and add:
```sql
INSERT INTO core_settings (key, value) VALUES ('fast_thorough_mode', 'true')
ON CONFLICT (key) DO NOTHING;
```

- [ ] **Step B1.2: Add helper in agent.py**

Near the top of `agent.py`, after imports, add:

```python
def _fast_thorough_enabled() -> bool:
    """Return True if fast+thorough parallel mode is on (default: True)."""
    try:
        from app.routers.v3.db import fetch_one as _fo
        row = _fo("SELECT value FROM core_settings WHERE key = 'fast_thorough_mode'", ())
        return (row or {}).get("value", "true").lower() != "false"
    except Exception:
        return True
```

### Task B2: Parallel execution in `_run_is_research`

- [ ] **Step B2.1: Read the current `run_research` call at line 562**

```bash
sed -n '555,580p' app/routers/v3/agent.py
```

Note the exact kwargs passed to `run_research()`. The fast run passes `max_depth=1`, `max_branches=5`, and omits `strategies_section`, `entity_strategy`, `techniques_section`, `meta_strategies_section`.

- [ ] **Step B2.2: Replace single `run_research` call with parallel execution**

In `_run_is_research`, replace the single `run_research(...)` call (currently at line ~562) with:

```python
from app.pipeline.fusion.merger import merge_research_results as _merge

if _fast_thorough_enabled():
    # Spawn fast and thorough in parallel
    fast_task = asyncio.create_task(run_research(
        query=query, user_id=uid, past_research=past_research,
        max_depth=1, max_branches=5,
        on_event=_on_tool_event,
        available_nodes=healthy_nodes,
        strategies_section="",      # no strategy injection for speed
        entity_strategy="",
        techniques_section="",
        meta_strategies_section="",
        user_sources=user_sources,
        session_context=session_context,
    ))
    thorough_task = asyncio.create_task(run_research(
        query=query, user_id=uid, past_research=past_research,
        max_depth=max_depth, max_branches=max_branches,
        on_event=_on_tool_event,
        available_nodes=healthy_nodes,
        strategies_section=strategies_section,
        entity_strategy=entity_strategy,
        techniques_section=techniques_section,
        meta_strategies_section=meta_strategies_section,
        user_sources=user_sources,
        session_context=session_context,
    ))

    await push_event(uid, {"type": "research.fast.started", "run_id": run_id})
    await push_event(uid, {"type": "research.thorough.started", "run_id": run_id})

    fast_result, thorough_result = await asyncio.gather(fast_task, thorough_task)

    await push_event(uid, {
        "type": "research.fast.completed", "run_id": run_id,
        "findings": fast_result.get("findings", []),
        "count": len(fast_result.get("findings", [])),
    })

    result = _merge(fast_result, thorough_result, query)

    await push_event(uid, {
        "type": "research.thorough.completed", "run_id": run_id,
        "findings": result.get("findings", []),
        "confirmed_count": result["confirmed_count"],
        "merged_count": result["merged_count"],
    })
else:
    # Original single-run path (unchanged)
    result = await run_research(
        query=query, user_id=uid, past_research=past_research,
        max_depth=max_depth, max_branches=max_branches,
        on_event=_on_tool_event,
        available_nodes=healthy_nodes,
        strategies_section=strategies_section,
        entity_strategy=entity_strategy,
        techniques_section=techniques_section,
        meta_strategies_section=meta_strategies_section,
        user_sources=user_sources,
        session_context=session_context,
    )
```

- [ ] **Step B2.3: Write smoke test for settings gate**

In `tests/v3/test_fast_thorough.py`:

```python
"""Smoke tests for fast+thorough settings gate."""
from unittest.mock import patch
import pytest
from app.routers.v3.agent import _fast_thorough_enabled


def test_fast_thorough_enabled_defaults_true():
    with patch("app.routers.v3.agent.fetch_one", return_value=None):
        # No row in DB → default True
        assert _fast_thorough_enabled() is True


def test_fast_thorough_disabled_when_setting_false():
    with patch("app.routers.v3.agent.fetch_one", return_value={"value": "false"}):
        assert _fast_thorough_enabled() is False


def test_fast_thorough_enabled_when_setting_true():
    with patch("app.routers.v3.agent.fetch_one", return_value={"value": "true"}):
        assert _fast_thorough_enabled() is True


def test_fast_thorough_enabled_on_db_exception():
    with patch("app.routers.v3.agent.fetch_one", side_effect=Exception("DB down")):
        assert _fast_thorough_enabled() is True
```

- [ ] **Step B2.4: Run tests**

```bash
.venv/bin/python -m pytest tests/pipeline/fusion/test_merger.py tests/v3/test_fast_thorough.py -v 2>&1 | tail -15
```

- [ ] **Step B2.5: Commit**

```bash
git add app/routers/v3/agent.py app/routers/v3/db.py tests/v3/test_fast_thorough.py
git commit -m "feat(agent): fast+thorough parallel execution — asyncio.gather, WebSocket phase events, settings gate (4 tests)"
```

---

## Phase C — Frontend two-phase display

**Files:**
- Modify: `frontend/src/components/results/ResultsPanel.tsx`
- Modify: `frontend/src/hooks/useWebSocket.ts` (add new event handlers)

### Task C1: Handle new WebSocket events

- [ ] **Step C1.1: Check existing event handler structure**

```bash
grep -n "research\.\|job\.\|is\." frontend/src/hooks/useWebSocket.ts | head -25
```

- [ ] **Step C1.2: Add new event cases in useWebSocket.ts**

In the message handler switch/if block, add:

```typescript
case 'research.fast.completed': {
  const findings = (data.findings || []) as Finding[]
  // Store fast findings in store for phase display
  useChatStore.getState().setFastFindings(findings)
  useChatStore.getState().setFastResearchDone(true)
  break
}
case 'research.thorough.completed': {
  useChatStore.getState().setFastResearchDone(false) // thorough supersedes fast
  break
}
case 'research.fast.started':
  // Fast run begun — show spinner
  break
case 'research.thorough.started':
  // Both started — no UI change needed (already shown from fast.started)
  break
```

- [ ] **Step C1.3: Add state to chatStore**

In `frontend/src/stores/chatStore.ts`:
```typescript
fastFindings: Finding[]
fastResearchDone: boolean

setFastFindings: (findings: Finding[]) => void
setFastResearchDone: (done: boolean) => void
```

### Task C2: Update ResultsPanel for two-phase display

- [ ] **Step C2.1: Read current ResultsPanel finding rendering**

```bash
grep -n "finding\|findings\|phase\|confirmed\|badge" frontend/src/components/results/ResultsPanel.tsx | head -25
```

- [ ] **Step C2.2: Add phase badges and fast-results section**

Add to the finding row render:
```tsx
{/* Phase badge */}
{finding.phase === 'fast' && finding.confirmed_by_thorough && (
  <span style={{ fontSize: 9, color: '#4ade80', marginLeft: 6, fontWeight: 700 }}>✓ confirmed</span>
)}
{finding.phase === 'thorough' && (
  <span style={{ fontSize: 9, color: '#60a5fa', marginLeft: 6, fontWeight: 700 }}>NEW</span>
)}
```

When fast results are available but thorough is still running, show a progress indicator:
```tsx
{fastResearchDone && !thoroughResearchDone && (
  <div style={{ padding: '8px 12px', fontSize: 11, color: '#94a3b8',
                borderTop: '1px solid #1e293b', display: 'flex', alignItems: 'center', gap: 6 }}>
    <span>⏳</span> Thorough research in progress…
  </div>
)}
```

- [ ] **Step C2.3: Commit**

```bash
git add frontend/src/components/results/ResultsPanel.tsx \
        frontend/src/hooks/useWebSocket.ts \
        frontend/src/stores/chatStore.ts
git commit -m "feat(ui): two-phase ResultsPanel — fast/thorough phase indicators and confirmation badges"
```

---

## Phase D — Push and PR

- [ ] **Step D1: Run all tests**

```bash
.venv/bin/python -m pytest tests/pipeline/fusion/test_merger.py tests/v3/test_fast_thorough.py -v 2>&1 | tail -10
```

- [ ] **Step D2: Create PR**

```bash
export PATH="/opt/homebrew/bin:$PATH"
git checkout -b feat/fast-thorough-parallel 2>/dev/null || true
git push -u origin feat/fast-thorough-parallel
gh pr create --repo rinehardramos/info-broker \
  --title "feat(research): fast + thorough parallel research with merger and phase UI" \
  --body "Every IS query now spawns two parallel runs via asyncio.gather:

**Backend:**
- merger.py: URL equality + title word-overlap dedup, confirmed_by_thorough marking, phase tagging
- agent.py: parallel fast (depth=1, branches=5, no strategy) + thorough (full) via asyncio.gather
- WebSocket events: research.fast.started/completed, research.thorough.started/completed
- Settings gate: fast_thorough_mode in core_settings (default true)

**Frontend:**
- Fast results appear immediately with spinner while thorough runs
- confirmed / NEW badges added when thorough completes
- Graceful fallback when fast_thorough_mode=false (single run, current behavior)

**Tests:** 10 merger unit tests, 4 settings gate tests" \
  --base main
```

---

## Self-Review

**Spec coverage:**
- ✅ Fast run: max_depth=1, max_branches=5, no strategy/technique injection
- ✅ Thorough run: full params (unchanged from current behavior)
- ✅ merge_research_results: URL equality + normalized title overlap ≥70%, confirmed_by_thorough, phase fields
- ✅ WebSocket events for both phases
- ✅ Frontend: fast results + progress → thorough merge-in + badges
- ✅ Settings gate: fast_thorough_mode
- ✅ Only thorough run drives post-run hooks (merged result uses thorough as base)
- ✅ Fast run timeout: asyncio.create_task — if fast takes >30s it's still pending when thorough finishes; gather returns both. Add `asyncio.wait_for(fast_task, 30)` if hard timeout is needed.

**Placeholder check:** All code blocks are complete. Similarity threshold is concrete (0.7). All WebSocket event names spelled out.

**Type consistency:** `merge_research_results` returns `dict`; callers read `result.get("findings", [])` — same pattern as existing code.

**One caveat for implementer:** Both `fast_task` and `thorough_task` call `_on_tool_event` with the same `run_id`. Tool events from both runs will interleave in the WebSocket stream. This is acceptable (the frontend distinguishes phases by the `research.fast.completed` event, not by individual tool events).
