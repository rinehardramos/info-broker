# Meta-Investigation Strategies Library — Design Spec

**Date**: 2026-05-10  
**Status**: Implemented  
**Author**: Claude + Rinehard

---

## Problem

The IS brain's investigation strategies were entity-type specific (person, company, etc.) and lacked cross-domain investigative approaches. When a person search yielded low confidence in an assumed locale — e.g., a Filipino name with no Philippine records — the brain had no strategy for widening the search geographically. More broadly, proven investigation methodologies from journalism, law enforcement, intelligence, DFIR, and business intelligence were not available to the brain.

---

## Solution: Generic Meta-Strategy Layer

A new `meta_strategies_section` injection slot in the IS brain prompt, populated by a compiler that selects relevant generic strategies based on query signals. These strategies are **entity-agnostic** and complement the existing entity-specific strategies.

---

## Architecture

```
IS Brain prompt injection order:
  1. meta_strategies_section   ← NEW: generic approaches, always present
  2. entity_strategy           ← existing: entity-type specific
  3. techniques_section        ← existing: tool sequences
  4. strategies_section        ← existing: entity strategy text (DB overlays)
```

### New Files

```
app/pipeline/strategies/meta/
  __init__.py
  compiler.py                  — selects strategies by query signals
  anchoring.py                 — anchor-and-pivot, source hierarchy, passive-first, triangulation
  scope_expansion.py           — net widening, breadth-first, geographic widening, negative space
  financial_trail.py           — follow the money/document, beneficial ownership, gap analysis
  network_analysis.py          — network-before-individual, MO matching, link analysis, interlocks
  temporal_analysis.py         — timeline-first, temporal anchoring, chronolocation, pattern-of-life
  hypothesis_testing.py        — ACH, key assumptions check, elimination, red cell, premortem
  verification.py              — geolocation→ground-truth, CIB detection, Admiralty Code
  business_intelligence.py     — SCIP cycle, job-posting intel, tech stack, financial, supply chain
  platform_social_intel.py     — social graph, identity graph, CIB, engagement network, ad intel

app/pipeline/nodes/
  name_origin_lookup.py        — NEW: Forebears.io + Namsor API → nationality probability
  migration_corridor_lookup.py — NEW: IOM Migration Data Portal → top destination countries
```

---

## Meta-Strategy Taxonomy

Drawn from 5 domains:

| Domain | Key Strategies |
|--------|----------------|
| OSINT/Investigation | Net widening, Anchor-pivot, Breadth-first, Negative space, Passive-first |
| Investigative Journalism (ICIJ, Bellingcat, IRE) | Follow-the-money, Follow-the-document, Timeline-first, Source triangulation, Network-before-individual |
| Law Enforcement (FBI, Interpol) | MO pattern matching, Known-associates expansion, Elimination-first, Geographic profiling, Weakest-link |
| Intelligence (CIA SATs, NSA) | ACH, Red cell, Layered collection, Mosaic aggregation, Pattern-of-life, Key Assumptions Check, I&W, Premortem |
| DFIR/Digital | Artifact correlation, IOC pivot, Pyramid of Pain, Infrastructure pivoting, Behavioral stylometry |
| Bellingcat/OSINT Verification | Geolocation→ground-truth, Chronolocation, Sock puppet detection, Media forensics |
| Business Intelligence (SCIP) | CI lifecycle, Job-posting-as-strategy, Tech stack intel, Beneficial ownership walk, Patent landscape |
| Platform/Social Intelligence | Identity graph construction, CIB detection, Engagement network mapping, Cross-platform correlation |

---

## Compiler Logic

```python
# Always-on (every query):
anchor_and_pivot       # source hierarchy, passive-first, triangulation
hypothesis_testing     # ACH, hypothesis ladder, elimination, red cell

# Query-triggered (by signal count, max 3):
financial_trail        # money/contract/asset/fraud signals
network_analysis       # ring/associates/shell/coordination signals
temporal_analysis      # timeline/when/history/scrubbed signals
osint_verification     # fake/bot/influence-operation/media signals
scope_expansion        # low confidence / not-found / diaspora signals
business_intelligence  # company/market/competitor/funding signals
platform_social_intel  # social-media/followers/platform signals

# Entity-type hints:
scope_expansion        # always added for person investigations
```

