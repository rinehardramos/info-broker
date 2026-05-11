# Analyze Node + Error Detection + User Feedback Design

## Problem

The IS brain scores error results (API 403s, missing keys, permission denials) as high-confidence findings (75-99%). Users see "Apollo blocked — 422" scored at 75% alongside real findings. There is no mechanism for user feedback to correct these scores or prevent recurrence.

## Goal

Three components working together:
1. **Error pre-filter** — automatically detect and flag error results before scoring
2. **Analyze node** — multi-stage structured intelligence from passing results
3. **User feedback** — manual scoring that weights against brain scores and trains future runs

---

## Component 1: Error Detection Pre-Filter

### Location
`app/is_brain.py` — added to `_parse_output()` after findings are extracted.

### Logic
Before findings are returned, each finding is checked against error patterns:

```python
_ERROR_PATTERNS = [
    "blocked", "403 forbidden", "404 not found", "422 unprocessable",
    "not configured", "api key", "api_key", "permission error",
    "authentication", "timed out", "connection refused", "rate limit",
    "access denied", "unauthorized", "quota exceeded",
]

def _classify_finding(finding: dict) -> dict:
    title = (finding.get("title") or "").lower()
    content = (finding.get("content") or "").lower()
    combined = f"{title} {content}"

    is_error = any(p in combined for p in _ERROR_PATTERNS)
    if is_error:
        finding["finding_type"] = "error"
        finding["confidence"] = 0
        finding["error_flagged"] = True
    else:
        finding["finding_type"] = "result"
        finding["error_flagged"] = False
    return finding
```

### Effect
- Error findings get `confidence: 0` and `finding_type: "error"`
- They're still included in the output (not dropped) so users can see what failed
- The Analyze node ignores them; the UI renders them differently (greyed out, error badge)

---

## Component 2: Analyze Node (Multi-Stage)

### Node Metadata
```python
node_type = "analyzer"
display_name = "Intelligence Analyzer"
category = "enrich"
```

### Config Schema
```json
{
  "properties": {
    "analysis_type": {
      "type": "string",
      "enum": ["comprehensive", "entity_extraction", "competitive", "risk_assessment"],
      "default": "comprehensive"
    },
    "min_confidence": {
      "type": "integer",
      "default": 50,
      "description": "Only analyze findings with confidence >= this threshold"
    },
    "model": {
      "type": "string",
      "default": "claude-haiku-4-5-20251001"
    },
    "context_prompt": {
      "type": "string",
      "description": "Additional context for the analysis (e.g., 'Focus on IT outsourcing needs')"
    }
  }
}
```

### Execution Stages

**Input:** `list[dict]` — items from upstream nodes (findings, search results, enrichment data)

**Pre-processing:**
- Filter out items where `error_flagged == True` or `confidence < min_confidence`
- Group remaining items by source, entity, or topic

**Stage 1 — Entity Extraction (one LLM call):**

Prompt: "Extract all entities (people, companies, roles, locations, technologies) from these findings. For each entity, list its attributes and which finding(s) mention it."

Output:
```json
{
  "entities": [
    {
      "name": "Juan dela Cruz",
      "type": "person",
      "attributes": {"role": "CEO", "company": "TechPH Inc", "location": "Manila"},
      "evidence": ["finding_id_1", "finding_id_3"]
    }
  ]
}
```

**Stage 2 — Relationship Mapping (one LLM call):**

Prompt: "Given these entities, identify relationships between them. Types: works_at, founded, uses_service, competes_with, partners_with, reports_to."

Output:
```json
{
  "relationships": [
    {"from": "Juan dela Cruz", "to": "TechPH Inc", "type": "works_at", "role": "CEO", "evidence": "finding_id_1"},
    {"from": "TechPH Inc", "to": "Accenture PH", "type": "outsources_to", "evidence": "finding_id_5"}
  ]
}
```

**Stage 3 — Synthesis (one LLM call):**

Prompt: "Based on these entities and relationships, produce: (1) actionable insights, (2) recommended next steps, (3) research gaps, (4) suggested enrichment targets."

Output:
```json
{
  "insights": [
    "3 of the 5 identified SME CEOs are in the manufacturing sector, suggesting IT outsourcing demand correlates with manufacturing digitalization in PH."
  ],
  "recommendations": [
    {"action": "Reach out to Juan dela Cruz at TechPH", "reason": "CEO of SME with explicit IT outsourcing need", "priority": "high"}
  ],
  "research_gaps": [
    {"entity": "TechPH Inc", "missing": "revenue/employee count", "suggested_tool": "run_opencorporates"}
  ],
  "enrichment_targets": [
    {"entity": "Maria Santos", "action": "linkedin_profile_search", "reason": "Found name but no contact details"}
  ]
}
```

### Final Output

