# PIR-Bounded INVESTIGATE Cycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the linear STEP 1–7 IS brain pipeline with a PIR-bounded recursive INVESTIGATE cycle — hypothesis-first BROADEN, per-hypothesis searches, penalty-based ranking — and remove the multi-branch Python pre-fetch infrastructure.

**Architecture:** The IS brain generates ≥3 competing hypotheses before any search (cold-start ACH), runs ≥1 dedicated search per hypothesis in BROADEN, then ranks by PIR signal coverage. The orchestration-layer multi-branch pre-fetch (TMDB branches, constraint_filter hard-block) is deleted — corpus diversity is now the brain's responsibility, not the orchestrator's.

**Tech Stack:** Python (FastAPI, asyncio), Claude Code subprocess, TypeScript/React (frontend flow graph — already updated in session)

---

## File Map

| File | Action | What changes |
|---|---|---|
| `app/pipeline/retrieval/` | **DELETE** entire package | multi_branch.py, tmdb_client.py, branches/ |
| `app/pipeline/fusion/constraint_filter.py` | **DELETE** | hard gender-block; imports from retrieval package |
| `app/routers/v3/agent.py` | **Modify** | remove prefetch block + constraint_filter block + prefetched_evidence param |
| `app/is_brain.py` | **Modify** | remove prefetched_evidence param and evidence_block wiring |
| `app/is_prompt.py` | **Modify** | remove `{prefetched_evidence}` slot + PRE-RETRIEVED block; update BROADEN to hypothesis-first |
| `app/pipeline/strategies/media_identification.py` | **Modify** | remove pre-fetch NOTE; add PIR template + hypothesis table |
| `app/pipeline/strategies/person.py` | **Modify** | add PIR template + hypothesis table |
| `app/pipeline/strategies/company.py` | **Modify** | add PIR template + hypothesis table |

---

## Task 1: Delete multi-branch retrieval package and constraint_filter

**Files:**
- Delete: `app/pipeline/retrieval/` (entire directory)
- Delete: `app/pipeline/fusion/constraint_filter.py`

- [ ] **Step 1: Delete the retrieval package**

```bash
rm -rf /Users/rinehardramos/Projects/info-broker/app/pipeline/retrieval
```

- [ ] **Step 2: Delete constraint_filter**

```bash
rm /Users/rinehardramos/Projects/info-broker/app/pipeline/fusion/constraint_filter.py
```

- [ ] **Step 3: Verify no other files import from retrieval or constraint_filter**

```bash
grep -rn "from app.pipeline.retrieval\|from app.pipeline.fusion.constraint_filter\|import constraint_filter\|import multi_branch\|import tmdb_client" /Users/rinehardramos/Projects/info-broker/app --include="*.py"
```

Expected: only `agent.py` references (will be cleaned in Task 2). No other files.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: delete multi-branch retrieval package and constraint_filter"
```

---

## Task 2: Clean up agent.py — remove prefetch and constraint_filter blocks

**Files:**
- Modify: `app/routers/v3/agent.py`

The file has two blocks to remove:

**Block A** (around line 448–459) — multi-branch pre-fetch:
```python
        # Multi-branch pre-fetch for media_identification only (non-fatal if fails)
        prefetched_evidence = None
        if research_category == "media_identification":
            try:
                from app.pipeline.retrieval.multi_branch import prefetch_branches
                _signals = _parse_identification_signals(query)
                prefetched_evidence = await prefetch_branches(_signals, research_category)
                log.info("IS Brain: pre-fetched branches balanced=%s branches=%s",
                         prefetched_evidence.balanced,
                         list(prefetched_evidence.branches.keys()))
            except Exception as _pf_exc:
                log.warning("prefetch_branches failed (non-fatal): %s", _pf_exc)
```

**Block B** (around line 597–621) — constraint_filter call:
```python
            # Hard lead-gender filter — blocks Spider-Noir before confirmation card
            if should_confirm and research_category == "media_identification":
                try:
                    from app.pipeline.fusion.constraint_filter import (
                        passes_lead_constraint, extract_primary_signal,
                    )
                    _cf_signals = _parse_identification_signals(query)
                    _cf_primary = extract_primary_signal(_cf_signals.get("primary", ""))
                    _cf_tmdb_id: int | None = None
                    try:
                        _cf_tmdb_id = int(top_finding.get("tmdb_id") or 0) or None
                    except (ValueError, TypeError):
                        pass
                    _cf_result = await passes_lead_constraint(
                        candidate_title=candidate_name,
                        candidate_tmdb_id=_cf_tmdb_id,
                        candidate_type=result.get("entity_type", "tv"),
                        primary_signal=_cf_primary,
                    )
                    if not _cf_result.passed:
                        log.info("Constraint filter BLOCKED %r: %s",
                                 candidate_name, _cf_result.reason)
                        should_confirm = False
                except Exception as _cf_exc:
                    log.warning("constraint_filter failed (non-fatal): %s", _cf_exc)
