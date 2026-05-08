# Comprehensive Investigation System — Changelog

**Date:** 2026-05-07
**Scope:** Full investigation pipeline from design specs through implementation
**Stats:** 64 registered nodes | 542 passing tests | 60+ commits

---

## What Was Built

### Design Specs (4 documents)
- `docs/superpowers/specs/2026-05-07-comprehensive-investigation-strategy-design.md` — Selector-centric OSINT investigation with NATO Admiralty classification, self-learning overlays, intelligence fusion layer
- `docs/superpowers/specs/2026-05-07-universal-research-engine-design.md` — 5 research categories (Retrieval/Generation/Prediction/Explanation/Synthesis) with cross-category transitions
- `docs/superpowers/specs/2026-05-07-research-paradigms-reference.md` — 36 research paradigms, 5-category taxonomy, architectural decision record
- `docs/superpowers/specs/2026-05-07-technique-catalog-auto-create-design.md` — Multi-engine meta-search, technique catalog, LLM-powered auto-create pipeline

### Phase 1: Collection Enhancement — 18 New Pipeline Nodes

**OSINT Investigation Nodes (13):**
- `smtp_verifier` — SMTP RCPT TO email existence verification
- `email_enumerator` — Name-based email candidate generation + SMTP verify
- `hibp_lookup` — HaveIBeenPwned breach database check (API + web fallback)
- `reverse_lookup` — Email/phone/username → identity cross-reference
- `username_enumerator` — Cross-platform username existence (9 platforms)
- `phone_osint` — Phone number recon (NumVerify API)
- `messaging_check` — Telegram/WhatsApp/Signal presence
- `pep_sanctions_screen` — PEP/sanctions/watchlist screening [SENTINEL]
- `adverse_media` — Negative news monitoring (fraud/corruption/scandal)
- `exif_extractor` — Image/document metadata extraction (GPS, device, author)
- `document_search` — Google Dorking for PDFs/docs
- `face_search` — Reverse facial recognition (PimEyes API)
- `crypto_tracer` — Blockchain wallet analysis (Etherscan) [SENTINEL]

**Search & Academic Nodes (5):**
- `multi_search` — Multi-engine meta-search (DDG + Serper + Brave + Exa) with consensus ranking
- `serper_search` — Google SERP proxy via Serper API
- `github_search` — GitHub repository/code/user search
- `openalex_search` — Free 250M+ scholarly works (OpenAlex API)
- `semantic_scholar` — Academic graph + citation search (Semantic Scholar API)

### Phase 2: Intelligence Fusion Layer (`app/pipeline/fusion/`)
- `selectors.py` — Regex extraction of emails, phones, domains, usernames from findings
- `classification.py` — NATO Admiralty source ratings (A-F) for 37 tools + STIX confidence
- `writer.py` — Write entities/relationships to KG event store with confidence
- `completeness.py` — 10-domain investigation checklist (CONFIRMED/PARTIAL/NOT_FOUND/NOT_ATTEMPTED)
- `deception.py` — Rule-based deception detection (5 flags: source_echo, copied_content, too_perfect, low_diversity, temporal_anomaly)

### Phase 3: Analysis Enhancement
- Completeness assessment hooked into post-run flow (logs coverage % + gaps)
- Deception detection hooked into post-run flow (flags suspicious findings)

### Phase 4: Self-Learning Strategy Evolution (`app/pipeline/strategies/`)
- `person.py` — Person investigation seed strategy (selector-centric, 10-domain completeness)
- `generation.py` — Generation research strategy (TRIZ, cross-domain, gap-driven)
- `explanation.py` — Explanation strategy (5 Whys, fishbone, systems thinking)
- `prediction.py` — Prediction strategy (signals, trends, scenarios)
- `synthesis.py` — Synthesis strategy (systematic review, multi-framework)
- `orchestrator.py` — Keyword-based query classification into 5 categories
- `compiler.py` — Merges seed strategy + learned DB overlays ([HIGH PRIORITY] / [LOW PRIORITY] annotations)
- `analyzer.py` — Post-run pivot analysis (28 tool mappings, EMA yield tracking, reinforce/prune/discover signals)

### Technique Catalog + Auto-Create
- `app/pipeline/techniques.py` — 11 structured techniques mapping tactics → tool sequences
- `app/pipeline/auto_create.py` — LLM-powered plugin generation (merit assessment → code generation → hot registration)
- Wired into MCP `suggest_plugin` handler for automatic tool creation

### Database Changes
- New table: `investigation_strategy_overlays` — self-learning pivot annotations
- New setting: `auto_create_techniques` — toggle for LLM auto-plugin creation
- Plugin request cleanup: 65 rejected (duplicates), 9 implemented, 10 approved

### Integration Points (all in `app/routers/v3/agent.py`)
Post-run hook order:
1. Insert research_trails
2. Index findings to Qdrant memory
3. Intelligence Fusion (selector extraction + KG write)
4. Completeness + deception assessment
5. Create procedural memory skill
6. Analyze pivot patterns (strategy overlays)
7. Plugin deduplication + auto-create tracking

### IS Brain Prompt Layers (in order)
1. Base system prompt (temporal grounding, query, context)
2. Tools section (64 registered tools)
3. Entity strategy (compiled from seed + overlays)
4. Technique catalog (11 proven tool sequences)
5. Suggested strategies (procedural memory from past runs)
6. Workflow (BOOTSTRAP → PLAN → RECURSE → DELIVER)
7. Output format
