# Technique Catalog + Auto-Create Plugin Pipeline — Design Spec

**Date:** 2026-05-07
**Status:** Draft
**Depends on:** `2026-05-07-comprehensive-investigation-strategy-design.md` (strategy/tactics/techniques hierarchy)

## Problem Statement

The IS brain has 59+ tools but no structured mapping of WHICH tools to combine for WHICH investigative tactic. The brain sees a flat list and must independently figure out tool sequences. Additionally, when the brain identifies a missing tool (`suggest_plugin`), the current flow requires manual human review before the tool is created — blocking the investigation.

Three gaps:
1. **Technique layer is implicit** — no structured catalog mapping tactics → tool sequences
2. **Search is single-engine** — DDG only, missing results that Google/Brave/Yandex would surface
3. **Plugin creation is manual** — 97 pending suggestions, many duplicates, no automated assessment or creation

## Architecture

### Strategy → Tactics → Techniques Hierarchy (Corrected)

| Level | Scope | Example | Storage |
|-------|-------|---------|---------|
| **Strategy** | Overarching plan — WHAT to investigate | "Discover and verify all email addresses" | `strategies/person.py` + compiler overlays |
| **Tactics** | HOW to execute using available environment | "Find company website, extract contact emails, try name patterns at domain" | Pivot patterns in strategy prompt text |
| **Techniques** | Specific tool sequences — precise steps | `email_enumerator → smtp_verifier → hibp_lookup` | **Technique catalog (NEW)** |

---

## Part 1: Multi-Engine Meta-Search

### Overview

Upgrade web search from single-engine (DDG) to multi-engine parallel dispatch with cross-engine consensus ranking. This is a transparent capability upgrade — the IS brain calls `run_multi_search` and gets results from multiple engines automatically.

### Engine Backends

| Backend | Index | Cost | Key Required | Env Var |
|---------|-------|------|-------------|---------|
| `ddg` | Bing-based | Free | No | — |
| `serper` | Google | $0.001/q | Optional | `SERPER_API_KEY` |
| `brave` | Independent | Free 2K/mo | Optional | `BRAVE_API_KEY` |
| `exa` | Neural/semantic | Free tier | Optional | `EXA_API_KEY` |
| `yandex` | Russian/CIS | Free tier | Optional | `YANDEX_API_KEY` |
| `baidu` | Chinese | Free tier | Optional | `BAIDU_API_KEY` |

If no key is configured for an engine, it's silently skipped. DDG always available.

### Implementation

**New file:** `app/pipeline/nodes/multi_search.py`

```python
class MultiSearchNode:
    node_type = "multi_search"
    display_name = "Multi-Engine Web Search"
    category = "source"
    
    config_schema = {
        "properties": {
            "query": {"type": "string"},
            "engines": {"type": "array", "items": {"type": "string"},
                       "default": ["ddg", "serper", "brave"]},
            "max_results": {"type": "integer", "default": 20},
        }
    }
```

**Engine dispatch:** `asyncio.gather()` all configured engines in parallel.

**Deduplication:** Normalize URLs (strip tracking params, trailing slashes), group by URL, merge snippets.

**Consensus ranking:** `consensus_score = len(engines_that_found_it)`. Sort by consensus DESC, then by position in first engine's results.

**Output per result:**
```json
{
    "title": "...",
    "url": "...",
    "snippet": "...",
    "engines": ["ddg", "serper", "brave"],
    "consensus_score": 3,
    "source": "multi_search"
}
```

### Integration

- Register in `NodeRegistry.auto_discover()`
- Add to `_STATIC_TOOLS` in `is_prompt.py`
- Strategy pivot patterns reference `run_multi_search` for web search pivots
- DDG node remains available for backward compatibility

---

## Part 2: Technique Catalog

### Overview

A structured, queryable registry mapping investigative tactics to proven tool sequences. Injected into the IS brain prompt so it knows exactly which tools to combine for each tactic.

### Data Model

```python
@dataclass
class Technique:
    name: str                     # "email_discovery"
    description: str              # "Discover and verify email addresses for a person"
    tactic: str                   # "digital_footprint_mapping"
    selector_types: list[str]     # ["full_name", "domain"]
    tool_sequence: list[str]      # ["email_enumerator", "smtp_verifier", "hibp_lookup"]
    when_to_use: str             # "When you have a person's name and need their email"
    expected_output: str          # "Verified email addresses with breach exposure data"
    category: str                # "person" | "company" | "general"
```

### Initial Catalog (derived from existing pivot patterns + implemented nodes)

**Person Investigation Techniques:**

