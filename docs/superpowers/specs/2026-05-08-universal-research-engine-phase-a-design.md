# Universal Research Engine Phase A: Intelligent Research Planning

**Date:** 2026-05-08
**Status:** Draft
**Depends on:** IS Brain, Research Orchestrator, Strategy System, Memory Phase 1-3
**Reference:** Feynman (getcompanion-ai/feynman) multi-agent research patterns

---

## Problem

The IS brain executes every query the same way: fire-and-forget with a single strategy. This causes two problems:

1. **Ambiguous queries waste research cycles.** "Investigate Company X" could mean financials, leadership, competitive position, or technology stack. The brain guesses and often researches the wrong dimension.

2. **Complex queries need multiple research categories.** "Why is Company X struggling and what should they do?" requires Retrieval (gather facts), Explanation (analyze causes), and Prediction (forecast outcomes). The orchestrator currently picks one category and runs it.

The Feynman research agent (6.8K stars) solves problem 1 with a plan-first workflow that asks clarifying questions before executing. We adopt this pattern while keeping our unique advantages (KG, memory fusion, OSINT tools, self-learning overlays).

## Solution

A **Two-Phase Brain** that classifies queries by complexity, asks clarifying questions for complex ones, builds a multi-step research plan, and executes category-by-category.

## Architecture

### Query Flow

```
User sends message
        |
        v
Scale Classifier (simple or complex?)
        |
        +-- Simple (score <= 0): Execute immediately (current behavior)
        |
        +-- Complex (score > 0):
                |
                v
          Clarification Phase
          (brain asks 1-3 questions via chat)
                |
                v
          User replies in same thread
                |
                v
          Research Planner
          (builds multi-step plan with category sequence)
                |
                v
          Plan saved to DB + shown in UI
                |
                v
          Execute plan (step by step)
          Each step loads its category strategy
                |
                v
          Verifier pass (check sources)
                |
                v
          Results delivered
```

### Phase overview

| Phase | For | What happens |
|-------|-----|-------------|
| **Direct** | Simple queries (score <= 0) | Current behavior unchanged. Single category, immediate execution. |
| **Clarify** | Complex queries (score > 0) | Brain asks 1-3 focused questions. User replies in chat. Q&A persisted. |
| **Plan** | After clarification | Brain builds a structured research plan with category sequence, tools, and completeness criteria. |
| **Execute** | After plan | Each plan step runs with its category strategy. Findings accumulate across steps. |
| **Verify** | After execution | Check source reachability, KG consistency, confidence alignment. |

---

## Scale Classifier

Enhances the existing `orchestrator.py` with a complexity scoring function.

### Scoring signals

| Signal | Score | Example |
|--------|-------|---------|
| Single entity + known type | -2 | "find email of John Doe" |
| Simple lookup verbs ("what is", "find", "look up") | -1 | "what is Acme Corp?" |
| Multi-entity or comparison | +2 | "compare AWS vs Azure vs GCP" |
| Open-ended verbs ("investigate", "analyze", "research") | +2 | "investigate TechCorp" |
| Multi-domain or conjunctions | +3 | "find their team and analyze financials" |
| Causal / explanatory ("why", "root cause") | +1 | "why did revenue drop?" |
| Predictive ("predict", "forecast", "what will") | +1 | "what will happen if they merge?" |
| Long query (> 50 words) | +1 | Detailed multi-part questions |

**Threshold:** Score <= 0 is simple, score > 0 is complex.

### API

```python
def classify_complexity(query: str) -> tuple[str, int]:
    """Return ('simple'|'complex', score)."""
```

Added to `app/pipeline/strategies/orchestrator.py` alongside the existing `classify_query()`.

---

## Clarification Phase

### ask_user MCP Tool

A new tool the IS brain can call to ask the user a question mid-research:

```python
@server.tool()
async def ask_user(question: str, options: list[str] = []) -> str:
    """Ask the user a clarifying question. Returns their answer.
    
    The question is displayed in the chat UI. If options are provided,
    they appear as quick-reply buttons. The tool blocks until the user responds.
    """
```