Single item dict combining all three stages:
```json
{
  "source": "analyzer",
  "analysis_type": "comprehensive",
  "entities": [...],
  "relationships": [...],
  "insights": [...],
  "recommendations": [...],
  "research_gaps": [...],
  "enrichment_targets": [...],
  "error_summary": {
    "total_errors": 5,
    "tools_failing": ["apollo_zoominfo", "hunter_io", "clutch_goodfirms"],
    "action_needed": "Configure API keys in Settings > Node Health"
  },
  "stats": {
    "findings_analyzed": 15,
    "findings_filtered_as_errors": 5,
    "entities_extracted": 12,
    "relationships_found": 8
  }
}
```

---

## Component 3: User Manual Scoring (Feedback Loop)

### Database

New table:
```sql
CREATE TABLE finding_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES ui_users(id),
    run_id UUID NOT NULL,
    finding_index INTEGER NOT NULL,  -- position in findings array
    finding_title TEXT,
    user_score INTEGER CHECK (user_score BETWEEN -1 AND 1),  -- -1=bad, 0=neutral, 1=good
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, run_id, finding_index)
);
```

### API Endpoints

```
POST /v3/research-trails/{run_id}/findings/{index}/feedback
Body: { "score": -1, "reason": "This is an API error, not a finding" }

GET /v3/research-trails/{run_id}/findings/{index}/feedback
Returns: { "user_score": -1, "reason": "..." }
```

### Frontend UI

Each finding card gets:
- Thumbs up (score: 1) / Thumbs down (score: -1) buttons
- When thumbs down: finding visually dims, score shows as overridden
- Optional reason text input on thumbs down

### Feedback Learning

When user marks a finding as bad:
1. Store in `finding_feedback` table
2. Check if the finding matches error patterns (blocked, 403, etc.)
3. If pattern detected, add to `core_settings` key `scoring.error_patterns` (JSON array)
4. Future IS runs load these patterns and apply them in the error pre-filter

This creates a **closed feedback loop**: user marks error → pattern stored → future runs auto-flag similar errors.

### Weighted Score Display

The UI shows both scores:
```
AI: 85%  |  You: 👎  |  Effective: 0%
```

Effective score formula: if `user_score == -1`, effective = 0. If `user_score == 1`, effective = min(ai_score + 10, 100). If no feedback, effective = ai_score.

---

## MCP Tool

```python
@mcp.tool()
async def run_analyzer(items: str, analysis_type: str = "comprehensive", context: str = "") -> str:
    """Analyze research findings to extract entities, relationships, insights, and action items."""
```

## IS Brain Integration

The IS brain's DELIVER section should:
1. Run the error pre-filter on all findings before outputting
2. Include error_summary in its output
3. When the Analyze node exists in the pipeline, the brain can call `run_analyzer` as a tool

## Large Dataset Handling: Map-Reduce (Zero Information Loss)

For large result sets, the analyzer uses a map-reduce pattern instead of summarization (which would dilute specific names, numbers, and URLs):

1. **MAP phase:** Extract entities and facts from each finding independently (parallel LLM calls, one per finding or small batch). Each call sees full detail of its finding(s).
2. **REDUCE phase:** Merge all extracted entity lists — deduplicate by name, merge attributes from multiple sources, resolve conflicts.
3. **ANALYZE phase:** Run relationship mapping + synthesis on the merged entity graph (compact structured data, not prose).

**Thresholds:**
- **<= 20 findings:** Single-pass (all 3 stages in sequence, one LLM call per stage)
- **> 20 findings:** Map-Reduce (batch findings into groups of 10 for MAP, then REDUCE + ANALYZE)

This preserves every name, URL, and data point while keeping LLM context manageable.

## Frontend Changes

### ResearchResults component — Analyze Button
- Add **"Analyze"** button next to the existing **"Go Deeper"** button
- Analyze button sends findings to the analyzer endpoint and displays results in an AnalysisPanel
- Button states: idle → "Analyzing..." (spinner) → results shown
- The Analyze action calls `POST /v3/nodes/analyzer/execute` with the current findings as input

### ResearchResults component — User Feedback
- Each finding card: add thumbs up/down buttons
- Error findings: render with red border, "Error" badge, greyed text
- Show effective score (AI score weighted by user feedback)

### New: AnalysisPanel component
- Renders below the findings when Analyze completes
- Shows: entity list, relationship graph, insights, recommendations
- Entity cards expandable to show evidence
- Research gaps show "Enrich" button that triggers the suggested tool
- Error summary section: "5 tools failing — configure in Settings"

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `app/pipeline/nodes/analyzer.py` | Create — Analyze node |
| `app/is_brain.py` | Modify — add error pre-filter to `_parse_output()` |
| `app/routers/v3/research_api.py` | Modify — add feedback endpoints |
| `app/routers/v3/db.py` | Modify — add `finding_feedback` table |
| `mcp_server/server.py` | Modify — add `run_analyzer` tool |
| `app/pipeline/nodes/__init__.py` | Modify — register AnalyzerNode |
| `frontend/src/components/results/ResearchResults.tsx` | Modify — add thumbs up/down, error styling |
| `frontend/src/components/results/AnalysisPanel.tsx` | Create — render analysis output |
| `frontend/src/api/v3.ts` | Modify — add feedback API calls |