| Technique | Tactic | Tool Sequence | When to Use |
|-----------|--------|---------------|-------------|
| email_discovery | digital_footprint | email_enumerator → smtp_verifier → hibp_lookup | Have name, need email |
| social_media_mapping | digital_footprint | username_enumerator → instagram_profile → facebook_pages → twitter_search | Have name or username |
| professional_profiling | professional_history | linkedin_profile → apollo_zoominfo → hunter_io | Need employment + contact info |
| breach_analysis | breach_intel | hibp_lookup → reverse_lookup | Have email, need breach exposure |
| phone_reconnaissance | communication_intel | phone_osint → messaging_check → reverse_lookup | Have phone number |
| regulatory_verification | public_records | ph_sec_dti → ph_bir → opencorporates → pep_sanctions_screen | Need corporate/regulatory records |
| visual_intelligence | visual_intel | face_search → exif_extractor | Have photo |
| negative_screening | public_records | pep_sanctions_screen → adverse_media | Need risk assessment |
| web_deep_search | general_research | multi_search → web_crawl → document_search | Need comprehensive web coverage |
| domain_investigation | digital_footprint | whois_lookup → shodan_search → hunter_io | Have domain name |

**General Techniques:**

| Technique | Tool Sequence | When to Use |
|-----------|---------------|-------------|
| academic_research | openalex_search → semantic_scholar_search | Need scholarly papers + citations |
| github_analysis | github_search | Need code/repo/developer research |
| location_intelligence | google_maps_places | Need local business data + reviews |
| media_research | tmdb_search → google_news | Need entertainment/media metadata |

### Storage

**File:** `app/pipeline/techniques.py`