```

Also remove the `prefetched_evidence=prefetched_evidence,` line from the `run_research(...)` call (around line 566).

- [ ] **Step 1: Remove Block A (prefetch block)**

Delete the entire `# Multi-branch pre-fetch for media_identification only` block. The variable `prefetched_evidence = None` and all lines through the `except` are removed. After removal, `entity_strategy` assignment flows directly into `# Load technique catalog`.

- [ ] **Step 2: Remove Block B (constraint_filter block)**

Delete the entire `# Hard lead-gender filter` block (the `if should_confirm and research_category == "media_identification":` block with its try/except). After removal, `if should_confirm:` follows directly after `rejection_count < 2` assignment.

- [ ] **Step 3: Remove prefetched_evidence from run_research call**

Find:
```python
            prefetched_evidence=prefetched_evidence,
```
Delete that line. The `run_research(...)` call no longer passes `prefetched_evidence`.

- [ ] **Step 4: Verify agent.py has no remaining references to retrieval or constraint_filter**

```bash
grep -n "prefetch\|constraint_filter\|BranchEvidence\|retrieval" /Users/rinehardramos/Projects/info-broker/app/routers/v3/agent.py
```

Expected: zero matches.

- [ ] **Step 5: Commit**

```bash
git add app/routers/v3/agent.py
git commit -m "feat: remove prefetch_branches and constraint_filter from agent orchestration"
```

---

## Task 3: Clean up is_brain.py — remove prefetched_evidence param

**Files:**
- Modify: `app/is_brain.py`

The `run_research` function accepts `prefetched_evidence=None` and wires it into `build_prompt`. Both references must be removed.

- [ ] **Step 1: Find the param and wiring**

```bash
grep -n "prefetched_evidence" /Users/rinehardramos/Projects/info-broker/app/is_brain.py
```

Expected: lines with `prefetched_evidence=None,` param, `BranchEvidence` import, and `evidence_block` wiring.

- [ ] **Step 2: Remove param, import, and evidence_block**

Find and remove:
- The `prefetched_evidence=None,` parameter from `run_research`'s signature
- Any `from app.pipeline.retrieval...` import
- The `evidence_block = prefetched_evidence.to_prompt_block() if isinstance(...) else ""`  line
- The `prefetched_evidence=evidence_block,` argument in the `build_prompt(...)` call

- [ ] **Step 3: Remove prefetched_evidence param from build_prompt**

Find the `build_prompt` function and remove `prefetched_evidence: str = ""` from its signature and remove its use in the format string.

- [ ] **Step 4: Verify**

```bash
grep -n "prefetched_evidence\|BranchEvidence" /Users/rinehardramos/Projects/info-broker/app/is_brain.py
```

Expected: zero matches.

- [ ] **Step 5: Commit**

```bash
git add app/is_brain.py
git commit -m "feat: remove prefetched_evidence from is_brain run_research"
```

---

## Task 4: Update is_prompt.py — hypothesis-first BROADEN

**Files:**
- Modify: `app/is_prompt.py`

Two changes:

**Change A**: Remove `{prefetched_evidence}` slot (line 35) and the PRE-RETRIEVED EVIDENCE block in BROADEN.

**Change B**: Replace the fixed signal-order search instructions in BROADEN with hypothesis-first rules.

- [ ] **Step 1: Remove {prefetched_evidence} slot**

Find line 35:
```python
{prefetched_evidence}
```
Delete this line entirely.

- [ ] **Step 2: Remove PRE-RETRIEVED EVIDENCE block from BROADEN**

Find and delete:
```
**When PRE-RETRIEVED EVIDENCE is present** (injected above the workflow):
Do NOT re-search that corpus. Work from it directly.
YOU MUST produce >= 1 candidate from each non-empty branch before ranking.
State "no viable candidate" for any branch you cannot satisfy.
```

- [ ] **Step 3: Replace fixed signal-order search instructions with hypothesis-first rules**

