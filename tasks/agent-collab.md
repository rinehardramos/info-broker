# Agent Collaboration Protocol

**CRITICAL MANDATE:** ALL agents MUST check this document before starting work and update it when claiming or finishing a task. This prevents race conditions and duplicated effort.

## 🚀 Active Work
*(Format: `[Date] - [Agent ID/Name] - [Task Description] - [Target Files]`)*
-

## ✅ Recently Completed
*(Format: `[Date] - [Agent ID/Name] - [Task Description] - [PR/Commit if applicable]`)*
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
