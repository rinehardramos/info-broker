# Strategy Scorecard + Docker Tool Nodes — Design Spec

**Date:** 2026-05-09
**Status:** Draft
**Depends on:** Investigation strategy system (implemented), technique catalog, self-learning overlays

## Problem Statement

After each IS brain research run, there is no visibility into WHICH strategies, tactics, and techniques were used, how effective each was, or how the user can influence future behavior. The existing feedback system only scores individual findings (thumbs up/down) — it doesn't score the investigation approach itself.

Additionally, techniques are currently limited to API-based pipeline nodes. Real OSINT investigation requires offline tools (nmap, hashcat, exiftool binary, theHarvester, etc.) that must run as sandboxed processes.

## Architecture

### Three Components

**1. Strategy Decomposition Engine** — Backend module that decomposes each research trail into a structured scorecard with three levels (strategy → tactics → techniques), auto-grades each level, and persists the scorecard.

**2. Investigation Breakdown UI** — Collapsible inline section in the Agent chat results showing the strategy tree with A-F letter grades. Users can override auto-grades. Grades feed back into the self-learning overlay system.

**3. Docker Tool Node Framework** — Extension to pipeline nodes that enables binary/executable tools to run inside Docker containers, exposing the same `async execute()` interface as API-based nodes.

---

## Part 1: Strategy Decomposition Engine

### Module: `app/pipeline/fusion/scorecard.py`

After each IS brain run completes, the scorecard engine:

1. **Reads the research trail** (branches, tools_used, findings_count, status per branch)
2. **Groups tool calls into tactics** using `PIVOT_TOOL_MAP` from the strategy analyzer
3. **Auto-grades each level** based on yield and effectiveness metrics
4. **Persists the scorecard** in `research_trails.scorecard` JSONB column

### Auto-Grading Algorithm

**Technique (individual tool call):**

| Grade | Criteria |
|-------|----------|
| A | Produced 3+ findings with high confidence |
| B | Produced 1-2 findings |
| C | Produced 0 findings but no error (clean negative) |
| D | Produced 0 findings with warning/timeout |
| E | Produced error but recoverable |
| F | Crashed, blocked, or misconfigured |

**Tactic (group of tool calls for a pivot pattern):**

| Grade | Criteria |
|-------|----------|
| A | yield_rate >= 0.7 AND at least 1 technique graded A |
| B | yield_rate >= 0.4 OR at least 2 techniques graded B+ |
| C | yield_rate >= 0.2 OR at least 1 technique produced findings |
| D | yield_rate > 0 but all findings low confidence |
| E | yield_rate = 0, all techniques graded D or lower |
| F | All techniques failed (E or F) |

**Strategy (overall investigation):**

| Grade | Criteria |
|-------|----------|
| A | 80%+ completeness, 3+ tactics graded B+, no F tactics |
| B | 60%+ completeness, 2+ tactics graded B+ |
| C | 40%+ completeness, at least 1 tactic graded B+ |
| D | 20%+ completeness, at least 1 finding |
| E | <20% completeness, few findings |
| F | 0 findings or strategy not loaded |

### Scorecard Data Model

```python
@dataclass
class TechniqueScore:
    tool: str               # "run_email_enumerator"
    result_count: int       # findings produced
    error: str | None       # error message if failed
    duration_ms: int        # execution time
    auto_grade: str         # A-F
    user_grade: str | None  # A-F from user, None if not graded

@dataclass
class TacticScore:
    name: str               # "email_discovery"
    selector_type: str      # "full_name" or "email"
    yield_rate: float       # findings / tool_calls
    auto_grade: str         # A-F
    user_grade: str | None
    techniques: list[TechniqueScore]

@dataclass
class StrategyScore:
    name: str               # "person"
    completeness_pct: float # from completeness assessment
    auto_grade: str         # A-F
    user_grade: str | None
    tactics: list[TacticScore]
    pir_coverage: dict | None  # from PIR decomposition
```

### Storage

Add `scorecard` JSONB column to `research_trails` table:
```sql
ALTER TABLE research_trails ADD COLUMN IF NOT EXISTS scorecard JSONB;
```

The scorecard is written during the post-run analysis hook, after completeness and PIR assessment.

### Functions

```python
def build_scorecard(trail: dict, findings: list[dict], completeness: dict, entity_type: str) -> dict:
    """Build the full strategy → tactic → technique scorecard from a research trail."""

def auto_grade_technique(tool: str, result_count: int, error: str | None) -> str:
    """Grade a single tool call A-F."""

def auto_grade_tactic(techniques: list[dict]) -> str:
    """Grade a tactic group based on its technique grades and yield."""

def auto_grade_strategy(tactics: list[dict], completeness_pct: float) -> str:
    """Grade the overall strategy based on tactic grades and coverage."""
```