Find the current BROADEN search order block:
```
When the query provides labeled signals (PRIMARY / SUPPORTING / CONTEXT), search in this order:
1. PRIMARY + CONTEXT — identifies candidates where the subject matches within the franchise/domain
2. PRIMARY + SUPPORTING — identifies candidates where both the subject and scene details co-occur
3. CONTEXT alone with any temporal or type constraints present in the query — surfaces the full candidate space within that domain so nothing is missed
4. Call get_past_research to check verified prior findings on this topic

When signals are NOT labeled (unstructured query):
1. Search the most specific descriptive element of the query
2. Search the next most identifying element
3. Search combined signals or composite query
4. Call get_past_research

If you have fewer than 3 live search results, you CANNOT rank hypotheses. Run more searches.
```

Replace with:
```
**HYPOTHESIS-FIRST BROADEN — minimum searches = number of hypotheses declared in log_cycle (≥3):**

For each hypothesis declared in log_cycle, run ≥1 dedicated search derived from that hypothesis.
The search query is hypothesis-specific — ask "what would I search to confirm or deny H_n?" not "what combination of signals do I search?".

H1 search: what confirms the most obvious interpretation?
H2 search: what confirms the actor-career / alternate-geography interpretation?
H3 search: what confirms the genre-blind / franchise-dropped interpretation?
H_last search: what confirms the unconventional interpretation (ad, alias, migration, shell entity)?

Also call get_past_research(query) — prior research may have already found a verified answer.

You CANNOT rank hypotheses before all hypothesis searches complete. This is the hard gate.
```

- [ ] **Step 4: Update AFTER BROADEN ranking rule**

Find:
```
**AFTER BROADEN — rank hypotheses by PRIMARY signal coverage first:**
A candidate that satisfies PRIMARY in the lead role outranks one that satisfies SUPPORTING more strongly.
The hypothesis that explains MORE labeled signals wins — with PRIMARY weighted above SUPPORTING above CONTEXT.

ANTI-PATTERN: ranking a candidate because it matches CONTEXT + SUPPORTING strongly while only weakly matching PRIMARY (e.g. franchise + weapon match, but wrong lead gender/role). Certainty comes from PRIMARY coverage, not peripheral signal density.
```

Replace with:
```
**AFTER BROADEN — rank by fewest signal inconsistencies (penalty-based, not elimination):**

Score each hypothesis against the PIR criteria declared in log_cycle:
- PRIMARY signal mismatch: heavy penalty (candidate scores low, still appears in results)
- SUPPORTING signal mismatch: moderate penalty
- CONTEXT signal mismatch: light penalty (CONTEXT is often loose or misleading)
- Medium-type mismatch (ad vs. show, from PreFlight): heavy penalty when medium is known
- Recency mismatch: moderate penalty for candidates outside the stated time window

No candidate is eliminated from the result set — every hypothesis scores at its earned confidence.
The top-ranked hypothesis proceeds to RECURSE. Low-scoring hypotheses are reported as considered alternatives.

ANTI-PATTERN: ranking a candidate high because it matches CONTEXT + SUPPORTING while mismatching PRIMARY. PRIMARY mismatch is the heaviest penalty — a franchise + weapon match with wrong lead gender/medium scores below a partial match that satisfies PRIMARY.
```

- [ ] **Step 5: Verify {prefetched_evidence} is gone and BROADEN reads correctly**

```bash
grep -n "prefetched_evidence\|PRE-RETRIEVED\|signal order\|labeled signals" /Users/rinehardramos/Projects/info-broker/app/is_prompt.py
```

Expected: zero matches for all four patterns.

- [ ] **Step 6: Commit**

```bash
git add app/is_prompt.py
git commit -m "feat: hypothesis-first BROADEN — min searches = hypothesis count, penalty-based ranking"
```

---

## Task 5: Update media_identification.py strategy

**Files:**
- Modify: `app/pipeline/strategies/media_identification.py`

- [ ] **Step 1: Remove pre-fetch NOTE and add PIR + hypothesis template**

Replace the entire STRATEGY string with:

```python
STRATEGY = """
=== MEDIA IDENTIFICATION STRATEGY ===

goal: Identify unknown show/movie/media clip/advertisement from partial descriptions.
execution_model: log_cycle(PIR + hypotheses) → BROADEN(≥1 search/hypothesis) → RANK → RECURSE → DELIVER

--- PIR TEMPLATE ---

PIR: What show, film, or advertisement does the user's description refer to?
MANDATORY: Content type matches user-described medium (show vs. ad vs. film) | Subject or lead matches user's PRIMARY descriptor
SUPPORTING: Franchise or IP connection present | Release year in stated time window | Platform identified
REJECT IF: Multiple MANDATORY criteria fail and no hypothesis scores above 20%

--- HYPOTHESIS TABLE ---

H1 (franchise-literal): A show or film IN the stated franchise/IP universe
  search: "[franchise] new series [year]" | run_tmdb_search("[franchise] [year]")

H2 (actor-career): An actress or actor FROM the franchise appears in a DIFFERENT new project
  search: "[franchise] actress new series [year]" | "[actor name] 2025 project"
  Note: "girl in spiderman" = Zendaya, not Spider-Noir. Search the actress's filmography.

H3 (genre-blind): PRIMARY signal + SUPPORTING signal only — CONTEXT/franchise dropped entirely
  search: "[primary descriptor] [supporting detail] new series [year]"
  Example: "girl shotgun 2025 series" — no spider-man in the query

H_last (advertisement/campaign): The content is NOT a show — it's a brand ad or streaming platform promo
  search: "[franchise or actor] advertisement 2025" | "[actor] [brand] campaign"
  Trigger: PreFlight confirms "YouTube" or "ad"

--- SCORING NOTES ---

Medium-type signal (from PreFlight "YouTube" / "advertisement"):
  - Content confirmed as ad → candidates that are shows receive heavy penalty
  - H_last (advertisement) score boosted when medium=ad confirmed

CONTEXT signal ("spiderman") is often loose — an actress FROM the franchise in a DIFFERENT project
satisfies context as strongly as a show IN the franchise. Do not over-weight CONTEXT.

tools: run_tmdb_search | run_web_search | run_google_news | run_web_crawl
"""
```

- [ ] **Step 2: Commit**

```bash
git add app/pipeline/strategies/media_identification.py
git commit -m "feat: media_identification strategy — PIR template + hypothesis table"
```

---

## Task 6: Update person.py strategy

**Files:**
- Modify: `app/pipeline/strategies/person.py`

- [ ] **Step 1: Add PIR template and hypothesis table at the top of STRATEGY**

After the `=== PERSON INVESTIGATION STRATEGY ===` header line, insert:

```
--- PIR TEMPLATE ---

PIR: Who is this person, where do they live/work, and what is their current role?
MANDATORY: At least one verified record (employment, registration, social, government) in any jurisdiction
SUPPORTING: Record corroborated by a second independent source | Timeline consistent with known facts
REJECT IF: Subject confirmed active in a jurisdiction that contradicts all H1–H3 findings

--- HYPOTHESIS TABLE ---

H1 (obvious locale): Person is based in their most obvious geography (PH if Filipino name, etc.)
  search: "[full name] [obvious locale]" | run_ph_sec_dti | run_apollo_search

H2 (migration / diaspora): Person has relocated — search popular migration destinations
  For Filipino subjects: Italy, UAE, Canada, UK, Australia, US, Singapore
  search: "[full name] [Italy/UAE/Canada/...]" | "[full name] overseas Filipino worker"

H3 (alias / name variant): Person uses a different name spelling, nickname, or married name
  search: run_ph_name_variants first | "[nickname] [surname]" | "[maiden name] [surname]"

H_last (no public trace): Person is a private individual with minimal online presence
  search: "[full name] site:linkedin.com" | "[full name] [employer if known]"
  If dead end: note absence explicitly — "no records found in [jurisdictions searched]"

```

- [ ] **Step 2: Commit**

```bash
git add app/pipeline/strategies/person.py
git commit -m "feat: person strategy — PIR template + hypothesis table (locale/migration/alias)"
```

---

## Task 7: Update company.py strategy

**Files:**
- Modify: `app/pipeline/strategies/company.py`

- [ ] **Step 1: Add PIR template and hypothesis table**

After the `=== COMPANY INVESTIGATION STRATEGY ===` header line, insert:

```
--- PIR TEMPLATE ---

PIR: What is this company's legal identity, jurisdiction, ownership, and current operational status?
MANDATORY: Legal entity record in at least one jurisdiction | Active or dissolved status confirmed
SUPPORTING: Ownership chain identified | Key personnel verified | Products/services confirmed
REJECT IF: Entity cannot be found in any jurisdiction after searching primary + alternate registries

--- HYPOTHESIS TABLE ---

H1 (primary jurisdiction): Company is registered in its most obvious jurisdiction
  search: run_opencorporates("[company name]") | run_ph_sec_dti | run_apollo_search

H2 (parent / subsidiary): The named entity is a subsidiary — the real answer is the parent
  search: "[company name] parent company" | "[company name] acquired by" | run_opencorporates(parent search)

H3 (entity lineage — renamed or dissolved): Company dissolved and re-registered under a new name
  search: run_entity_lineage first | "[old name] renamed" | "[old name] successor"
  This is a common PH fraud pattern — always run entity lineage for PH subjects.

H_last (foreign subsidiary / shell): Entity is a holding company or shell in a different jurisdiction
  search: "[company name] offshore" | "[company name] BVI/Cayman/Singapore" | run_opencorporates(intl)

```

