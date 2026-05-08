# Universal Research Engine Phase A: Intelligent Research Planning

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:[REDACTED:high-entropy-base64:27ch:hash=88f76bb3] (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a two-phase IS brain that classifies query complexity, asks clarifying questions for complex queries, builds multi-step research plans, and verifies sources post-run.

**Architecture:** Scale classifier scores queries as simple/complex. Complex queries trigger a clarification phase via ask_user MCP tool, then a structured research plan with cross-category execution. A verifier pass checks source quality after completion. All Q&A and plans are persisted.

**Tech Stack:** Python (asyncio), PostgreSQL (schema changes), FastAPI (new endpoints), MCP (ask_user tool), React (chat rendering)

---

### Task 1: Database Schema -- plan + clarification columns

**Files:** Modify `app/routers/v3/db.py`

- [ ] Add ALTER TABLE statements after the research_trails CREATE TABLE block. Add columns: `plan JSONB`, `clarification JSONB DEFAULT '[]'`, `verification_status VARCHAR(32)`. Follow the existing ALTER TABLE pattern in the file (search for other ALTER TABLE statements).
- [ ] Rebuild API container, verify columns exist
- [ ] Commit: `git add app/routers/v3/db.py && git commit -m "schema: add plan, clarification, verification_status to research_trails"`

---

### Task 2: Scale Classifier (TDD)

**Files:**
- Modify: `app/pipeline/strategies/orchestrator.py`
- Create: `tests/pipeline/strategies/test_orchestrator_complexity.py`

- [ ] Write failing tests. Key assertions:
  - `classify_complexity("find email of John Doe")` returns `("simple", score <= 0)`
  - `classify_complexity("what is Acme Corp?")` returns `("simple", score <= 0)`
  - `classify_complexity("investigate TechCorp")` returns `("complex", score > 0)`
  - `classify_complexity("compare AWS vs Azure vs GCP")` returns `("complex", score > 0)`
  - `classify_complexity("why did revenue drop?")` returns `("complex", score > 0)`
  - `classify_complexity("find their team and analyze financials")` returns `("complex", score > 0)`
  - `classify_complexity("predict what happens if they merge")` returns `("complex", score > 0)`
  - Long query (> 50 words) returns complex
  - Edge case: empty string returns simple
- [ ] Run tests -- verify FAIL
- [ ] Implement `classify_complexity(query: str) -> tuple[str, int]` in orchestrator.py after the existing classify_query function. Use signal-word scoring: simple lookup verbs (-1), single entity (-2), open-ended verbs (+2), multi-entity/comparison (+2), multi-domain (+3), causal (+1), predictive (+1), long query (+1). Return ("simple", score) if score <= 0, ("complex", score) if score > 0.
- [ ] Run tests -- verify PASS
- [ ] Commit: `git add app/pipeline/strategies/orchestrator.py tests/pipeline/strategies/test_orchestrator_complexity.py && git commit -m "feat(engine): add scale classifier for query complexity scoring"`

---

### Task 3: ask_user Answer Queue (backend)

**Files:**
- Create: `app/routers/v3/brain_questions.py`

- [ ] Create a module that manages the ask/answer loop for brain questions. It needs:
  - `_pending_questions: dict[str, asyncio.Event]` -- keyed by run_id
  - `_pending_answers: dict[str, str]` -- keyed by run_id
  - `async def wait_for_answer(run_id: str, question: str, options: list[str], uid: str) -> str` -- pushes WS event `brain.question`, creates asyncio.Event, waits for it (timeout 300s), returns the answer
  - `def submit_answer(run_id: str, answer: str) -> bool` -- stores answer, sets the event, returns True if run_id was waiting
  - Two API endpoints on a router (prefix="/v3/agent"):
    - `POST /brain-question` -- called by MCP ask_user tool. Body: `{run_id, question, options, uid}`. Calls wait_for_answer, returns `{"answer": "..."}`.
    - `POST /brain-answer` -- called by frontend. Body: `{run_id, answer}`. Calls submit_answer, returns `{"status": "ok"}`.
  - Import `push_event` from `app.routers.v3.stream`
- [ ] Commit: `git add app/routers/v3/brain_questions.py && git commit -m "feat(engine): add brain question/answer queue with asyncio.Event"`

---

### Task 4: ask_user MCP Tool

**Files:**
- Modify: `mcp_server/server.py`

- [ ] Add `ask_user` tool after existing tools. It calls `api_call("POST", "/v3/agent/brain-question", json={"run_id": run_id, "question": question, "options": options, "uid": uid})`. The tool needs run_id and uid as params (passed from the IS brain context). Returns the user's answer as a string.
  - Note: The IS brain passes run_id via MCP session context. For now, accept run_id as an explicit param.
  - Signature: `async def ask_user(question: str, run_id: str, options: list[str] = []) -> str`
- [ ] Commit: `git add mcp_server/server.py && git commit -m "feat(engine): add ask_user MCP tool for brain clarification"`

---

### Task 5: Research Planner (TDD)

**Files:**
- Create: `app/pipeline/strategies/planner.py`
- Create: `tests/pipeline/strategies/test_planner.py`

- [ ] Write failing tests. Key assertions:
  - `format_plan_for_prompt(plan_dict)` returns a formatted string with step numbers, categories, goals, tools, and completeness criteria
  - `format_plan_for_prompt(None)` returns empty string
  - `format_plan_for_prompt({"steps": []})` returns empty string
  - Format includes "Step 1 [retrieval]:" style lines
  - Format includes "Completeness criteria:" section
- [ ] Run tests -- verify FAIL
- [ ] Implement `format_plan_for_prompt(plan: dict | None) -> str` in planner.py. Takes a plan dict (as generated by the IS brain) and formats it into a prompt section. Also add `format_clarification_for_prompt(clarification: list[dict]) -> str` to render Q&A history.
- [ ] Run tests -- verify PASS
- [ ] Commit: `git add app/pipeline/strategies/planner.py tests/pipeline/strategies/test_planner.py && git commit -m "feat(engine): add research plan formatter for IS brain prompt"`

---

### Task 6: Verifier (TDD)

**Files:**
- Create: `app/pipeline/strategies/verifier.py`
- Create: `tests/pipeline/strategies/test_verifier.py`

- [ ] Write failing tests. Key assertions:
  - `verify_findings([])` returns `{"status": "PASS", "issues": []}`
  - Finding with confidence > 70 but low Admiralty source gets flagged
  - Finding with unreachable URL gets flagged (mock httpx)
  - Multiple issues returns "PASS_WITH_NOTES"
  - verify_findings returns correct issue count
- [ ] Run tests -- verify FAIL
- [ ] Implement `verify_findings(findings: list[dict]) -> dict` in verifier.py. Checks:
  1. Confidence alignment: findings with source in F-rated tools should not exceed confidence 70
  2. Source quality: flag findings with no URL or empty content
  Returns `{"status": "PASS"|"PASS_WITH_NOTES"|"BLOCKED", "issues": [{"type": "...", "finding_index": N, "message": "..."}]}`
  Note: HTTP reachability checking is deferred to avoid network calls in the background loop. Phase A only does rule-based checks.
- [ ] Run tests -- verify PASS
- [ ] Commit: `git add app/pipeline/strategies/verifier.py tests/pipeline/strategies/test_verifier.py && git commit -m "feat(engine): add rule-based finding verifier"`

---

### Task 7: Wire Into IS Brain -- Prompt + Execution

**Files:**
- Modify: `app/is_prompt.py`
- Modify: `app/is_brain.py`
- Modify: `app/routers/v3/agent.py`

- [ ] In `app/is_prompt.py`: Add `{research_plan}` placeholder after `{context_section}` and before `## AVAILABLE MCP TOOLS`. Add a CLARIFICATION section to the prompt instructing the brain to use ask_user for complex queries (max 3 questions, provide options).
- [ ] In `app/is_brain.py`: Add `research_plan=""` param to `run_research()` and pass it to `build_prompt()`.
- [ ] In `app/routers/v3/agent.py`:
  - Import `classify_complexity` from orchestrator
  - Before calling `_run_is_research`, check complexity. If complex, pass `is_complex=True` to the function.
  - In `_run_is_research`: after the brain completes, parse the result for a `plan` field. Store plan + clarification in research_trails columns.
  - After findings are collected, call `verify_findings()` and store verification_status.
  - Push `brain.plan` WS event when plan is detected in brain output.
- [ ] Register the brain_questions router in `app/main.py`
- [ ] Commit: `git add app/is_prompt.py app/is_brain.py app/routers/v3/agent.py app/main.py && git commit -m "feat(engine): wire plan-aware execution into IS brain + agent endpoint"`

---

### Task 8: Frontend -- Brain Questions + Plan Display

**Files:**
- Modify: `frontend/src/components/agent/AgentChat.tsx`

- [ ] In the WS event handler, add branches for `brain.question` and `brain.plan` event types
- [ ] For `brain.question`: add a message with `type: 'question'` to the messages array. Include `options` from the event payload.
- [ ] Render question messages with a distinct style (e.g., blue background, question mark icon). If options exist, render as clickable pill buttons.
- [ ] When user clicks an option or types a reply to a question, POST to `/v3/agent/brain-answer` with `{run_id, answer}`.
- [ ] For `brain.plan`: add a message with `type: 'plan'` to messages. Render as a collapsible card showing category sequence, steps with goals, and completeness criteria.
- [ ] For verification badge: when `job.completed` event includes `verification_status`, show a colored badge (green PASS / yellow NOTES / red BLOCKED).
- [ ] Commit: `git add frontend/src/components/agent/AgentChat.tsx && git commit -m "feat(fe): render brain questions, research plans, and verification badges in chat"`

---

### Task 9: Integration Test + Docker Deploy

- [ ] Run all unit tests: `uv run pytest tests/ -q --tb=short --ignore=tests/v3 --ignore=tests/e2e`
  Expected: 688+ existing + ~25 new, all pass
- [ ] Docker build and deploy: `docker compose build info-broker-api && docker compose up -d`
- [ ] Verify new columns exist in DB
- [ ] Test simple query via API -- should execute immediately (current behavior)
- [ ] Test complex query via API -- should trigger brain.question WS event
- [ ] Frontend build check: `cd frontend && npm run build`
- [ ] Push: `git push origin main`