---

## Geographic Widening Protocol (Key New Capability)

Triggered when person investigation confidence < 0.5 after 3+ locale-specific calls.

**8-step protocol:**
1. Re-evaluate name origin: `run_name_origin_lookup()` → nationality probability vector
2. Build corridor list: `run_migration_corridor_lookup()` → top-5 destination countries
3. Parallel shallow sweep (top-3 locales): local platforms, LinkedIn dork, corporate registry
4. Diaspora-specific sources: h1bdata.info, London Gazette, DMW/POEA, ICIJ, alumni cross-border
5. Digital shadow triangulation: phone prefix, messaging platform, posting timezone
6. Anchor-pivot (if confidence ≥ 0.6): deep-dive anchor's locale
7. Deep widen (locales 4-5)
8. Reset: hypothesize wrong name-origin, pivot on non-name attributes

**Key corridors encoded:**
- PH → US / UAE/SA/QA/KW / CA / AU / SG/HK / JP / IT
- IN → UAE / SA / US / UK / CA / AU
- VN → US (Orange County, Houston) / JP / AU / KR / DE / FR
- CN → US / HK / SG / CA / AU
- NG → US / UK / CA / ZA

---

## New Nodes

### `name_origin_lookup`
- **API**: Namsor v2 `/diaspora/{first}/{last}` (key via env/DB) + Forebears.io scrape fallback
- **Output**: `likely_origin`, `top_countries[{country, probability}]`, `romanization_artifact`, `diaspora_ambiguous`, `script`
- **When**: Start of every person investigation before any locale-specific calls

### `migration_corridor_lookup`
- **API**: IOM Migration Data Portal (`migrationdataportal.org/api/`) + hardcoded corridor fallback
- **Output**: `origin_country`, `destinations[{destination, migrant_stock, rank, search_tips}]`
- **When**: Step 1 of geographic widening

---

## New Techniques (23 total, was 11)

New techniques added to `app/pipeline/techniques.py`:
- `name_origin_analysis`, `migration_corridor_research`, `geographic_widening`
- `diaspora_record_search`, `cross_border_footprint`
- `financial_trail`, `beneficial_ownership_walk`
- `network_mapping`, `hypothesis_testing_ach`
- `opsec_failure_hunting`, `job_posting_intelligence`
- `coordinated_behavior_detection`

---

## IS Brain MCP Exposure

The full IS brain research loop is now accessible as an MCP tool:

```python
run_intelligent_search(query, max_depth=3, max_branches=12)
```

This calls `POST /v3/agent/research/sync` which runs the complete investigation loop synchronously (280s timeout) and returns the full JSON result (summary, findings, tree, pipeline, gaps).

Previously only individual tool calls were exposed via MCP. Now Claude Code and other MCP clients can invoke the full recursive investigation engine directly.

---

## Research Sources

- Opus 4.6 deep research on geographic widening TTPs (250K token research)
- Opus 4.6 deep research on generic cross-domain meta-strategies
- Opus 4.6 deep research on business intelligence + social/platform intelligence
- Opus 4.6 GitHub + academic paper research (SpiderFoot, Maigret, Splink, HippoRAG, etc.)
- Web research: IOM Migration Data Portal API, Namsor API, SCIP, ACH (Heuer), Bellingcat toolkit

---

## Future Roadmap (from GitHub/academic research)

High-priority integrations identified:
1. **Splink (Fellegi-Sunter PRL)** — replace fusion-layer identity dedup with principled probabilistic linkage
2. **HippoRAG-style PPR** — Personalized PageRank over investigation graph for next-pivot suggestions
3. **Maigret per-site `data.json` schema** — adopt for social-platform nodes (3000+ sites)
4. **Leiden+CPM community detection** — surface coordination/identity clusters
5. **TRAM (MITRE ATT&CK)** — auto-tag findings with controlled TTP vocabulary
