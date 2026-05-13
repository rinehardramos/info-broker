# Session-Aware Agent Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make agent chat session-aware — each message in a session carries the accumulated investigation context (genesis query + conversation thread + distilled findings), the IS brain's strategy evolves with the conversation, and a classifier decides between a full investigation run and a fast conversational reply.

**Architecture:** New `agent_sessions` DB table tracks session state server-side. The `send_message` endpoint creates/fetches a session, runs a Haiku classifier to decide mode, and either fires a full IS brain run (investigation) or returns a lightweight synthesised reply (conversational). Both modes update the session after completion. Session context is injected into the IS brain prompt via a new `session_context` field.

**Tech Stack:** Python/FastAPI (backend), PostgreSQL (persistence), Anthropic Haiku (classifier + conversational reply), React/TypeScript (frontend), Zustand (state management).

---

## File Map

**Create:**
- `app/routers/v3/sessions_api.py` — session CRUD endpoints (create, list, get, archive)
- `app/services/session_service.py` — session business logic (create, update, classify, conversational reply)
- `tests/test_session_service.py` — unit tests for session service
- `tests/test_sessions_api.py` — API endpoint tests

**Modify:**
- `app/routers/v3/db.py` — add `agent_sessions` table + `session_id` column on `pipeline_runs` to `_MIGRATIONS`
- `app/routers/v3/models.py` — update `AgentMessageIn`, `AgentMessageOut`; add `AgentSessionOut`
- `app/routers/v3/agent.py` — wire session into `send_message`; import sessions_api router
- `app/main.py` — register `sessions_api` router
- `app/is_brain.py` — add `session_context: str = ""` parameter to `run_research`
- `app/is_prompt.py` — add `{session_context}` slot to `RESEARCH_PROMPT` + update `build_prompt`
- `frontend/src/stores/chatStore.ts` — add `sessionId`, `genesisQuery` fields
- `frontend/src/api/v3.ts` — update `sendMessage`, add `archiveSession`, `listSessions`
- `frontend/src/components/agent/AgentChat.tsx` — pass `sessionId`, handle conversational reply, clear with archive, session indicator

---

## Task 1: DB Migration — `agent_sessions` table

**Files:**
- Modify: `app/routers/v3/db.py`

- [ ] **Step 1: Open `app/routers/v3/db.py` and find `_MIGRATIONS`**

  Look for the long string starting with `_MIGRATIONS = """` that contains all `CREATE TABLE IF NOT EXISTS` statements. Add these lines BEFORE the closing `"""`:

  ```sql
  CREATE TABLE IF NOT EXISTS agent_sessions (
      id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id              UUID NOT NULL,
      genesis_query        TEXT NOT NULL,
      status               VARCHAR DEFAULT 'active',
      created_at           TIMESTAMPTZ DEFAULT now(),
      archived_at          TIMESTAMPTZ,
      run_count            INT DEFAULT 0,
      turn_count           INT DEFAULT 0,
      conversation_thread  JSONB DEFAULT '[]',
      accumulated_summary  TEXT DEFAULT '',
      key_findings         JSONB DEFAULT '[]',
      entity_type          VARCHAR DEFAULT 'unknown'
  );
  CREATE INDEX IF NOT EXISTS agent_sessions_user_status_idx
      ON agent_sessions (user_id, status, created_at DESC);

  ALTER TABLE pipeline_runs
      ADD COLUMN IF NOT EXISTS session_id UUID REFERENCES agent_sessions(id);
  ```

- [ ] **Step 2: Verify migration runs cleanly**

  ```bash
  cd /Users/rinehardramos/Projects/info-broker
  POSTGRES_PORT=5433 .venv/bin/python -c "
  from app.routers.v3.db import run_migrations
  run_migrations()
  print('Migration OK')
  "
  ```

  Expected: `Migration OK` with no errors.

- [ ] **Step 3: Verify table exists**

  ```bash
  POSTGRES_PORT=5433 .venv/bin/python -c "
  from app.routers.v3.db import fetch_one
  row = fetch_one(\"SELECT column_name FROM information_schema.columns WHERE table_name = 'agent_sessions' ORDER BY ordinal_position\", ())
  print('Table exists, first column:', row)
  "
  ```

  Expected: `Table exists, first column: {'column_name': 'id'}`

- [ ] **Step 4: Commit**

  ```bash
  git add app/routers/v3/db.py
  git commit -m "feat(session): add agent_sessions table + session_id on pipeline_runs"
  ```

---

## Task 2: Backend Models

**Files:**
- Modify: `app/routers/v3/models.py`

