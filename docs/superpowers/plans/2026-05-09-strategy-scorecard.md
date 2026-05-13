# Strategy Scorecard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:[REDACTED:high-entropy-base64:27ch:hash=88f76bb3] (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add three-level A-F grading (strategy/tactic/technique) to research results with inline UI and feedback loop into the self-learning overlay system.

**Architecture:** Backend scorecard engine decomposes research trails into a graded strategy tree, persisted as JSONB. Frontend renders a collapsible Investigation Breakdown section. User grade overrides feed directly into the existing strategy overlay system.

**Tech Stack:** Python 3.11, React/TypeScript, pytest, Playwright

---

## Tasks

### Task 1: Scorecard engine (backend)
- Create: `app/pipeline/fusion/scorecard.py`
- Test: `tests/pipeline/fusion/test_scorecard.py`
- Functions: build_scorecard, auto_grade_technique, auto_grade_tactic, auto_grade_strategy
- TDD: test grading logic for each level

### Task 2: DB schema + wire into post-run
- Modify: `app/routers/v3/db.py` — add scorecard column
- Modify: `app/routers/v3/agent.py` — wire build_scorecard into post-run
- Modify: `app/routers/v3/research_api.py` — add GET/POST scorecard endpoints

### Task 3: Grade feedback → overlay update
- Modify: `app/routers/v3/research_api.py` — POST grade triggers overlay upsert
- Test: verify grade A → reinforce, grade F → prune

### Task 4: Frontend InvestigationBreakdown component
- Create: `frontend/src/components/results/InvestigationBreakdown.tsx`
- Create: `frontend/src/components/results/GradeBadge.tsx`
- Modify: `frontend/src/components/results/ResultsPanel.tsx`
- Modify: `frontend/src/api/v3.ts` — add scorecard API calls

### Task 5: Integration test
- E2E: scorecard built → displayed → graded → overlay updated
