# Analyze Node + Error Filter + User Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add intelligence analysis with error detection and user feedback to IS brain research results.

**Architecture:** Three independent components — (1) error pre-filter in is_brain.py catches tool failures before scoring, (2) AnalyzerNode performs map-reduce entity extraction + relationship mapping + synthesis, (3) user feedback API + UI lets users thumbs-down bad findings which trains future error detection.

**Tech Stack:** Python/FastAPI backend, Claude API for LLM calls, React/TypeScript frontend, PostgreSQL for feedback storage.

---

### Task 1: Error Detection Pre-Filter

**Files:**
- Modify: `app/is_brain.py`
- Test: `tests/test_error_filter.py`

- [ ] **Step 1: Write failing test for _classify_finding**

```python
# tests/test_error_filter.py
"""Tests for IS brain error detection pre-filter."""
from app.is_brain import _classify_finding

def test_classify_finding_detects_403_error():
    finding = {"title": "Apollo blocked - 422 Unprocessable", "content": "API returned 422", "confidence": 85}
    result = _classify_finding(finding)
    assert result["finding_type"] == "error"
    assert result["confidence"] == 0
    assert result["error_flagged"] is True

def test_classify_finding_detects_api_key_error():
    finding = {"title": "Hunter.io - HUNTER_IO_API_KEY not configured", "content": "Missing key", "confidence": 99}
    result = _classify_finding(finding)
    assert result["finding_type"] == "error"
    assert result["confidence"] == 0

def test_classify_finding_passes_real_result():
    finding = {"title": "CEO of TechPH Inc", "content": "Juan dela Cruz founded TechPH", "confidence": 80}
    result = _classify_finding(finding)
    assert result["finding_type"] == "result"
    assert result["error_flagged"] is False
    assert result["confidence"] == 80

def test_classify_finding_detects_permission_error():
    finding = {"title": "LinkedIn Apify blocked", "content": "requires full access to your account", "confidence": 99}
    result = _classify_finding(finding)
    assert result["finding_type"] == "error"

def test_classify_finding_detects_rate_limit():
    finding = {"title": "Google rate limited", "content": "429 rate limit exceeded", "confidence": 70}
    result = _classify_finding(finding)
    assert result["finding_type"] == "error"

def test_classify_finding_handles_missing_fields():
    finding = {}
    result = _classify_finding(finding)
    assert result["finding_type"] == "result"
    assert result["error_flagged"] is False
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `uv run pytest tests/test_error_filter.py -v`
Expected: FAIL — `_classify_finding` not importable

- [ ] **Step 3: Implement _classify_finding and wire into _parse_output**

Add to `app/is_brain.py` (after the imports, before `_parse_output`):

```python
_ERROR_PATTERNS = [
    "blocked", "403 forbidden", "403 Forbidden", "404 not found", "422 unprocessable",
    "not configured", "api key", "api_key", "permission error",
    "authentication", "timed out", "connection refused", "rate limit",
    "rate_limit", "access denied", "unauthorized", "quota exceeded",
    "requires full access", "token is not valid", "user was not found",
]

def _classify_finding(finding: dict) -> dict:
    """Detect error findings that the brain mistakenly scored as high-confidence."""
    title = (finding.get("title") or "").lower()
    content = (finding.get("content") or "").lower()
    combined = f"{title} {content}"

    is_error = any(p.lower() in combined for p in _ERROR_PATTERNS)
    if is_error:
        finding["finding_type"] = "error"
        finding["confidence"] = 0
        finding["error_flagged"] = True
    else:
        finding.setdefault("finding_type", "result")
        finding["error_flagged"] = False
    return finding
