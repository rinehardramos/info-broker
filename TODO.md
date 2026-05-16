# info-broker: Implementation TODO

> Last updated: 2026-05-13
> Tiers 1–3 complete. Remaining: Tier 3.6 + Tier 4 backlog.

---

## Tier 3 — Remaining

### 3.6 Session Multi-Turn Investigation Memory
> Arch hint: `build_session_context()` injects prior findings but doesn't track hypothesis graph. Add `investigated_hypotheses` JSONB to `agent_sessions`; update `update_session_after_run` to append hypothesis results.
- [ ] Persist hypothesis outcomes across session turns in `agent_sessions.investigated_hypotheses`
- [ ] Inject prior hypothesis results into session context so brain avoids re-exploring settled branches

---

## Tier 4 — Backlog

### 4.1 Non-Admin User RBAC
> Needs: `is_admin BOOLEAN DEFAULT false` on `ui_users` first, then gate admin-only routes.
- [ ] Add `is_admin` column to `ui_users`
- [ ] Org membership model (admin / analyst / viewer roles)
- [ ] Implement role enforcement in `Depends()` middleware

### 4.2 Plugin Ecosystem
- [ ] Plugin scaffold generator (#47)
- [ ] Plugin request review UI (#46)
- [ ] OSINT marketplace integration nodes (#45)

### 4.3 New Datastore Nodes
- [ ] Shodan network/IP scan node (#44)
- [ ] Dropbox datastore node (#43)
- [ ] Google Drive datastore node (#42)

### 4.4 Metrics / Performance Dashboard
- [ ] Performance Dashboard (latency, branch depth, tool call counts per run)
- [ ] Strategy + Tactic + Technique Summary metrics

### 4.5 Async IS: Temporal Workflow Migration
> Complete Budget Phase 2 enforcement first.
- [ ] Migrate from in-process asyncio to Temporal worker
- [ ] Resumable row/batch checkpointing for large source uploads

---

## Completed

### Tier 1 — all shipped (2026-05-13)
- [x] PlayGen Phase 7 tests
- [x] SDK timeouts in session_service.py
- [x] Prompt injection XML delimiters
- [x] is_brain.py LimitOverrunError + terminate/kill fix
- [x] Pipeline runs reconciliation (startup + sweep)
- [x] Preflight test suite — 100 tests
- [x] Run Budget Phase 1
- [x] Tenant isolation tests — 24 tests
- [x] Tenant isolation enforcement — 9 org_id gaps
- [x] UI fixes (agent_input border, Create All button)

### Tier 2 — all shipped (2026-05-13)
- [x] ACH/PIR media_identification — hypothesis matrix + PIR scoring + disconfirmation gate
- [x] Fast+Thorough Phase A/B/C — merger, parallel exec, frontend badges
- [x] Budget Phase 2 — pre-run reservation gate
- [x] Signed webhook callbacks — HMAC + retry

### Tier 3 — shipped (2026-05-13)
- [x] ach.py real ACH consistency matrix (Heuer ranking)
- [x] pir.py word-boundary keyword matching
- [x] Results tab on Research page (#39)
- [x] Interactive DAG + buttons on nodes (#27)
- [x] PIR dead-end re-hypothesization + 8 structural prompt tests (PR #73)

### Previously completed
- [x] Phases 1–7: auto-marketer agent, PlayGen audio sourcing
- [x] Session-aware chat, ACH/PIR modules, Memory phases 3/4/5
- [x] URE Phase C — 38 domain strategies
- [x] IS brain + IS prompt with log_cycle, hypothesis-first BROADEN, PIR scoring