Techniques are defined as a Python list of dicts (not DB — they're code-level configuration). The auto-create system can append new techniques dynamically.

### Prompt Injection

The technique catalog is injected into the IS brain prompt AFTER the entity strategy section:

```
{entity_strategy}

## INVESTIGATION TECHNIQUES (proven tool sequences)
When executing a tactic, use these proven sequences:

Email Discovery (when you have a name and need email):
  run_email_enumerator(first, last) → run_smtp_verifier(email) → run_hibp_lookup(email)

Social Media Mapping (when you have a name/username):
  run_username_enumerator(username) → run_instagram_profile → run_facebook_pages → run_twitter_search

...

{strategies_section}
## YOUR WORKFLOW
```

### Self-Learning Integration

The strategy overlay system already tracks which tools work (reinforce/prune). Technique sequences that consistently produce findings get reinforced. New technique sequences discovered by the brain (tool combinations not in the catalog) get added via the "discover" overlay type.

---

## Part 3: Auto-Create Plugin Pipeline

### Overview

When `auto_create_techniques` is toggled ON in Settings, the system automatically generates new pipeline nodes when the IS brain requests a missing tool. The generated code runs in-process with full trust.

### Settings Toggle

**DB:** `core_settings` table, key: `auto_create_techniques`, value: `"true"` or `"false"` (default: `"false"`)

### Flow

```
IS Brain calls: suggest_plugin(name, description, reason)
    ↓
MCP Server suggest_plugin() handler:
    ↓
Existing dedup logic (exact match, partial match, keyword overlap)
    ↓
If truly new AND auto_create_techniques = "true":
    ↓
Step 1: MERIT ASSESSMENT (LLM call, Haiku-class, ~2s)
    Input: {name, description, reason, existing_node_types}
    Output: {achievable: HIGH|MEDIUM|LOW, api_url, auth_method, response_format, category}
    If LOW → store as pending, return "needs_manual"
    ↓
Step 2: CODE GENERATION (LLM call, Sonnet-class, ~5s)
    Input: {name, description, api_details, template_example}
    Template: contents of an existing simple node (e.g., whois_lookup.py)
    Output: complete Python module source code
    ↓
Step 3: VALIDATION
    - Parse the generated code (compile check)
    - Verify it defines a class with node_type, display_name, category, config_schema, execute()
    - Verify no dangerous imports (os.system, subprocess, eval, exec — wait, we're full trust)
    - Actually: just verify it compiles and has the PipelineNode interface
    ↓
Step 4: HOT REGISTRATION
    - Write to app/pipeline/nodes/auto/{name}.py
    - exec() the module code in a namespace
    - Extract the node class, instantiate, register in NodeRegistry
    ↓
Step 5: RETURN TO IS BRAIN
    - Return {"status": "auto_created", "tool_name": "run_{name}"}
    - Brain can now call the tool immediately in the same research run
    ↓
Step 6: POST-RUN PERSISTENCE
    - If the auto-created node was used and produced findings → keep it
    - Update plugin_request status to "auto_implemented"
    - If it crashed or produced no results → mark "auto_create_failed"
    - Log the generation details for review
```

### Auto Directory

Auto-created nodes live in `app/pipeline/nodes/auto/` with `__init__.py`. This directory is:
- Git-ignored (generated code, not version-controlled)
- Loaded at startup by `NodeRegistry.auto_discover()` scanning the auto/ subdirectory
- Persisted across restarts (files stay on disk)

### LLM Prompts

**Merit Assessment Prompt:**
```
You are evaluating whether a suggested plugin can be automatically implemented.

Plugin: {name}
Description: {description}
Reason: {reason}

Assess:
1. Is there a free/cheap public API for this? (provide URL if yes)
2. Can the data be reliably scraped from a public website?
3. What authentication method is needed? (none / api_key / oauth)
4. What's the expected response format? (JSON / HTML / XML)

Rate achievability:
- HIGH: Free API with documented endpoints
- MEDIUM: Public website with scrapeable structure
- LOW: Paywalled, requires authentication, or no reliable source

Output JSON: {"achievable": "HIGH|MEDIUM|LOW", "api_url": "...", "auth_method": "...", "response_format": "...", "category": "source|enrich", "notes": "..."}
```

**Code Generation Prompt:**
```
Generate a Python pipeline node for info-broker.

TEMPLATE (follow this exact pattern):
{contents of whois_lookup.py}

REQUIREMENTS:
- Node name: {name}
- Description: {description}
- API details: {api_url, auth_method, response_format}
- Class must have: node_type, display_name, category, config_schema, async execute()
- Use httpx for HTTP calls, asyncio.get_running_loop() + run_in_executor for blocking I/O
- Include _REASON constant
- Handle errors gracefully (return error dict, never crash)
- Output dicts must include "source" and "reason" keys

Output ONLY the Python code. No markdown fences. No explanation.
```

### Safety Guardrails

Even with full trust:
- Generated code is **logged** before execution (audit trail)
- A compilation check (`compile()`) catches syntax errors before exec
- Interface check verifies the class has the required PipelineNode attributes
- If the node crashes during execution, the error is caught by the existing `try/except` in the IS brain's tool execution loop — it doesn't propagate
- Auto-created nodes are clearly marked (node_type prefix or metadata) for review

---

## Part 4: Plugin Request DB Cleanup

### One-Time Script

Update the 118 existing plugin_requests based on the analysis:

```sql
-- Reject 40 duplicates/low-value
UPDATE plugin_requests SET status = 'rejected', reviewed_at = now()
WHERE spec->>'name' IN ('bing_search', 'ecosia_search', 'qwant_search', ...);

-- Merge duplicates (keep newest, reject older)
-- For entries like arxiv_search x3, keep the one with the best description

-- Approve 15 high-value for manual implementation
UPDATE plugin_requests SET status = 'approved', reviewed_at = now()
WHERE spec->>'name' IN ('serper_search', 'github_search', 'openalex_search', ...);
```

### Ongoing Dedup Enhancement

Enhance the existing dedup logic in `mcp_server/server.py` and `agent.py`:
- Add **semantic similarity** check: embed the description and compare against existing plugin_requests (not just name matching)
- If similarity > 0.85, merge instead of creating new
- Track `duplicate_of` field pointing to the canonical request

---

## Part 5: Implementation Phases

### Phase A: Multi-Engine Meta-Search (no dependencies)
- Create `multi_search.py` node with DDG + Serper backends
- Register, add to static tools, update strategy pivot patterns

### Phase B: Technique Catalog (no dependencies)
- Create `techniques.py` with initial catalog
- Add `{techniques_section}` to `is_prompt.py`
- Inject formatted catalog into IS brain prompt

### Phase C: DB Cleanup (no dependencies)
- Script to reject/approve/merge existing plugin_requests
- Enhance dedup logic with semantic similarity

### Phase D: Auto-Create Pipeline (depends on A, B)
- Settings toggle in core_settings
- Merit assessment LLM call
- Code generation LLM call
- Hot registration in NodeRegistry
- Post-run persistence logic

---

## New Files

| File | Purpose |
|------|---------|
| `app/pipeline/nodes/multi_search.py` | Multi-engine meta-search node |
| `app/pipeline/techniques.py` | Technique catalog registry |
| `app/pipeline/nodes/auto/__init__.py` | Auto-created nodes directory |
| `app/pipeline/auto_create.py` | LLM-powered node generation pipeline |
| `scripts/cleanup_plugin_requests.py` | One-time DB cleanup script |

## Modified Files

| File | Change |
|------|--------|
| `app/is_prompt.py` | Add `{techniques_section}` placeholder + multi_search to static tools |
| `app/pipeline/nodes/__init__.py` | Register multi_search + auto-discover from auto/ |
| `mcp_server/server.py` | Add auto-create flow to suggest_plugin handler |
| `app/routers/v3/agent.py` | Post-run: persist auto-created nodes on success |