- [ ] **Step 1: Write tests for model shapes**

  Create `tests/test_session_models.py`:

  ```python
  from app.routers.v3.models import AgentMessageIn, AgentMessageOut, AgentSessionOut
  import pytest

  def test_agent_message_in_accepts_session_id():
      msg = AgentMessageIn(message="hello", session_id="abc-123")
      assert msg.session_id == "abc-123"

  def test_agent_message_in_session_id_optional():
      msg = AgentMessageIn(message="hello")
      assert msg.session_id is None

  def test_agent_message_out_has_session_id():
      out = AgentMessageOut(job_id="j1", session_id="s1", status="pending", mode="investigation")
      assert out.session_id == "s1"
      assert out.mode == "investigation"
      assert out.reply is None

  def test_agent_message_out_conversational():
      out = AgentMessageOut(job_id=None, session_id="s1", status="done",
                            mode="conversational", reply="Here is what I found.")
      assert out.job_id is None
      assert out.reply == "Here is what I found."

  def test_agent_session_out():
      import datetime
      session = AgentSessionOut(
          id="s1", user_id="u1", genesis_query="what is MemGPT?",
          status="active", created_at=datetime.datetime.now(),
          run_count=2, turn_count=3, accumulated_summary="MemGPT is...",
          conversation_thread=[], key_findings=[], entity_type="concept"
      )
      assert session.genesis_query == "what is MemGPT?"
  ```

- [ ] **Step 2: Run tests — expect ImportError (models not yet updated)**

  ```bash
  .venv/bin/python -m pytest tests/test_session_models.py -v 2>&1 | head -20
  ```

  Expected: `ImportError` or `cannot import name 'AgentSessionOut'`

- [ ] **Step 3: Update `app/routers/v3/models.py`**

  Find `class AgentMessageIn(BaseModel):` and replace its body:

  ```python
  class AgentMessageIn(BaseModel):
      message: str
      session_id: str | None = None
      context_job_id: str | None = None
      use_intelligent_search: bool = False
      parent_run_id: str | None = None
  ```

  Find `class AgentMessageOut(BaseModel):` and replace its body:

  ```python
  class AgentMessageOut(BaseModel):
      job_id: str | None = None
      session_id: str = ""
      status: str = "pending"
      reply: str | None = None
      mode: str = "investigation"
  ```

  Add after `AgentMessageOut` (before the next class):

  ```python
  from datetime import datetime
  from typing import Any

  class AgentSessionOut(BaseModel):
      id: str
      user_id: str
      genesis_query: str
      status: str
      created_at: datetime
      archived_at: datetime | None = None
      run_count: int = 0
      turn_count: int = 0
      accumulated_summary: str = ""
      conversation_thread: list[dict[str, Any]] = []
      key_findings: list[dict[str, Any]] = []
      entity_type: str = "unknown"
  ```

- [ ] **Step 4: Run tests — expect PASS**

  ```bash
  .venv/bin/python -m pytest tests/test_session_models.py -v
  ```

  Expected: `5 passed`

- [ ] **Step 5: Commit**

  ```bash
  git add app/routers/v3/models.py tests/test_session_models.py
  git commit -m "feat(session): update AgentMessageIn/Out + add AgentSessionOut model"
  ```

---

## Task 3: Session Service

**Files:**
- Create: `app/services/session_service.py`
- Create: `tests/test_session_service.py`

- [ ] **Step 1: Write tests**

  Create `tests/test_session_service.py`:

  ```python
  import pytest
  from unittest.mock import patch, MagicMock
  from app.services.session_service import (
      classify_turn,
      build_session_context,
      distil_summary,
  )

  def test_classify_turn_investigation_no_session():
      # No session → always investigation
      result = classify_turn("find information about OpenAI", None, None)
      assert result == "investigation"

  def test_classify_turn_returns_valid_mode():
      thread = [{"role": "user", "content": "who is Wonyoung?"}]
      summary = "Wonyoung is an IVE member and Dyson ambassador."
      with patch("app.services.session_service._call_classifier") as mock:
          mock.return_value = "conversational"
          result = classify_turn("what brand does she represent?", thread, summary)
      assert result in ("investigation", "conversational")

  def test_build_session_context_no_session():
      ctx = build_session_context(None, "test query")
      assert ctx == ""

  def test_build_session_context_with_session():
      session = {
          "genesis_query": "who is Wonyoung?",
          "conversation_thread": [
              {"role": "user", "content": "who is Wonyoung?", "ts": "2026-01-01"},
              {"role": "agent", "content": "IVE member", "ts": "2026-01-01"},
          ],
          "accumulated_summary": "Wonyoung is an IVE member.",
          "key_findings": [{"title": "IVE member", "confidence": 90}],
          "turn_count": 2,
      }
      ctx = build_session_context(session, "what brand does she represent?")
      assert "who is Wonyoung?" in ctx
      assert "Wonyoung is an IVE member" in ctx
      assert "SESSION CONTEXT" in ctx

  def test_distil_summary_empty():
      result = distil_summary([], "")
      assert result == ""
  ```

- [ ] **Step 2: Run tests — expect ImportError**

  ```bash
  .venv/bin/python -m pytest tests/test_session_service.py -v 2>&1 | head -10
  ```

  Expected: `ImportError` — `app.services.session_service` does not exist yet.

