# Agent Collaboration Protocol

**CRITICAL MANDATE:** ALL agents MUST check this document before starting work and update it when claiming or finishing a task. This prevents race conditions and duplicated effort.

## 🚀 Active Work
*(Format: `[Date] - [Agent ID/Name] - [Task Description] - [Target Files]`)*
- [2026-05-06] - [Claude/software-developer] - [Task 5: [REDACTED:high-entropy-base64:20ch:hash=935f9396] — bridge analyzer output to event store (entity_observations, relationship_observations)] - [app/knowledge/writer.py, tests/knowledge/test_writer.py]
- [2026-05-06] - [Claude/software-developer] - [Add context drawers to Go Deeper, Analyze, and Re-Analyze action buttons in ResultsPanel] - [frontend/src/components/results/ActionDrawer.tsx, frontend/src/components/results/ResultsPanel.tsx]
- [2026-05-06] - [Claude/software-developer] - [IS brain error detection pre-filter: _classify_finding() + wire into _parse_output() + tests] - [app/is_brain.py, tests/test_error_filter.py]
- [2026-05-06] - [Claude/software-developer] - [Create 4 pipeline node plugins: clutch_goodfirms, linkedin_profile, apify_mcp, web_search_fetch] - [app/pipeline/nodes/clutch_goodfirms.py, app/pipeline/nodes/linkedin_profile.py, app/pipeline/nodes/apify_mcp.py, app/pipeline/nodes/web_search_fetch.py, app/pipeline/nodes/__init__.py]
## ✅ Recently Completed
*(Format: `[Date] - [Agent ID/Name] - [Task Description] - [PR/Commit if applicable]`)*
- [2026-05-06] - [Claude/software-developer] - [Task 1: Database Schema — Event Store + Observability Tables: 8 migration tables, 25 entity types, 25 relationship types, materializer seed, 6 Pydantic models, 4 tests] - [3048e2d]
- [2026-05-06] - [Claude/software-developer] - [Intelligence Analyzer pipeline node: entity extraction, relationship mapping, synthesis, map-reduce for large datasets — 22 tests, all passing] - [app/pipeline/nodes/analyzer.py, app/pipeline/nodes/__init__.py, tests/pipeline/nodes/test_analyzer.py]
- [2026-05-06] - [Claude/software-developer] - [Frontend plugin health dashboard + streaming tool results UI: NodeHealth settings section, is.tool_result streaming counter in AgentChat, grey out unhealthy nodes in PipelineBuilder] - [frontend/src/api/v3.ts, frontend/src/pages/Settings.tsx, frontend/src/components/agent/AgentChat.tsx, frontend/src/components/pipeline/StepList.tsx, frontend/src/components/pipeline/PipelineBuilder.tsx]
- [2026-05-06] - [Claude/software-developer] - [Create 8 OSINT pipeline node plugins: facebook_pages, twitter_search, opencorporates, instagram_profile, hunter_io, whois_lookup, google_news, shodan_search — 42 tests, all passing]
- [2026-05-06] - [Claude/software-developer] - [Plugin health check system: HealthStatus TypedDict, health_check() on Apify nodes, GET /v3/pipelines/nodes/types/health endpoint, get_healthy_nodes() helper] - [app/pipeline/nodes/base.py, app/pipeline/nodes/apify_actor.py, app/pipeline/nodes/apify_mcp.py, app/pipeline/nodes/linkedin_profile.py, app/routers/v3/pipelines.py, tests/pipeline/nodes/test_health_check.py]
- [2026-04-08] - [Gemini CLI] - [Fix Qdrant AttributeError: 'QdrantClient' object has no attribute 'search' in v1.17+ by migration to `query_points`; updated episodic-memory test suite to match API changes.] - [feat/media-jokes]
- [2026-04-07] - [Claude] - [SQL-injection lint: ruff S608 + AST-based pytest scanner forbidding f-string/.format/%/concatenated SQL in execute calls; two-layer, cannot be silenced via noqa] - [pyproject.toml, test_no_sql_string_formatting.py, SECURITY.md]
- [2026-04-07] - [Claude] - [Supply-chain hardening: adopted uv 0.11.3 + pip-audit; generated uv.lock + hash-pinned requirements.lock; swapped renamed `duckduckgo-search` → `ddgs`; 0 CVEs, 64 security tests passing] - [pyproject.toml, uv.lock, requirements.lock, research_agent.py, security.py]
- [2026-04-07] - [Claude] - [Phases 3/4/5: dynamic few-shot from Postgres, critic agent + retry loop, fine-tuning JSONL exporter, base-vs-finetuned eval harness, fine-tuning docs, 17 new tests] - [research_agent.py, export_dataset.py, evaluate_finetuned.py, docs/fine-tuning.md, test_phases_345.py]
- [2026-04-07] - [Claude] - [Phase 2 finishing touches: --backfill-memory CLI for historical grades + 13-test episodic-memory suite (save/recall/inject/backfill, all Qdrant-mocked)] - [research_agent.py, test_episodic_memory.py]
- [2026-04-07] - [Claude] - [Phase 2: Episodic memory via Qdrant — feedback collection + recall of past mistakes into system prompt] - [research_agent.py]
- [2026-04-07] - [Claude (security)] - [Phase 6: Sanitize untrusted data — SSRF guard, prompt-injection hardening, CSV formula-injection escaping, ingest hardening, security test suite (60 unit + 4 integration)] - [security.py, research_agent.py, ingest.py, export_data.py, generate_emails.py, test_security.py, tasks/todo.md]
- [2026-04-07] - [Gemini CLI] - [Feature: Light Data Export & Personalized Email Generation] - [None]
- [2026-04-07] - [Gemini CLI] - [Feature: Data Export System (JSON, CSV, XLSX)] - [None]
- [2026-04-07] - [Gemini CLI] - [Phase 1 MVP: ReAct Loop for Research Agent] - [None]

## 🔴 BLOCKED / Needs User Input
- 

## 📝 Conventions & Rules
1. Never start a ticket already in `Active Work`.
2. Update this file in the SAME commit as your work.
3. Check `shared/db/src/migrations/` for the highest number and reserve the next number here before creating a migration.
4. Grep for existing routes in a service's `routes/` directory before adding new ones.
5. Run `git show origin/main -- <file>` for key files before writing new code to avoid duplication with merged work.