---

## Part 2: Investigation Breakdown UI

### Layout: Collapsible Inline Section

Appears in the Agent chat results panel, below the findings list, as a collapsible "Investigation Breakdown" section.

```
▼ Investigation Breakdown                    [B]
┌───────────────────────────────────────────────┐
│ Strategy: Person Investigation          [B]   │
│ Coverage: 60% (6/10 domains)                  │
│ PIR: Identity ✓  Professional ✓  Risk ✓       │
│                                               │
│ ├─ Email Discovery                      [C]   │
│ │  ├ run_email_enumerator    3 found    [B]   │
│ │  ├ run_smtp_verifier       2 verified [A]   │
│ │  └ run_hibp_lookup         1 breach   [A]   │
│ │                                             │
│ ├─ Social Media Mapping                [D]   │
│ │  ├ run_instagram_profile   error     [F]   │
│ │  └ run_ddg_search (fb)     0 found   [D]   │
│ │                                             │
│ ├─ Professional Profile               [C]   │
│ │  ├ run_linkedin_lookup     error     [F]   │
│ │  └ run_apollo_search       1 found   [B]   │
│ │                                             │
│ └─ Neg Screening [SENTINEL]            [A]   │
│    ├ run_pep_sanctions_screen  clean   [A]   │
│    └ run_adverse_media         clean   [A]   │
└───────────────────────────────────────────────┘
```

### Grade Interaction

Each grade badge (e.g., `[B]`) is clickable. Clicking opens a dropdown with A-F options. Selecting a grade:
1. Highlights the badge with the new grade color
2. Sends `POST /v3/research-trails/{run_id}/scorecard/grade` with body `{level, name, grade}`
3. Backend updates the scorecard + triggers overlay update

### Grade Colors