```

In `_parse_output`, after `if isinstance(research, dict) and "findings" in research:`, add:

```python
research["findings"] = [_classify_finding(f) for f in research["findings"]]
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run pytest tests/test_error_filter.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add app/is_brain.py tests/test_error_filter.py
git commit -m "feat: error detection pre-filter for IS brain findings"
```

---

### Task 2: Analyzer Pipeline Node

**Files:**
- Create: `app/pipeline/nodes/analyzer.py`
- Test: `tests/pipeline/nodes/test_analyzer.py`
- Modify: `app/pipeline/nodes/__init__.py`

- [ ] **Step 1: Write failing tests for AnalyzerNode**

```python
# tests/pipeline/nodes/test_analyzer.py
"""Tests for the Intelligence Analyzer node."""
from __future__ import annotations
import asyncio
import json
from unittest.mock import patch, AsyncMock
from app.pipeline.nodes.analyzer import AnalyzerNode, _filter_errors
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")

def _arun(coro):
    return asyncio.run(coro)

# --- _filter_errors ---

def test_filter_errors_removes_flagged():
    items = [
        {"title": "Good", "confidence": 80, "error_flagged": False},
        {"title": "Bad", "confidence": 0, "error_flagged": True},
        {"title": "Low", "confidence": 30, "error_flagged": False},
    ]
    result = _filter_errors(items, min_confidence=50)
    assert len(result) == 1
    assert result[0]["title"] == "Good"

def test_filter_errors_keeps_all_above_threshold():
    items = [
        {"title": "A", "confidence": 90, "error_flagged": False},
        {"title": "B", "confidence": 60, "error_flagged": False},
    ]
    result = _filter_errors(items, min_confidence=50)
    assert len(result) == 2

def test_filter_errors_handles_missing_fields():
    items = [{"title": "No flags"}]
    result = _filter_errors(items, min_confidence=0)
    assert len(result) == 1

# --- Node metadata ---

def test_node_metadata():
    node = AnalyzerNode()
    assert node.node_type == "analyzer"
    assert node.display_name == "Intelligence Analyzer"
    assert node.category == "enrich"
    assert "analysis_type" in node.config_schema["properties"]
    assert "min_confidence" in node.config_schema["properties"]

# --- Execute with mock LLM ---

def test_execute_returns_structured_analysis():
    node = AnalyzerNode()
    mock_response = json.dumps({
        "entities": [{"name": "Test Corp", "type": "company", "attributes": {}, "evidence": []}],
        "relationships": [],
        "insights": ["Test insight"],
        "recommendations": [],
        "research_gaps": [],
        "enrichment_targets": [],
    })
    items = [
        {"title": "Finding 1", "content": "Test Corp is a company", "confidence": 80, "error_flagged": False},
    ]

    with patch("app.pipeline.nodes.analyzer._call_llm", new_callable=AsyncMock, return_value=mock_response):
        results = _arun(node.execute({}, items, CTX))

    assert len(results) == 1
    assert results[0]["source"] == "analyzer"
    assert "entities" in results[0]
    assert "insights" in results[0]

def test_execute_with_all_errors_returns_error_summary_only():
    node = AnalyzerNode()
    items = [
        {"title": "Error 1", "confidence": 0, "error_flagged": True},
        {"title": "Error 2", "confidence": 0, "error_flagged": True},
    ]
    results = _arun(node.execute({}, items, CTX))
    assert len(results) == 1
    assert results[0]["source"] == "analyzer"
    assert results[0]["stats"]["findings_analyzed"] == 0
    assert results[0]["stats"]["findings_filtered_as_errors"] == 2
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `uv run pytest tests/pipeline/nodes/test_analyzer.py -v`

- [ ] **Step 3: Implement AnalyzerNode**

Create `app/pipeline/nodes/analyzer.py` with:
- `_filter_errors(items, min_confidence)` — filter out error-flagged and low-confidence items
- `_call_llm(prompt, model)` — async LLM call via the existing provider pattern from summarizer.py
- `_format_items(items)` — format findings for LLM context
- Stage 1 prompt: entity extraction
- Stage 2 prompt: relationship mapping (receives stage 1 output)
- Stage 3 prompt: synthesis (receives stages 1+2)
- Map-reduce for >20 items: batch MAP calls, then REDUCE merge, then stages 2+3
- `execute()` orchestrates the pipeline

- [ ] **Step 4: Register in __init__.py**