- [ ] **Step 3: Create `app/services/__init__.py`** (empty if it doesn't exist)

  ```bash
  mkdir -p app/services && touch app/services/__init__.py
  ```

- [ ] **Step 4: Create `app/services/session_service.py`**

  ```python
  """Session service — manage investigation sessions for agent chat."""
  from __future__ import annotations

  import json
  import logging
  import os
  from datetime import datetime, timezone
  from typing import Any

  log = logging.getLogger(__name__)

  _CLASSIFIER_PROMPT = """\
  You are classifying a follow-up message in an ongoing investigation session.

  Session genesis query: {genesis_query}
  Conversation thread (last 5 turns):
  {thread_excerpt}
  Accumulated session summary: {summary}

  Latest user message: {message}

  Classify the latest message as ONE of:
  - "investigation": requires fetching new data the session does not yet have \
  (new entity, new angle, scope change, cannot be answered from existing findings)
  - "conversational": can be answered from existing session findings plus at most \
  one targeted tool call (narrowing, filtering, clarifying what was found)

  Respond with valid JSON only: {{"mode": "investigation"|"conversational", "reasoning": "brief reason"}}
  """


  def _call_classifier(
      message: str, genesis_query: str, thread: list[dict], summary: str
  ) -> str:
      """Call Haiku to classify the turn. Returns 'investigation' or 'conversational'."""
      try:
          import anthropic
          client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
          thread_excerpt = "\n".join(
              f"[{t.get('role','?')}]: {str(t.get('content',''))[:200]}"
              for t in (thread or [])[-5:]
          )
          prompt = _CLASSIFIER_PROMPT.format(
              genesis_query=genesis_query or message,
              thread_excerpt=thread_excerpt or "(none)",
              summary=summary[:500] if summary else "(none)",
              message=message,
          )
          response = client.messages.create(
              model="claude-haiku-4-5-20251001",
              max_tokens=100,
              messages=[{"role": "user", "content": prompt}],
          )
          text = response.content[0].text.strip()
          data = json.loads(text)
          mode = data.get("mode", "investigation")
          return mode if mode in ("investigation", "conversational") else "investigation"
      except Exception as exc:
          log.warning("Classifier failed (%s) — defaulting to investigation", exc)
          return "investigation"


  def classify_turn(
      message: str,
      conversation_thread: list[dict] | None,
      accumulated_summary: str | None,
      genesis_query: str = "",
  ) -> str:
      """Return 'investigation' or 'conversational' for this turn."""
      if not conversation_thread:
          return "investigation"
      return _call_classifier(
          message=message,
          genesis_query=genesis_query or message,
          thread=conversation_thread or [],
          summary=accumulated_summary or "",
      )


  def build_session_context(session: dict | None, current_message: str) -> str:
      """Build the session_context string for IS brain prompt injection."""
      if not session:
          return ""

      genesis = session.get("genesis_query", "")
      thread = session.get("conversation_thread") or []
      summary = session.get("accumulated_summary") or ""
      key_findings = session.get("key_findings") or []
      turn_count = session.get("turn_count", 0)

      # Format last 5 thread turns
      thread_lines = []
      for t in thread[-5:]:
          role = t.get("role", "?")
          content = str(t.get("content", ""))[:300]
          thread_lines.append(f"[{role}]: {content}")
      thread_excerpt = "\n".join(thread_lines) if thread_lines else "(no prior turns)"

      # Format top findings
      findings_lines = []
      for f in key_findings[:5]:
          title = f.get("title", "?")
          conf = f.get("confidence", "?")
          findings_lines.append(f"  - [{conf}%] {title}")
      findings_text = "\n".join(findings_lines) if findings_lines else "  (none yet)"

      return f"""## SESSION CONTEXT
  This is turn {turn_count + 1} of an ongoing investigation session.

  Genesis query (the original question anchoring this session):
    "{genesis}"

  Conversation thread (how the investigation has evolved):
  {thread_excerpt}

  What has been found so far:
  {summary or "(nothing yet)"}

  Key confirmed findings from prior turns:
  {findings_text}

  Current message (the latest refinement/direction):
    "{current_message}"

  INSTRUCTIONS: The current message evolves the session — it may widen, narrow,
  redirect, or add constraints to the genesis query. Your strategy, tactics, and
  investigation scope should reflect the FULL session intent, not just the latest
  message in isolation. Do not re-investigate what was already confirmed in prior
  turns. Build on what exists.
  """


  def distil_summary(findings: list[dict], current_summary: str) -> str:
      """Distil a compact running summary from findings. Returns empty string on failure."""
      if not findings:
          return current_summary or ""
      try:
          import anthropic
          client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
          findings_text = "\n".join(
              f"- [{f.get('confidence','?')}%] {f.get('title','?')}: {str(f.get('content',''))[:200]}"
              for f in findings[:20]
          )
          prompt = (
              f"Prior summary:\n{current_summary or '(none)'}\n\n"
              f"New findings:\n{findings_text}\n\n"
              "Write a compact (≤200 word) updated summary integrating the new findings with the prior summary. "
              "Preserve confirmed facts. Drop speculative or low-confidence items. Plain text only."
          )
          response = client.messages.create(
              model="claude-haiku-4-5-20251001",
              max_tokens=300,
              messages=[{"role": "user", "content": prompt}],
          )
          return response.content[0].text.strip()
      except Exception as exc:
          log.warning("distil_summary failed: %s", exc)
          return current_summary or ""


  def build_conversational_reply(
      message: str, session: dict, tool_result: str = ""
  ) -> str:
      """Build a conversational reply using session context + optional tool result."""
      try:
          import anthropic
          client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
          ctx = build_session_context(session, message)
          content = ctx
          if tool_result:
              content += f"\n\nAdditional data from targeted lookup:\n{tool_result[:2000]}"
          content += f"\n\nUser question: {message}\n\nProvide a concise, direct answer based on the session context above."
          response = client.messages.create(
              model="claude-haiku-4-5-20251001",
              max_tokens=500,
              messages=[{"role": "user", "content": content}],
          )
          return response.content[0].text.strip()
      except Exception as exc:
          log.warning("build_conversational_reply failed: %s", exc)
          return "I couldn't generate a reply from the session context. Please try again."


  def update_session_after_run(
      session_id: str,
      user_message: str,
      agent_summary: str,
      run_id: str | None,
      findings: list[dict],
      entity_type: str,
      is_investigation: bool,
  ) -> None:
      """Update session thread, summary, key_findings after a run completes."""
      try:
          from app.routers.v3.db import fetch_one, execute
          session = fetch_one(
              "SELECT * FROM agent_sessions WHERE id = %s", (session_id,)
          )
          if not session:
              return

          thread = list(session.get("conversation_thread") or [])
          now = datetime.now(timezone.utc).isoformat()
          thread.append({"role": "user", "content": user_message, "ts": now})
          thread.append({
              "role": "agent",
              "content": agent_summary[:500],
              "run_id": run_id,
              "ts": now,
          })

          # Update key_findings: merge + dedup by title, keep top-5 by confidence
          existing = list(session.get("key_findings") or [])
          all_findings = existing + (findings or [])
          seen_titles: set[str] = set()
          unique: list[dict] = []
          for f in sorted(all_findings, key=lambda x: x.get("confidence", 0), reverse=True):
              t = f.get("title", "")
              if t and t not in seen_titles:
                  seen_titles.add(t)
                  unique.append(f)
          key_findings = unique[:5]

          new_summary = distil_summary(findings, session.get("accumulated_summary") or "")

          execute(
              """UPDATE agent_sessions SET
                  conversation_thread = %s,
                  accumulated_summary = %s,
                  key_findings = %s,
                  entity_type = %s,
                  turn_count = turn_count + 1,
                  run_count = run_count + %s
              WHERE id = %s""",
              (
                  json.dumps(thread),
                  new_summary,
                  json.dumps(key_findings),
                  entity_type or "unknown",
                  1 if is_investigation else 0,
                  session_id,
              ),
          )
      except Exception as exc:
          log.warning("update_session_after_run failed: %s", exc)
  ```

- [ ] **Step 5: Run tests — expect PASS**

  ```bash
  .venv/bin/python -m pytest tests/test_session_service.py -v
  ```

  Expected: `5 passed`

- [ ] **Step 6: Commit**

  ```bash
  git add app/services/__init__.py app/services/session_service.py tests/test_session_service.py
  git commit -m "feat(session): add session service (classifier, context builder, distil, update)"
  ```

---

## Task 4: Session CRUD API

**Files:**
- Create: `app/routers/v3/sessions_api.py`
- Create: `tests/test_sessions_api.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write API tests**

  Create `tests/test_sessions_api.py`:

  ```python
  import pytest
  from fastapi.testclient import TestClient
  from unittest.mock import patch

  def test_sessions_router_registered(client):
      """Sessions endpoint exists (even if it returns 401 without auth)."""
      response = client.get("/v3/agent/sessions")
      assert response.status_code in (401, 403, 200)

  def test_archive_session_endpoint_exists(client):
      response = client.post("/v3/agent/sessions/nonexistent-id/archive")
      assert response.status_code in (401, 403, 404, 200)
  ```

  Note: These are smoke tests — full auth flow testing is manual.

- [ ] **Step 2: Create `app/routers/v3/sessions_api.py`**

  ```python
  """Agent session CRUD endpoints."""
  from __future__ import annotations

  import json
  import uuid
  from datetime import datetime, timezone

  from fastapi import APIRouter, Depends, HTTPException

  from app.routers.v3.auth import get_current_user
  from app.routers.v3.db import execute, fetch_all, fetch_one
  from app.routers.v3.models import AgentSessionOut

  router = APIRouter(prefix="/v3/agent/sessions", tags=["v3-sessions"])


  @router.post("", response_model=AgentSessionOut, status_code=201)
  def create_session(body: dict, user: dict = Depends(get_current_user)):
      """Create a new investigation session."""
      genesis_query = (body.get("genesis_query") or "").strip()
      if not genesis_query:
          raise HTTPException(status_code=422, detail="genesis_query required")
      session_id = str(uuid.uuid4())
      uid = str(user["id"])
      row = fetch_one(
          """INSERT INTO agent_sessions (id, user_id, genesis_query)
             VALUES (%s, %s, %s) RETURNING *""",
          (session_id, uid, genesis_query),
      )
      if not row:
          raise HTTPException(status_code=500, detail="Failed to create session")
      return _row_to_out(row)


  @router.get("", response_model=list[AgentSessionOut])
  def list_sessions(user: dict = Depends(get_current_user)):
      """List all sessions for the current user, newest first."""
      uid = str(user["id"])
      rows = fetch_all(
          "SELECT * FROM agent_sessions WHERE user_id = %s ORDER BY created_at DESC LIMIT 50",
          (uid,),
      )
      return [_row_to_out(r) for r in rows]


  @router.get("/{session_id}", response_model=AgentSessionOut)
  def get_session(session_id: str, user: dict = Depends(get_current_user)):
      """Get a single session with full conversation thread."""
      uid = str(user["id"])
      row = fetch_one(
          "SELECT * FROM agent_sessions WHERE id = %s AND user_id = %s",
          (session_id, uid),
      )
      if not row:
          raise HTTPException(status_code=404, detail="Session not found")
      return _row_to_out(row)


  @router.post("/{session_id}/archive")
  def archive_session(session_id: str, user: dict = Depends(get_current_user)):
      """Archive a session (triggered by chat clear)."""
      uid = str(user["id"])
      row = fetch_one(
          "SELECT id FROM agent_sessions WHERE id = %s AND user_id = %s",
          (session_id, uid),
      )
      if not row:
          raise HTTPException(status_code=404, detail="Session not found")
      execute(
          "UPDATE agent_sessions SET status = 'archived', archived_at = now() WHERE id = %s",
          (session_id,),
      )
      return {"status": "archived", "session_id": session_id}


  def _row_to_out(row: dict) -> AgentSessionOut:
      return AgentSessionOut(
          id=str(row["id"]),
          user_id=str(row["user_id"]),
          genesis_query=row["genesis_query"],
          status=row["status"],
          created_at=row["created_at"],
          archived_at=row.get("archived_at"),
          run_count=row.get("run_count", 0),
          turn_count=row.get("turn_count", 0),
          accumulated_summary=row.get("accumulated_summary") or "",
          conversation_thread=row.get("conversation_thread") or [],
          key_findings=row.get("key_findings") or [],
          entity_type=row.get("entity_type") or "unknown",
      )
  ```

- [ ] **Step 3: Register in `app/main.py`**

  Find the block of `include_router` calls. After:
  ```python
  from app.routers.v3.agent import router as v3_agent_router
  ```
  Add:
  ```python
  from app.routers.v3.sessions_api import router as v3_sessions_router
  ```

  After `app.include_router(v3_agent_router)`, add:
  ```python
  app.include_router(v3_sessions_router)
  ```

- [ ] **Step 4: Verify API starts cleanly**

  ```bash
  POSTGRES_PORT=5433 .venv/bin/python -c "
  from app.main import app
  routes = [r.path for r in app.routes if 'session' in r.path]
  print('Session routes:', routes)
  assert '/v3/agent/sessions' in routes
  assert '/v3/agent/sessions/{session_id}' in routes
  assert '/v3/agent/sessions/{session_id}/archive' in routes
  print('All routes registered OK')
  "
  ```

  Expected: `All routes registered OK`

- [ ] **Step 5: Commit**

  ```bash
  git add app/routers/v3/sessions_api.py app/main.py tests/test_sessions_api.py
  git commit -m "feat(session): add session CRUD endpoints + register router"
  ```

---

## Task 5: IS Brain Prompt Injection

**Files:**
- Modify: `app/is_prompt.py`
- Modify: `app/is_brain.py`

- [ ] **Step 1: Write test**

  Add to `tests/test_is_prompt.py` (create if it doesn't exist):

  ```python
  from app.is_brain import build_prompt

  def test_build_prompt_accepts_session_context():
      prompt = build_prompt(
          query="who is Wonyoung?",
          max_depth=3,
          max_branches=20,
          session_context="## SESSION CONTEXT\nGenesis: who is Wonyoung?\n",
      )
      assert "SESSION CONTEXT" in prompt
      assert "who is Wonyoung?" in prompt

  def test_build_prompt_empty_session_context():
      prompt = build_prompt(query="test", max_depth=2, max_branches=10)
      assert isinstance(prompt, str)
      assert len(prompt) > 100
  ```

- [ ] **Step 2: Run test — expect FAIL**

  ```bash
  .venv/bin/python -m pytest tests/test_is_prompt.py -v 2>&1 | head -20
  ```

  Expected: FAIL — `session_context` not yet a param.

- [ ] **Step 3: Add `{session_context}` slot to `RESEARCH_PROMPT` in `app/is_prompt.py`**

  Find this section in `RESEARCH_PROMPT` (after `{context_section}` and before `{research_plan}`):

  ```
  {context_section}

  {research_plan}
  ```

  Replace with:

  ```
  {context_section}

  {session_context}
  {research_plan}
  ```

- [ ] **Step 4: Add `session_context` to `build_prompt` in `app/is_prompt.py`**

  Find the `def build_prompt(` function signature. Add `session_context: str = ""` as a parameter after `user_sources: str = ""`.

  In the `return RESEARCH_PROMPT.format(...)` call, add:
  ```python
  session_context=_esc(session_context),
  ```

- [ ] **Step 5: Add `session_context` to `run_research` in `app/is_brain.py`**

  Find `async def run_research(` or `async def run_is_brain(`. Add `session_context: str = ""` parameter after `user_sources: str = ""`.

  Find the `build_prompt(` call inside the function. Add:
  ```python
  session_context=session_context,
  ```

- [ ] **Step 6: Run tests — expect PASS**

  ```bash
  .venv/bin/python -m pytest tests/test_is_prompt.py -v
  ```

  Expected: `2 passed`

- [ ] **Step 7: Commit**

  ```bash
  git add app/is_prompt.py app/is_brain.py tests/test_is_prompt.py
  git commit -m "feat(session): add session_context injection to IS brain prompt"
  ```

---

## Task 6: Wire Session into `send_message`

**Files:**
- Modify: `app/routers/v3/agent.py`

- [ ] **Step 1: Update imports in `app/routers/v3/agent.py`**

  At the top, after existing imports, add:

  ```python
  from app.services.session_service import (
      classify_turn,
      build_session_context,
      build_conversational_reply,
      update_session_after_run,
  )
  ```

- [ ] **Step 2: Update `AgentMessageOut` import**

  The existing import line:
  ```python
  from app.routers.v3.models import AgentMessageIn, AgentMessageOut, AgentPipelineOut
  ```
  is already correct — `AgentMessageOut` now has `session_id`, `reply`, `mode` fields.

- [ ] **Step 3: Add session creation helper (top of agent.py, before `send_message`)**

  After the `_get_active_pipeline` function, add:

  ```python
  def _create_or_fetch_session(session_id: str | None, user_id: str, message: str) -> tuple[str, dict | None]:
      """Return (session_id, session_row). Creates session if session_id is None."""
      if not session_id:
          row = fetch_one(
              """INSERT INTO agent_sessions (id, user_id, genesis_query)
                 VALUES (%s, %s, %s) RETURNING *""",
              (str(uuid.uuid4()), user_id, message),
          )
          return str(row["id"]), dict(row) if row else None
      row = fetch_one(
          "SELECT * FROM agent_sessions WHERE id = %s AND user_id = %s",
          (session_id, user_id),
      )
      return session_id, dict(row) if row else None
  ```

- [ ] **Step 4: Modify the `send_message` endpoint for IS brain path**

  Find the `if body.use_intelligent_search:` block. At the start of that block, add session creation + classifier:

  ```python
  if body.use_intelligent_search:
      # --- Session handling ---
      sid, session_row = _create_or_fetch_session(body.session_id, uid, body.message)

      # Classifier decides mode (first message always = investigation)
      thread = (session_row or {}).get("conversation_thread") or []
      summary = (session_row or {}).get("accumulated_summary") or ""
      genesis = (session_row or {}).get("genesis_query") or body.message
      mode = classify_turn(body.message, thread, summary, genesis) if thread else "investigation"

      # --- Conversational reply path ---
      if mode == "conversational" and session_row:
          reply_text = build_conversational_reply(body.message, session_row)
          # Update session async (don't block reply)
          import asyncio
          asyncio.create_task(_update_session_conversational(
              sid, body.message, reply_text, uid
          ))
          return AgentMessageOut(
              job_id=None,
              session_id=sid,
              status="done",
              reply=reply_text,
              mode="conversational",
          )

      # --- Full investigation path (existing logic, extended) ---
      # Build session context for IS brain
      session_context = build_session_context(session_row, body.message)
  ```

  Then find where `_run_is_research` is called and add `session_context` + `session_id`:

  ```python
  task = asyncio.create_task(
      _run_is_research(
          run_id, uid, pipeline_id, body.message,
          past_research=past_research,
          session_id=sid,
          session_context=session_context,
      )
  )
  ```

  Update the `return AgentMessageOut(...)` at the end of the IS branch:
  ```python
  return AgentMessageOut(job_id=run_id, session_id=sid, status="pending", mode="investigation")
  ```

- [ ] **Step 5: Add `_update_session_conversational` helper**

  After `_create_or_fetch_session`, add:

  ```python
  async def _update_session_conversational(
      session_id: str, user_message: str, reply: str, uid: str
  ) -> None:
      """Lightweight session update for conversational replies."""
      import asyncio
      loop = asyncio.get_event_loop()
      await loop.run_in_executor(
          None,
          update_session_after_run,
          session_id, user_message, reply, None, [], "conversational", False,
      )
  ```

- [ ] **Step 6: Update `_run_is_research` signature**

  Find `async def _run_is_research(` and add parameters:

  ```python
  async def _run_is_research(
      run_id: str, uid: str, pipeline_id: str, query: str,
      past_research: list[dict] | None = None,
      session_id: str | None = None,
      session_context: str = "",
  ) -> None:
  ```

  Inside `_run_is_research`, find the `run_research(` call and add:
  ```python
  session_context=session_context,
  ```

  After the `run_research(` call completes and `result` is available, add session update:
  ```python
  # Update session after run
  if session_id:
      try:
          findings = result.get("findings") or []
          summary = result.get("summary") or ""
          entity_type = result.get("entity_type") or "unknown"
          update_session_after_run(
              session_id=session_id,
              user_message=query,
              agent_summary=summary,
              run_id=run_id,
              findings=findings,
              entity_type=entity_type,
              is_investigation=True,
          )
          # Update pipeline_run with session_id
          execute(
              "UPDATE pipeline_runs SET session_id = %s WHERE id = %s",
              (session_id, run_id),
          )
      except Exception as exc:
          log.warning("Session update after run failed: %s", exc)
  ```

- [ ] **Step 7: Verify import and syntax**

  ```bash
  .venv/bin/python -c "
  from app.routers.v3.agent import router
  print('Agent router OK, routes:', len(router.routes))
  "
  ```

  Expected: `Agent router OK, routes: N` (no import errors)

- [ ] **Step 8: Commit**

  ```bash
  git add app/routers/v3/agent.py
  git commit -m "feat(session): wire session into send_message — classifier + conversational reply + session update"
  ```

---

## Task 7: Frontend — `chatStore.ts`

**Files:**
- Modify: `frontend/src/stores/chatStore.ts`

- [ ] **Step 1: Update `chatStore.ts`**

  Replace the entire file content:

  ```typescript
  import { create } from 'zustand'
  import { persist, createJSONStorage } from 'zustand/middleware'

  export interface Message {
    id: string
    role: 'user' | 'assistant' | 'agent'
    content: string
    status?: 'pending' | 'running' | 'done' | 'error'
    type?: 'message' | 'question' | 'plan'
    payload?: Record<string, unknown>
  }

  interface ChatState {
    messages: Message[]
    sessionId: string | null
    genesisQuery: string | null
    addMessage: (msg: Message) => void
    updateMessage: (id: string, patch: Partial<Message>) => void
    setMessages: (msgs: Message[]) => void
    setSessionId: (id: string) => void
    setGenesisQuery: (q: string) => void
    clearMessages: () => void
  }

  export const useChatStore = create<ChatState>()(
    persist(
      (set) => ({
        messages: [],
        sessionId: null,
        genesisQuery: null,
        addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
        updateMessage: (id, patch) =>
          set((s) => ({
            messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)),
          })),
        setMessages: (messages) => set({ messages }),
        setSessionId: (id) => set({ sessionId: id }),
        setGenesisQuery: (q) => set({ genesisQuery: q }),
        clearMessages: () => set({ messages: [], sessionId: null, genesisQuery: null }),
      }),
      {
        name: 'ib-chat',
        storage: createJSONStorage(() => localStorage),  // changed from sessionStorage → localStorage
      },
    ),
  )
  ```

- [ ] **Step 2: Verify TypeScript**

  ```bash
  cd /Users/rinehardramos/Projects/info-broker/frontend && npx tsc --noEmit 2>&1 | grep chatStore
  ```

  Expected: no errors mentioning `chatStore`.

- [ ] **Step 3: Commit**

  ```bash
  git add frontend/src/stores/chatStore.ts
  git commit -m "feat(session): add sessionId + genesisQuery to chatStore, use localStorage"
  ```

---

## Task 8: Frontend — `v3.ts` API

**Files:**
- Modify: `frontend/src/api/v3.ts`

- [ ] **Step 1: Update `sendMessage` and add session API functions**

  Find `export const sendMessage =` and replace it:

  ```typescript
  export const sendMessage = (
    message: string,
    sessionId?: string | null,
    useIntelligentSearch?: boolean,
    parentRunId?: string,
  ) =>
    api.post<AgentMessageOut>('/v3/agent/message', {
      message,
      session_id: sessionId ?? undefined,
      use_intelligent_search: useIntelligentSearch,
      parent_run_id: parentRunId,
    }).then(r => r.data)
  ```

  Add the `AgentMessageOut` interface near the top of the file (with other interfaces):

  ```typescript
  export interface AgentMessageOut {
    job_id: string | null
    session_id: string
    status: string
    reply: string | null
    mode: 'investigation' | 'conversational'
  }

  export interface AgentSession {
    id: string
    genesis_query: string
    status: 'active' | 'archived'
    created_at: string
    turn_count: number
    run_count: number
    accumulated_summary: string
    entity_type: string
  }
  ```

  Add after `sendMessage`:

  ```typescript
  export const archiveSession = (sessionId: string): Promise<void> =>
    api.post(`/v3/agent/sessions/${sessionId}/archive`).then(() => undefined)

  export const listSessions = (): Promise<AgentSession[]> =>
    api.get('/v3/agent/sessions').then(r => r.data)
  ```

- [ ] **Step 2: Verify TypeScript**

  ```bash
  cd /Users/rinehardramos/Projects/info-broker/frontend && npx tsc --noEmit 2>&1 | grep "v3.ts"
  ```

  Expected: no errors.

- [ ] **Step 3: Commit**

  ```bash
  git add frontend/src/api/v3.ts
  git commit -m "feat(session): update sendMessage API + add archiveSession/listSessions"
  ```

---

## Task 9: Frontend — `AgentChat.tsx`

**Files:**
- Modify: `frontend/src/components/agent/AgentChat.tsx`

- [ ] **Step 1: Update imports**

  Find the import line for `sendMessage` and update:

  ```typescript
  import { sendMessage, getAgentPipeline, getBrainStatus, archiveSession } from '../../api/v3'
  import type { AgentMessageOut } from '../../api/v3'
  ```

  Find the chatStore imports and update:

  ```typescript
  const chatMessages = useChatStore(s => s.messages)
  const clearMessages = useChatStore(s => s.clearMessages)
  const sessionId = useChatStore(s => s.sessionId)
  const setSessionId = useChatStore(s => s.setSessionId)
  const setGenesisQuery = useChatStore(s => s.setGenesisQuery)
  const setChatMessages = useChatStore(s => s.setMessages)
  ```

- [ ] **Step 2: Update `handleSend` to pass `sessionId` and handle conversational reply**

  Find the `async function handleSend()` function and replace it:

  ```typescript
  async function handleSend() {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setSending(true)
    setAgentInput(text)

    const userMsg: Message = { id: `user-${++_msgCounter}`, role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])

    try {
      const result: AgentMessageOut = await sendMessage(
        text,
        sessionId ?? undefined,
        useIntelligentSearch,
      )

      // Store session_id from first response
      if (result.session_id) {
        setSessionId(result.session_id)
        if (!sessionId) setGenesisQuery(text)  // first message = genesis
      }

      if (result.mode === 'conversational' && result.reply) {
        // Conversational reply — render directly, no spinner, no ResultsPanel tab
        setMessages(prev => [
          ...prev,
          { id: `agent-${++_msgCounter}`, role: 'agent', content: result.reply! },
        ])
      } else {
        // Investigation — existing async flow
        setMessages(prev => [
          ...prev,
          { id: result.job_id!, role: 'agent', content: `Researching…`, status: 'pending' },
        ])
        setActiveJobId(result.job_id!)
        const { setCol1Content } = useSessionStore.getState()
        setCol1Content({ type: 'pipeline_run', runId: result.job_id! })
      }
    } catch {
      setMessages(prev => [
        ...prev,
        { id: `err-${++_msgCounter}`, role: 'agent', content: 'Failed to start research. Check your connection.' },
      ])
    } finally {
      setSending(false)
    }
  }
  ```

- [ ] **Step 3: Update clear button to archive session first**

  Find the Clear button's `onClick` handler:
  ```typescript
  onClick={clearMessages}
  ```

  Replace with:
  ```typescript
  onClick={async () => {
    if (sessionId) {
      try { await archiveSession(sessionId) } catch { /* non-fatal */ }
    }
    clearMessages()
  }}
  ```

- [ ] **Step 4: Add session indicator to header**

  Find the header `<span>Agent</span>` and replace with:

  ```typescript
  <span>Agent</span>
  {sessionId && (
    <span style={{
      fontSize: 8, color: 'var(--muted)', fontWeight: 400,
      padding: '1px 5px', borderRadius: 3,
      border: '1px solid var(--border)', marginLeft: 4,
    }}>
      Session active
    </span>
  )}
  ```

- [ ] **Step 5: TypeScript check**

  ```bash
  cd /Users/rinehardramos/Projects/info-broker/frontend && npx tsc --noEmit 2>&1 | grep "AgentChat"
  ```

  Expected: no new errors in AgentChat.tsx.

- [ ] **Step 6: Commit**

  ```bash
  git add frontend/src/components/agent/AgentChat.tsx
  git commit -m "feat(session): wire sessionId into AgentChat — conversational reply, archive on clear, session indicator"
  ```

---

## Task 10: Deploy to Docker and Smoke Test

- [ ] **Step 1: Deploy all changed files**

  ```bash
  export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
  docker compose build info-broker-api && docker compose restart info-broker-api
  ```

  If build is slow, copy directly:
  ```bash
  docker cp app/routers/v3/db.py info-broker-info-broker-api-1:/app/app/routers/v3/db.py
  docker cp app/routers/v3/agent.py info-broker-info-broker-api-1:/app/app/routers/v3/agent.py
  docker cp app/routers/v3/sessions_api.py info-broker-info-broker-api-1:/app/app/routers/v3/sessions_api.py
  docker cp app/routers/v3/models.py info-broker-info-broker-api-1:/app/app/routers/v3/models.py
  docker cp app/services/session_service.py info-broker-info-broker-api-1:/app/app/services/session_service.py
  docker cp app/services/__init__.py info-broker-info-broker-api-1:/app/app/services/__init__.py
  docker cp app/is_prompt.py info-broker-info-broker-api-1:/app/app/is_prompt.py
  docker cp app/is_brain.py info-broker-info-broker-api-1:/app/app/is_brain.py
  docker cp app/main.py info-broker-info-broker-api-1:/app/app/main.py
  docker restart info-broker-info-broker-api-1
  ```

- [ ] **Step 2: Verify migration ran**

  ```bash
  sleep 8 && docker exec info-broker-info-broker-api-1 python3 -c "
  import sys; sys.path.insert(0, '/app')
  from app.routers.v3.db import fetch_one
  r = fetch_one(\"SELECT COUNT(*) as c FROM information_schema.tables WHERE table_name = 'agent_sessions'\", ())
  print('agent_sessions table exists:', r['c'] == 1)
  "
  ```

  Expected: `agent_sessions table exists: True`

- [ ] **Step 3: Verify session routes registered**

  ```bash
  docker exec info-broker-info-broker-api-1 python3 -c "
  import sys; sys.path.insert(0, '/app')
  from app.main import app
  routes = [r.path for r in app.routes if 'session' in r.path]
  print('Session routes:', routes)
  assert len(routes) >= 3
  print('OK')
  "
  ```

- [ ] **Step 4: Open Chrome and run a 2-turn test**

  ```bash
  open http://localhost:5173
  ```

  Test sequence:
  1. Send: *"Who is Jang Wonyoung?"* → wait for research to complete
  2. Send follow-up: *"What brands does she represent?"* → should see "Session active" in header; brain should NOT restart from zero; conversational or contextual investigation
  3. Clear chat → should see session archived, new session next message

- [ ] **Step 5: Final commit**

  ```bash
  git add -A
  git commit -m "feat(session): complete session-aware agent chat — Option B implementation"
  ```