| Grade | Color | Meaning |
|-------|-------|---------|
| A | Green (#22c55e) | Excellent — reinforce |
| B | Light green (#86efac) | Good — mild reinforce |
| C | Yellow (#facc15) | Adequate — neutral |
| D | Orange (#fb923c) | Below average — mild prune |
| E | Red (#f87171) | Poor — prune |
| F | Dark red (#dc2626) | Failed — prune + flag |

### Frontend Components

**New:** `InvestigationBreakdown.tsx` — renders the scorecard tree
**New:** `GradeBadge.tsx` — clickable A-F badge with color + dropdown
**Modify:** `ResultsPanel.tsx` — add the collapsible section after findings

### API Endpoints

**GET** `/v3/research-trails/{run_id}/scorecard`
- Returns the scorecard JSON for a run

**POST** `/v3/research-trails/{run_id}/scorecard/grade`
- Body: `{"level": "strategy|tactic|technique", "name": "email_discovery", "tool": "run_email_enumerator", "grade": "A"}`
- Updates the scorecard + triggers overlay feedback

---

## Part 3: Feedback Loop — Grade → Overlay → Future Strategy

### Grade-to-Overlay Mapping

When a user grades a tactic or technique:

| User Grade | Overlay Action | Effect on Future Runs |
|-----------|---------------|----------------------|
| A | reinforce (confidence=0.95) | `[HIGH PRIORITY - user rated A]` annotation |
| B | reinforce (confidence=0.75) | `[HIGH PRIORITY]` annotation |
| C | neutral (no change) | No annotation |
| D | prune (confidence=0.6) | `[LOW PRIORITY - user rated D]` annotation |
| E | prune (confidence=0.8) | `[LOW PRIORITY]` annotation |
| F | prune (confidence=0.95) + flag | `[LOW PRIORITY - FLAGGED]` + logged for review |

### Implementation

When `POST /v3/research-trails/{run_id}/scorecard/grade` is received:

1. Update `research_trails.scorecard` with the user grade
2. Determine overlay action from grade
3. Call `_upsert_overlay()` from `app/pipeline/strategies/analyzer.py` with:
   - `entity_type` from the run
   - `selector_type` from the tactic
   - `pivot_pattern` from the tool mapping
   - `overlay_type` = reinforce or prune
   - `yield_rate` adjusted by user grade
4. Update `research_skills.quality_score` if applicable

### Integration with Existing Systems

- **Strategy Compiler:** Already reads overlays and annotates pivot patterns with `[HIGH PRIORITY]` / `[LOW PRIORITY]`. User grades flow into the same overlay table.
- **Procedural Memory:** User grades contribute to `quality_score` on `research_skills`. High strategy grades boost skill quality; low grades reduce it.
- **Technique Catalog:** Techniques with consistent F grades get automatically flagged in the catalog with `[UNRELIABLE]` annotation.

---

## Part 4: Docker Tool Node Framework

### Overview

A new base class `DockerToolNode` enables pipeline nodes that execute binaries inside Docker containers. Same interface as API-based nodes (`async execute() -> list[dict]`) but the implementation spawns a container.

### Base Class

```python
class DockerToolNode:
    """Pipeline node that runs a tool inside a Docker container."""
    
    node_type: str
    display_name: str
    category: str = "enrich"
    config_schema: dict
    
    # Docker-specific config
    docker_image: str       # "info-broker/nmap:latest"
    docker_command: str     # "nmap -sV {target}"
    output_parser: str      # "json" | "text" | "xml"
    timeout_seconds: int    # Container timeout
    
    async def execute(self, config, inputs, context) -> list[dict]:
        """Builds args from config/inputs, runs container, parses output."""
        args = self._build_args(config, inputs)
        stdout = await self._run_container(args)
        return self._parse_output(stdout)
    
    async def _run_container(self, args: list[str]) -> str:
        """docker run --rm --network=none <image> <args>"""
        # Uses asyncio.subprocess with timeout
        # --network=none for security (no outbound access unless explicitly allowed)
        # --read-only for filesystem safety
        # Resource limits: --memory=512m --cpus=1
```

### Security

- Containers run with `--network=none` by default (no internet). Tools that need network access must explicitly declare it in their node config.
- `--read-only` filesystem. Input data passed via stdin or volume mount.
- Memory limit: 512MB default, configurable per tool.
- CPU limit: 1 core default.
- Timeout: 60 seconds default, configurable.

### Example: EXIF Binary Node

```python
class ExifToolBinaryNode(DockerToolNode):
    node_type = "exiftool_binary"
    display_name = "ExifTool (Binary)"
    docker_image = "info-broker/exiftool:latest"
    docker_command = "exiftool -json {file_path}"
    output_parser = "json"
    timeout_seconds = 30
```

### Dockerfile Pattern

```dockerfile
# Dockerfile.exiftool
FROM alpine:3.19
RUN apk add --no-cache exiftool
ENTRYPOINT ["exiftool"]
```

### Pre-built Tool Images

Initial set of Docker tool images to create:

| Image | Tool | Purpose |
|-------|------|---------|
| `info-broker/exiftool` | ExifTool 12+ | Full EXIF/metadata extraction (replaces Python-only version) |
| `info-broker/nmap` | Nmap 7+ | Network/port scanning for infrastructure recon |
| `info-broker/theharvester` | theHarvester | Email/subdomain discovery from public sources |
| `info-broker/amass` | OWASP Amass | DNS enumeration and network mapping |
| `info-broker/sherlock-bin` | Sherlock | Username enumeration across 400+ sites (faster than HTTP probing) |

---

## Part 5: Implementation Phases

### Phase A: Scorecard Engine (backend, no UI)
- `app/pipeline/fusion/scorecard.py` with build_scorecard + auto-grading
- Add `scorecard` column to research_trails
- Wire into post-run flow in agent.py
- Tests

### Phase B: Scorecard UI (frontend)
- `InvestigationBreakdown.tsx` component
- `GradeBadge.tsx` component
- Integration into ResultsPanel.tsx
- API endpoints for get/update scorecard

### Phase C: Feedback Loop (backend)
- Grade → overlay mapping
- POST endpoint for user grades
- Integration with overlay system + skill quality

### Phase D: Docker Tool Framework (infrastructure)
- `DockerToolNode` base class
- Container lifecycle management
- First tool: exiftool binary
- Dockerfile build pipeline

## New Files

| File | Purpose |
|------|---------|
| `app/pipeline/fusion/scorecard.py` | Strategy decomposition + auto-grading engine |
| `frontend/src/components/results/InvestigationBreakdown.tsx` | Scorecard tree UI |
| `frontend/src/components/results/GradeBadge.tsx` | Clickable A-F grade badge |
| `app/pipeline/nodes/docker_tool.py` | DockerToolNode base class |
| `docker/tools/exiftool/Dockerfile` | ExifTool container image |
| `docker/tools/nmap/Dockerfile` | Nmap container image |

## Modified Files

| File | Change |
|------|--------|
| `app/routers/v3/research_api.py` | Add scorecard GET/POST endpoints |
| `app/routers/v3/agent.py` | Wire scorecard into post-run flow |
| `app/routers/v3/db.py` | Add scorecard column to research_trails |
| `frontend/src/components/results/ResultsPanel.tsx` | Add InvestigationBreakdown section |
| `frontend/src/api/v3.ts` | Add scorecard API calls |