Add to `app/pipeline/nodes/__init__.py`:
```python
from app.pipeline.nodes.analyzer import AnalyzerNode
# In the register list:
AnalyzerNode(),
```

- [ ] **Step 5: Add MCP tool to mcp_server/server.py**

```python
@mcp.tool()
async def run_analyzer(items: str, analysis_type: str = "comprehensive", context_prompt: str = "") -> str:
    """Analyze research findings to extract entities, relationships, insights, and action items."""
    result = await api_call(
        "POST", "/v3/nodes/analyzer/execute",
        json={"items": json.loads(items), "analysis_type": analysis_type, "context_prompt": context_prompt},
    )
    return json.dumps(result)
```

- [ ] **Step 6: Run tests — expect PASS**

Run: `uv run pytest tests/pipeline/nodes/test_analyzer.py -v`

- [ ] **Step 7: Commit**

```bash
git add app/pipeline/nodes/analyzer.py app/pipeline/nodes/__init__.py mcp_server/server.py tests/pipeline/nodes/test_analyzer.py
git commit -m "feat: Intelligence Analyzer node with map-reduce entity extraction"
```

---

### Task 3: User Feedback API

**Files:**
- Modify: `app/routers/v3/db.py` — add finding_feedback table
- Modify: `app/routers/v3/research_api.py` — add feedback endpoints
- Test: `tests/test_finding_feedback.py`

- [ ] **Step 1: Add finding_feedback table to db.py**

In `app/routers/v3/db.py`, add to the schema creation section:

```sql
CREATE TABLE IF NOT EXISTS finding_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES ui_users(id),
    run_id UUID NOT NULL,
    finding_index INTEGER NOT NULL,
    finding_title TEXT,
    user_score INTEGER CHECK (user_score BETWEEN -1 AND 1),
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, run_id, finding_index)
);
```

- [ ] **Step 2: Add feedback endpoints to research_api.py**

```python
@router.post("/research-trails/{run_id}/findings/{index}/feedback")
def submit_finding_feedback(
    run_id: str, index: int, body: dict,
    user: dict = Depends(get_current_user),
):
    uid = str(user["id"])
    execute(
        """INSERT INTO finding_feedback (id, user_id, run_id, finding_index, finding_title, user_score, reason)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, run_id, finding_index)
        DO UPDATE SET user_score = EXCLUDED.user_score, reason = EXCLUDED.reason, created_at = now()""",
        (str(uuid.uuid4()), uid, run_id, index, body.get("title", ""), body.get("score", 0), body.get("reason", "")),
    )
    # If thumbs down on an error pattern, store for future auto-detection
    if body.get("score") == -1:
        _learn_error_pattern(body.get("title", ""), body.get("reason", ""))
    return {"status": "ok"}

@router.get("/research-trails/{run_id}/feedback")
def get_run_feedback(run_id: str, user: dict = Depends(get_current_user)):
    uid = str(user["id"])
    rows = fetch_all(
        "SELECT finding_index, user_score, reason FROM finding_feedback WHERE user_id = %s AND run_id = %s",
        (uid, run_id),
    )
    return {str(r["finding_index"]): {"score": r["user_score"], "reason": r["reason"]} for r in rows}
```

- [ ] **Step 3: Add _learn_error_pattern helper**

```python
def _learn_error_pattern(title: str, reason: str):
    """Extract error keywords from user feedback and store for future auto-detection."""
    import json
    row = fetch_one("SELECT value FROM core_settings WHERE key = 'scoring.error_patterns'", ())
    patterns = json.loads(row["value"]) if row else []
    # Extract meaningful keywords from the title
    keywords = [w.lower() for w in (title or "").split() if len(w) > 3 and w.isalpha()]
    for kw in keywords[:3]:  # max 3 new keywords per feedback
        if kw not in patterns and kw not in ("the", "and", "for", "from", "with", "that", "this"):
            patterns.append(kw)
    if patterns:
        execute(
            "INSERT INTO core_settings (key, value, is_secret) VALUES (%s, %s, false) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            ("scoring.error_patterns", json.dumps(patterns)),
        )
```