### Interaction flow

1. IS brain calls `ask_user(question, options)` via MCP
2. MCP server sends HTTP POST to `/v3/agent/brain-question` with run_id, question, options
3. API pushes WebSocket event: `{type: "brain.question", run_id, question, options}`
4. Frontend renders the question as a chat bubble with optional quick-reply buttons
5. User types or clicks a reply
6. Frontend sends reply via POST `/v3/agent/brain-answer` with run_id, answer
7. API stores Q&A in `research_trails.clarification` JSONB array
8. API signals the waiting `ask_user` handler (via asyncio.Event or similar)
9. MCP tool returns the user's answer to the IS brain
10. Brain continues with the clarified context

### Concurrency handling

Each run has a unique `run_id`. The `ask_user` handler creates an `asyncio.Event` keyed by run_id. The brain-answer endpoint sets the event with the answer. Multiple concurrent runs don't interfere because each waits on its own event.

### Prompt injection

The IS brain prompt gains a new section:

```
## CLARIFICATION (for complex queries)

Before starting research, assess whether the query is ambiguous or multi-faceted.
If so, use the ask_user tool to ask 1-3 focused questions:
- What specific aspect to focus on?
- What is the intended use of this research?
- Any constraints (geography, time period, budget)?

Keep questions concise. Provide 3-4 options when possible.
Do NOT ask more than 3 questions total.
After clarification, build your research plan.
```

---

## Research Planner

After clarification (or immediately for simple queries), the brain builds a research plan.

### Plan structure

```json
{
    "query": "Investigate Company X",
    "clarification_summary": "Focus on financials and leadership team",
    "complexity": "complex",
    "category_sequence": ["retrieval", "explanation"],
    "steps": [
        {
            "step": 1,
            "category": "retrieval",
            "goal": "Gather Company X financial data and leadership profiles",
            "strategy_hints": ["Use SEC filings, LinkedIn, news sources"],
            "expected_tools": ["ddg_search", "linkedin_profile", "sec_edgar", "google_news"]
        },
        {
            "step": 2,
            "category": "explanation",
            "goal": "Analyze why revenue declined based on gathered data",
            "strategy_hints": ["Apply root cause analysis to financial findings"],
            "expected_tools": ["ddg_search", "google_news"]
        }
    ],
    "completeness_criteria": [
        "Financial data for last 2 years found",
        "Leadership team identified (CEO, CFO, CTO minimum)",
        "Revenue decline root cause identified with evidence"
    ],
    "estimated_tool_calls": 15
}
```

### Plan persistence

The plan is stored as a new JSONB column on `research_trails`:

```sql
ALTER TABLE research_trails ADD COLUMN IF NOT EXISTS plan JSONB;
ALTER TABLE research_trails ADD COLUMN IF NOT EXISTS clarification JSONB DEFAULT '[]';
ALTER TABLE research_trails ADD COLUMN IF NOT EXISTS verification_status VARCHAR(32);
```

The plan is also pushed to the frontend via WebSocket so the user can see the research strategy before execution begins.

### Plan in the IS prompt

A new `{research_plan}` placeholder in `is_prompt.py` renders the plan as structured context:

```
## YOUR RESEARCH PLAN

You have already clarified this query with the user. Execute this plan:

Step 1 [retrieval]: Gather Company X financial data and leadership profiles
  Tools to use: ddg_search, linkedin_profile, sec_edgar, google_news

Step 2 [explanation]: Analyze why revenue declined based on gathered data
  Tools to use: ddg_search, google_news

Completeness criteria:
- Financial data for last 2 years found
- Leadership team identified
- Revenue decline root cause identified
```

---

## Cross-Category Execution

When the plan has multiple steps across categories:

1. Orchestrator loads the strategy for step 1's category
2. IS brain executes step 1 with that strategy injected
3. Findings from step 1 are accumulated
4. Orchestrator loads step 2's strategy
5. Step 1 findings are passed as context to step 2
6. Repeat until all steps complete

### Implementation

