# Session-Aware Agent Chat — Design Spec

**Date**: 2026-05-10  
**Status**: Approved  
**Author**: Claude + Rinehard

---

## Problem

Every `sendMessage` call is currently stateless. Each IS brain run is independent — the brain has no knowledge of prior turns in the same conversation. The only exception is the single-parent `parent_run_id` ("Go Deeper"), which feeds exactly one prior run's findings. This means:

- Follow-up messages restart investigation from scratch, wasting budget re-confirming what was already found
- The brain's strategy and tactics don't adapt to what the user has added across the conversation
- There is no "session" — each message is an island

---

## Solution: Session-Aware Option B

A persistent server-side session that tracks the full investigation thread. Each new message in a session carries the accumulated context (genesis query + conversation thread + distilled findings). The IS brain's strategy, tactics, and scope evolve with the conversation. A lightweight classifier decides whether a follow-up requires a new full investigation or a faster conversational reply.

---

## Section 1: Data Model

### New table: `agent_sessions`

```sql
CREATE TABLE agent_sessions (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES users(id),
    genesis_query        TEXT NOT NULL,
    status               VARCHAR DEFAULT 'active',  -- active | archived
    created_at           TIMESTAMPTZ DEFAULT now(),
    archived_at          TIMESTAMPTZ,
    run_count            INT DEFAULT 0,
    turn_count           INT DEFAULT 0,
    conversation_thread  JSONB DEFAULT '[]',   -- [{role, content, run_id, ts}]
    accumulated_summary  TEXT DEFAULT '',
    key_findings         JSONB DEFAULT '[]'    -- top-5 across all session runs
);
```

### Schema changes to existing tables

- `pipeline_runs`: add `session_id UUID REFERENCES agent_sessions(id)`
- `AgentMessageIn`: add `session_id: str | None = None`
- `AgentMessageOut`: add `session_id: str`, `reply: str | None`, `mode: str`

### Session state fields

| Field | Description |
|---|---|
| `genesis_query` | First user message — the anchor for the entire session |
| `conversation_thread` | Ordered list of `{role, content, run_id?, ts}` entries for every turn |
| `accumulated_summary` | Haiku-distilled running summary of all findings so far; refreshed after each run |
| `key_findings` | Top-5 highest-confidence, deduplicated findings across all session runs |
| `run_count` | Full IS brain runs triggered in this session |
| `turn_count` | Total turns (includes conversational replies) |

---

## Section 2: Session Lifecycle + Conversation Classifier

### Session creation and flow

```
sendMessage(message, session_id?)
  │
  ├── No session_id → CREATE SESSION (genesis_query = message)
  │                   → always full IS brain run (genesis = first anchor)
  │
  └── Has session_id → FETCH SESSION (thread + summary + key_findings)
                       → RUN CLASSIFIER
                          │
                          ├── "investigation" → full IS brain run
                          └── "conversational" → light reply path
```

### Classifier

A fast Haiku call (~1s) with a tight prompt:

```
Session genesis: {genesis_query}
Thread (last 5 turns): [{...}]
Latest message: {message}

Classify as ONE of:
- "investigation": requires new data the session doesn't yet have
- "conversational": answerable from existing session findings + optional single tool

Respond: {"mode": "investigation"|"conversational", "reasoning": "..."}
```

**Investigation signals:** new entity, new angle, explicit "find/research/investigate", scope change the existing findings can't answer.  
**Conversational signals:** narrows/filters existing findings, clarifies what was found, simple factual follow-up.

### After every run (both modes)

1. Append `{role: "user", content, ts}` + `{role: "agent", content: summary, run_id, ts}` to `conversation_thread`
2. Refresh `accumulated_summary` via Haiku distillation of all findings
3. Update `key_findings` (top-5 by confidence, deduplicated across runs)
4. Increment `turn_count` (and `run_count` for investigation mode)
5. Update `entity_type` on session if it changed

### Clear = archive + new session

- Clearing the chat panel calls `POST /v3/agent/sessions/{id}/archive`
- Session `status` → `"archived"`, `archived_at` set
- Frontend clears `sessionId` — next message auto-creates a new session
- Archived sessions are browsable in history

---

## Section 3: API Changes

### New endpoints

```
POST   /v3/agent/sessions              → create session (genesis_query)
GET    /v3/agent/sessions              → list user's sessions (history)
GET    /v3/agent/sessions/{id}         → get session + full thread
POST   /v3/agent/sessions/{id}/archive → archive session
```

### Modified `POST /v3/agent/message`

**`AgentMessageIn`:**
```python
class AgentMessageIn(BaseModel):
    message: str
    session_id: str | None = None        # links to session
    context_job_id: str | None = None
    use_intelligent_search: bool = False
    parent_run_id: str | None = None
```