- [ ] **Step 2: Commit**

```bash
git add app/pipeline/strategies/company.py
git commit -m "feat: company strategy — PIR template + hypothesis table (jurisdiction/parent/lineage/shell)"
```

---

## Task 8: Fix flow graph node text truncation

**Files:**
- Modify: `frontend/src/components/results/ResearchFlow.tsx`

The current node renderer truncates text with `...` (e.g. `node.pir?.slice(0, 30) + '...'`). Users cannot read truncated text in the graph. Replace truncation with full text in a multi-line SVG `<text>` or use `<title>` (SVG tooltip) so hovering shows the full text.

The fix: for PIR and Hypothesis nodes, add a `<title>` element inside the `<g>` so hovering shows full text; also increase the node display to show more characters by using word-wrap via `<foreignObject>` or by breaking the text into two `<text>` lines.

- [ ] **Step 1: Find all `.slice(0, N)` truncations in FlowGraph**

```bash
grep -n "slice(0," /Users/rinehardramos/Projects/info-broker/frontend/src/components/results/ResearchFlow.tsx
```

- [ ] **Step 2: Add SVG <title> tooltip to PIR nodes**

For each PIR node `<g>`, add before the `<rect>`:
```tsx
<title>{node.pir ?? ''}</title>
```

- [ ] **Step 3: Add SVG <title> tooltip to hypothesis nodes**

For each hypothesis node `<g>`, add:
```tsx
<title>{node.hypothesisText ?? ''}</title>
```

- [ ] **Step 4: Add SVG <title> tooltip to tool call nodes**

For each tool node `<g>`, add:
```tsx
<title>{node.tool}{node.resultPreview ? ` — ${node.resultPreview}` : ''}</title>
```

- [ ] **Step 5: For PIR nodes, display text without truncation using two SVG text lines**

Replace the single truncated `<text>` with two lines that break at word boundaries. Use the node width `pirW` to calculate character limit (approximately `Math.floor(pirW / (fontSize * 0.55))` chars per line):

```tsx
const pirFull = node.pir ?? ''
const charsPerLine = Math.floor(pirW / (fontSize * 0.6))
const line1 = pirFull.slice(0, charsPerLine)
const line2 = pirFull.slice(charsPerLine, charsPerLine * 2)
// then render two <text> elements at y * 0.5 and y * 0.75
```

- [ ] **Step 6: Verify TypeScript compiles**

```bash
cd /Users/rinehardramos/Projects/info-broker/frontend && npx tsc --noEmit
```

Expected: no errors in ResearchFlow.tsx.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/results/ResearchFlow.tsx
git commit -m "fix(flow-graph): add SVG title tooltips and multi-line text for PIR/hypothesis nodes"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task that covers it |
|---|---|
| Delete `app/pipeline/retrieval/` | Task 1 |
| Delete `app/pipeline/fusion/constraint_filter.py` | Task 1 |
| Remove prefetch from `agent.py` | Task 2 |
| Remove constraint_filter block from `agent.py` | Task 2 |
| Remove `prefetched_evidence` from `is_brain.py` | Task 3 |
| Remove `{prefetched_evidence}` from `is_prompt.py` | Task 4 |
| Remove PRE-RETRIEVED EVIDENCE block | Task 4 |
| Hypothesis-first BROADEN (≥1 search/hypothesis) | Task 4 |
| Penalty-based ranking (not elimination) | Task 4 |
| media_identification PIR + hypothesis table | Task 5 |
| person PIR + hypothesis table | Task 6 |
| company PIR + hypothesis table | Task 7 |
| Flow graph text not truncated | Task 8 |

**Placeholder scan:** No TBDs. All steps have exact file paths, exact code, or exact commands.

**Type consistency:** `prefetched_evidence` removed consistently from is_brain.py (Task 3) and is_prompt.py (Task 4). `run_research` call in agent.py no longer passes this param (Task 2). Consistent across all three.