The `_run_is_research` function in `agent.py` gains a loop:

```python
for step in plan["steps"]:
    strategy = load_strategy(step["category"])
    findings = await run_brain_step(step, strategy, prior_findings)
    all_findings.extend(findings)
    prior_findings = all_findings
```

For simple queries (no plan), the current single-pass behavior is unchanged.

---

## Verifier Pass

After all plan steps complete, a lightweight verification runs:

### Checks

1. **Source reachability** -- HTTP HEAD on all finding URLs. Flag unreachable sources.
2. **KG consistency** -- compare findings against existing entity_observations. Flag contradictions with known facts.
3. **Confidence alignment** -- findings from low-Admiralty sources (F-rated) should not have confidence > 70.

### Output

```python
def verify_findings(findings: list[dict]) -> dict:
    """Returns {status: 'PASS'|'PASS_WITH_NOTES'|'BLOCKED', issues: [...]}"""
```

Stored on `research_trails.verification_status`.

### Scope

Phase A verification is lightweight (rule-based). LLM-assisted deep verification is deferred to Phase B.

---

## Frontend Changes

### Brain question rendering

When `brain.question` WS event arrives:
- Render as a special chat bubble (distinct from normal assistant messages)
- If options provided, show as clickable pills/buttons
- User can type a custom answer or click an option
- After answering, the bubble shows the Q&A as read-only history

### Plan display

When `brain.plan` WS event arrives:
- Render as a collapsible plan card in the chat
- Shows category sequence as colored step badges
- Each step shows goal + expected tools
- Completeness criteria as a checklist (checked off as findings arrive)

### Verification badge

After run completes, show verification status as a badge on the run tab:
- PASS: green checkmark
- PASS_WITH_NOTES: yellow warning
- BLOCKED: red x

---

## New/Modified Files

### New files

| File | Purpose |
|------|---------|
| `app/pipeline/strategies/planner.py` | Build research plan from clarified query |
| `app/pipeline/strategies/verifier.py` | Post-run source verification |
| `tests/pipeline/strategies/test_planner.py` | Planner tests |
| `tests/pipeline/strategies/test_verifier.py` | Verifier tests |
| `tests/pipeline/strategies/test_orchestrator_complexity.py` | Scale classifier tests |

### Modified files

| File | Change |
|------|--------|
| `app/pipeline/strategies/orchestrator.py` | Add `classify_complexity()` |
| `app/is_brain.py` | Plan-aware execution, multi-step loop |
| `app/is_prompt.py` | Add `{research_plan}` and clarification prompt section |
| `app/routers/v3/agent.py` | Handle brain questions, route answers, multi-step execution |
| `app/routers/v3/db.py` | ALTER TABLE: add plan, clarification, verification_status columns |
| `mcp_server/server.py` | Add `ask_user` tool |
| `frontend/src/components/results/ResultsPanel.tsx` | Render brain questions, plan cards, verification badge |

---

## Testing Strategy

### Unit tests
- Scale classifier: 10+ test cases covering all signal types
- Planner: plan generation from clarified queries, category sequence logic
- Verifier: source check mocking, KG contradiction detection

### Integration tests
- Full flow: complex query -> clarification -> plan -> execute -> verify
- Simple query: direct execution (no plan step)
- Multi-category plan: retrieval -> explanation sequence

### E2E test
- Playwright: send complex query, verify brain question appears, answer it, verify plan renders, verify results

---

## Scope Boundaries

**In scope (Phase A):**
- Scale classifier (simple vs complex)
- ask_user MCP tool for clarification
- Clarification Q&A persistence
- Research plan generation and persistence
- Cross-category execution loop
- Lightweight source verification
- Frontend: question rendering, plan display, verification badge

**Out of scope (Phase B: Tool Mapping):**
- Tool-to-strategy mapping for all 5 categories
- Self-learning overlays for non-person categories
- Completeness validation tied to strategy checklists

**Out of scope (Phase C: Domain Sub-Strategies):**
- Market research, due diligence, competitive intel sub-strategies
- Drug discovery, patent search sub-strategies