**`AgentMessageOut`:**
```python
class AgentMessageOut(BaseModel):
    job_id: str | None = None            # null for conversational replies
    session_id: str                      # always returned
    status: str = "pending"
    reply: str | None = None             # populated for conversational replies
    mode: str = "investigation"          # "investigation" | "conversational"
```

### Conversational reply handler (internal)

1. Build context: `accumulated_summary` + `key_findings` + last 5 thread turns
2. Optionally call ONE fast tool if classifier flags it (`run_web_search` with targeted query)
3. Haiku call: context + optional tool result → synthesised reply
4. Update session thread + summary
5. Return reply synchronously (no WebSocket, no job_id)

---

## Section 4: IS Brain Prompt Injection

New `session_context` field injected between `{context_section}` and `{research_plan}` in `RESEARCH_PROMPT`:

```
## SESSION CONTEXT
This is turn {turn_count} of an ongoing investigation session.

Genesis query (the original question anchoring this session):
  "{genesis_query}"

Conversation thread (how the investigation has evolved):
{conversation_thread_last_5}

What has been found so far:
{accumulated_summary}

Key confirmed findings from prior turns:
{key_findings_top_5}

Current message (the latest refinement/direction):
  "{current_message}"

INSTRUCTIONS: The current message evolves the session — it may widen, narrow,
redirect, or add constraints to the genesis query. Your strategy, tactics, and
investigation scope should reflect the FULL session intent, not just the latest
message in isolation. Do not re-investigate what was already confirmed in prior
turns. Build on what exists.
```

**Strategy/tactic adaptation:**
- `complexity_score` computed from **genesis + full thread** (not latest message alone)
- `entity_type` evolves per turn, stored on session
- Meta compiler receives full session context as query signal → strategies adapt across turns

**`build_prompt` signature:**
```python
def build_prompt(..., session_context: str = "") -> str:
```

---

## Section 5: Frontend Changes

### `chatStore.ts`

```typescript
interface ChatState {
  messages: Message[]
  sessionId: string | null
  genesisQuery: string | null
  setSessionId: (id: string) => void
  setGenesisQuery: (q: string) => void
  clearMessages: () => void  // also clears sessionId + genesisQuery
}
```

`sessionId` stored in `localStorage` (survives page reload).

### `AgentChat.tsx` behaviour changes

| Event | Behaviour |
|---|---|
| Send message | Pass `sessionId` with every call |
| First response | Store `session_id` from response → `setSessionId` + `setGenesisQuery` |
| Conversational reply | `mode === "conversational"` → reply arrives synchronously, render directly (no spinner, no ResultsPanel tab) |
| Clear chat | Call `archiveSession(sessionId)` → then `clearMessages()` (clears sessionId too) |
| Session indicator | Header pill: `Turn N · Session active` when session running |

### `v3.ts` API

```typescript
export const sendMessage = (
  message: string,
  sessionId?: string,
  useIntelligentSearch?: boolean,
  parentRunId?: string,
) => api.post<AgentMessageOut>('/v3/agent/message', {
  message, session_id: sessionId,
  use_intelligent_search: useIntelligentSearch,
  parent_run_id: parentRunId,
}).then(r => r.data)

export const archiveSession = (sessionId: string) =>
  api.post(`/v3/agent/sessions/${sessionId}/archive`).then(r => r.data)

export const listSessions = () =>
  api.get('/v3/agent/sessions').then(r => r.data)
```

### Conversational reply UX

- No job_id, no ResultsPanel tab, no spinner
- Reply appears as agent message bubble directly
- If single tool was called, a small collapsed chip shows (e.g. `run_web_search`) inline

---

## Architecture Diagram

```
User types message
       │
       ▼
AgentChat.tsx
  - passes session_id (or null if new)
       │
       ▼
POST /v3/agent/message
       │
       ├─ No session_id → CREATE agent_sessions row (genesis = message)
       │                  → skip classifier, full IS run
       │
       └─ Has session_id → FETCH session
                           → CLASSIFIER (Haiku, ~1s)
                              │
                              ├─ "investigation"
                              │    → build session_context
                              │    → inject into IS brain prompt
                              │    → full async IS brain run
                              │    → update session after
                              │
                              └─ "conversational"
                                   → build context from session
                                   → optional single tool call
                                   → Haiku reply synthesis
                                   → update session
                                   → return reply synchronously
```

---

## What This Unlocks

- **Evolving investigation:** Each follow-up narrows, widens, or redirects without restarting from zero
- **Strategy adaptation:** IS brain's strategy/tactics reflect the full conversation intent, not just the latest message
- **Budget efficiency:** Simple clarifications don't burn full investigation budget
- **Session history:** Archived sessions are browsable — full thread + findings preserved
- **No regression:** Sessions are opt-in per message; existing `parent_run_id` mechanism is unchanged