- [ ] **Step 4: Commit**

```bash
git add app/routers/v3/db.py app/routers/v3/research_api.py
git commit -m "feat: user feedback API for research findings with error pattern learning"
```

---

### Task 4: Frontend — Analyze Button + Feedback UI + Error Styling

**Files:**
- Modify: `frontend/src/components/results/ResultsPanel.tsx` — add Analyze button, thumbs up/down, error styling
- Create: `frontend/src/components/results/AnalysisPanel.tsx` — render analysis output
- Modify: `frontend/src/api/v3.ts` — add feedback + analyze API calls

- [ ] **Step 1: Add API functions to v3.ts**

```typescript
export const submitFindingFeedback = (runId: string, index: number, score: number, reason?: string) =>
  api.post(`/v3/research-trails/${runId}/findings/${index}/feedback`, { score, reason }).then(r => r.data)

export const getRunFeedback = (runId: string): Promise<Record<string, { score: number; reason: string }>> =>
  api.get(`/v3/research-trails/${runId}/feedback`).then(r => r.data)

export const runAnalyzer = (items: object[], analysisType?: string, contextPrompt?: string) =>
  api.post('/v3/nodes/analyzer/execute', { items, analysis_type: analysisType, context_prompt: contextPrompt }).then(r => r.data)
```

- [ ] **Step 2: Add Analyze button next to Go Deeper in ResearchResults**

In `ResultsPanel.tsx`, in the action buttons section (after the Go Deeper button), add:

```tsx
{/* Analyze */}
<button
  onClick={handleAnalyze}
  disabled={analyzing}
  style={{
    background: analyzing ? '#f59e0b22' : '#f59e0b22',
    border: '1px solid #f59e0b55', color: '#f59e0b',
    fontSize: 11, fontWeight: 600, padding: '6px 14px', borderRadius: 6,
    cursor: analyzing ? 'not-allowed' : 'pointer', opacity: analyzing ? 0.5 : 1,
  }}
>
  {analyzing ? '⟳ Analyzing...' : '◈ Analyze'}
</button>
```

Add state and handler:
```tsx
const [analyzing, setAnalyzing] = useState(false)
const [analysis, setAnalysis] = useState<any>(null)

const handleAnalyze = async () => {
  setAnalyzing(true)
  try {
    const result = await runAnalyzer(trail.findings)
    setAnalysis(result)
  } finally {
    setAnalyzing(false)
  }
}
```

- [ ] **Step 3: Add thumbs up/down to each finding card**

Each finding card gets feedback buttons. Error findings get red border + "Error" badge.

- [ ] **Step 4: Create AnalysisPanel component**

`frontend/src/components/results/AnalysisPanel.tsx` renders the analysis output:
- Entity list with expandable attributes
- Relationship list
- Insights as bullet points
- Recommendations with priority badges
- Research gaps with "Enrich" action buttons
- Error summary section

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/results/ResultsPanel.tsx frontend/src/components/results/AnalysisPanel.tsx frontend/src/api/v3.ts
git commit -m "feat: Analyze button, user feedback thumbs, and AnalysisPanel in research results"
```

---

### Task 5: Rebuild + Live Test

- [ ] **Step 1: Run all tests**

```bash
uv run pytest tests/ -q
```

- [ ] **Step 2: Rebuild and deploy**

```bash
docker compose build info-broker-api && docker compose up -d info-broker-api
```

- [ ] **Step 3: Test error filter**

Run an IS research query. Verify error findings show confidence: 0 and finding_type: "error".

- [ ] **Step 4: Test Analyze button**

Click Analyze on completed research. Verify structured entities/relationships/insights appear.

- [ ] **Step 5: Test thumbs down**

Click thumbs down on an error finding. Verify feedback is stored and pattern learning triggers.

- [ ] **Step 6: Commit final**

```bash
git add -A && git commit -m "feat: complete analyze node + error filter + user feedback system"
```
