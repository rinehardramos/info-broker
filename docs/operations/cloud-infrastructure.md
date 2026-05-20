# Cloud Infrastructure Design — Info-Broker

A workload-first design for hosting Info-Broker in the cloud. Optimized for:
- **Bursty, long-running, LLM-heavy** workflows (research runs span minutes to hours)
- **Subprocess-spawning brain** that must persist OAuth state
- **Cross-run memory** that requires durable, queryable storage
- **Small team, lean budget** at the start, with a clear scale-out path
- **PH/SEA primary user base** with latency-sensitive UI interactions

The design is presented in **three tiers** so the project can adopt the right level for current load without over-building. Each tier has a concrete bill of materials, monthly cost estimate, and a trigger for promoting to the next tier.

---

## 1. Workload analysis (what we're actually building for)

Before picking services, characterize the load honestly:

| Component | Pattern | SLO | Cost shape |
|---|---|---|---|
| FastAPI HTTP layer | Mostly idle, burst on dashboard loads | p95 < 300ms PH | Cheap; CPU-light |
| Frontend (React/Vite static) | Pure static; CDN | p95 < 100ms | Near-zero |
| Temporal worker (regular activities) | Steady; long-poll | n/a | Steady RAM/CPU |
| IS Temporal worker (loop brain) | Bursty; **subprocess** per turn; 60–300s per turn × N turns | Throughput-bound, not latency-bound | The dominant variable |
| Postgres | Read-heavy with growing memory tables; small writes per turn | p95 query < 50ms | Grows with run history |
| Qdrant (vectors) | Read-heavy; embedding writes per finding | p95 search < 100ms | Grows with corpus |
| Temporal server | Steady; manages workflow state | n/a | Fixed-ish |
| Object storage (run artifacts, exports) | Write-once, read-rare | n/a | Cheap per-GB |
| Egress | Small (JSON), spikes on exports | n/a | Cheap unless careless |

**Key load-shaping facts:**
1. **The brain subprocess is the dominant cost** — both compute (RAM + CPU + subprocess overhead) and LLM tokens.
2. **Workflow state lives in Temporal**, not in process memory. Workers are restartable; this is a load-bearing property.
3. **The OAuth-based Claude Code subprocess is a quota bottleneck.** One shared subscription = one shared quota. At scale this becomes an API-key migration question, not a compute question.
4. **Cross-run memory grows monotonically.** Postgres + Qdrant retention policies become real decisions at ~100k runs.
5. **No real-time SLO on runs.** Users start a run and come back later. The UI needs to be responsive; the run itself doesn't.

---

## 2. Recommended cloud provider: **GCP** (with honest alternatives)

The recommendation is **GCP**, but the case is not overwhelming — Fly.io or Hetzner+managed-services would also work and would be cheaper at Tier 1.

| Provider | Pros | Cons | Best for |
|---|---|---|---|
| **GCP** | Cloud Run for stateless APIs (scale to 0), GKE Autopilot for stateful workers, Cloud SQL, native Secret Manager + Workload Identity, good observability, PH/Asia regions (Singapore, Jakarta) | Pricing complexity; egress not cheap | Recommended — sweet spot of managed + flexible |
| AWS | Mature, every service exists | Expensive at small scale; IAM is a tax; Fargate ergonomics weaker than Cloud Run | Skip unless org already on AWS |
| Azure | Strong managed Postgres | Smaller AI tooling ecosystem | Skip |
| Fly.io | Simple, cheap, region-flexible, machines API is great for bursty workers | Smaller managed-data ecosystem; ops burden grows at scale | **Best Tier 1 choice** |
| Hetzner + managed services | Cheapest raw compute (~5× cheaper than hyperscalers) | DIY ops; no PH/SG data centers | Cost-optimized, latency-tolerant |
| Railway | Easiest deploy; current familiarity | Pricing scales steeply; less control | Tier 1 only |

**Recommendation summary:**
- **Tier 1 (now)** — Fly.io. Cheap, simple, multi-region trivially. Move when you outgrow it.
- **Tier 2 (growth)** — Migrate to GCP. Cloud Run + GKE Autopilot + Cloud SQL + Secret Manager.
- **Tier 3 (scale)** — Stay on GCP; layer in multi-region read replicas, dedicated Temporal cluster, CDN edge functions.

The migration cost between tiers is real but bounded — containers are containers; Postgres dumps restore.

---

## 3. Tier 1 — "We have <100 users and need to ship"

**Target:** $80–250/month all-in. One-engineer ops burden.

```
                   ┌────────────────────────────────────────┐
                   │  Cloudflare (DNS + WAF + CDN, free)    │
                   └────────────────────────────────────────┘
                                     │
                ┌────────────────────┴────────────────────┐
                │                                          │
        ┌───────▼───────┐                          ┌───────▼───────┐
        │ Fly App: API  │                          │ Fly App: Web  │
        │ 1× shared-cpu │                          │ static-served │
        │ 1GB / 2GB     │                          │ ~$0           │
        └───────┬───────┘                          └───────────────┘
                │
   ┌────────────┼────────────────────┬──────────────────┐
   │            │                    │                  │
┌──▼──────┐ ┌───▼─────────┐  ┌───────▼────────┐  ┌──────▼────────┐
│ Fly App │ │ Fly App     │  │ Neon Postgres  │  │ Qdrant Cloud  │
│ Temporal│ │ IS-Worker   │  │ Free / $19 mo  │  │ Free / $25 mo │
│ server  │ │ 2× cpu/4GB  │  │                │  │               │
│ self-   │ │ + subprocess│  │                │  │               │
│ hosted  │ └─────────────┘  └────────────────┘  └───────────────┘
└─────────┘
                │
        ┌───────▼────────┐
        │ Fly Volumes    │
        │ for Temporal   │
        │ persistence    │
        └────────────────┘

   Secrets: Fly Secrets (built-in)
   Object storage: Cloudflare R2 ($0 egress)
   Observability: Grafana Cloud free tier + Sentry free
   Backups: Neon PITR + nightly pg_dump to R2
```

**Bill of materials (Tier 1)**

| Item | Spec | Monthly |
|---|---|---|
| Fly: API | 1× shared-cpu-1x, 1GB | $5 |
| Fly: IS-worker (brain) | 1× shared-cpu-2x, 4GB | $30 |
| Fly: Temporal server | 1× shared-cpu-1x, 2GB + 10GB volume | $15 |
| Fly: Temporal worker (non-brain) | 1× shared-cpu-1x, 1GB | $5 |
| Frontend (static via Fly or Cloudflare Pages) | — | $0 |
| Neon Postgres | Pro starter w/ branching | $19 |
| Qdrant Cloud | 1GB cluster | $25 |
| Cloudflare R2 | 10GB | ~$0.15 |
| Grafana Cloud | Free tier | $0 |
| Sentry | Developer (free) | $0 |
| **Subtotal (infra)** |  | **~$100** |
| LLM costs (variable) | $5–50 / run × N runs | Variable |

**Trade-offs at Tier 1:**
- Self-hosted Temporal server is the riskiest piece. Acceptable at low concurrency; promote to Temporal Cloud at Tier 2.
- Single brain worker = serialized throughput on long runs. Fine for <100 users with non-realtime SLO; not fine the day someone runs 10 concurrent investigations.
- Neon's free/starter has good PITR; no replica yet. Sufficient.

**Promotion trigger to Tier 2:**
- >50 concurrent active runs, or
- >$50/mo on Temporal Cloud is cheaper than the ops time to manage it, or
- First customer with a compliance ask (SOC2-shaped).

---

## 4. Tier 2 — "We have product-market fit and need to scale"

**Target:** $500–1500/month infra + LLM. Multi-engineer team, basic compliance posture.

```
              ┌──────────────────────────────────────────┐
              │ Cloudflare (DNS + WAF + CDN + R2)        │
              └────────────────┬─────────────────────────┘
                               │
                        ┌──────▼──────┐
                        │  Cloud Run  │  ← stateless API
                        │  FastAPI    │     scale 0..N
                        │  (autoscale)│     1-3 vCPU
                        └──────┬──────┘
                               │
       ┌───────────────────────┼────────────────────────────────┐
       │                       │                                │
┌──────▼─────────┐    ┌────────▼─────────┐         ┌────────────▼──────────┐
│ Cloud SQL      │    │ Qdrant Cloud     │         │ GKE Autopilot         │
│ Postgres 16    │    │ Dedicated cluster│         │  • Temporal worker    │
│ HA primary +   │    │ 2 GB+, HA        │         │  • IS-Brain workers   │
│ read replica   │    │                  │         │     (HPA on queue)    │
│ pgvector,      │    │                  │         │  • MCP server pod     │
│ daily backups  │    │                  │         │  • Scheduled jobs     │
└────────────────┘    └──────────────────┘         └──────────┬────────────┘
                                                              │
                                              ┌───────────────▼────────────┐
                                              │ Temporal Cloud             │
                                              │  ($100–300/mo)             │
                                              └────────────────────────────┘

  Secrets:   GCP Secret Manager  (Claude OAuth, API keys, DB creds)
  Identity:  Workload Identity   (no static creds anywhere)
  Storage:   Cloudflare R2       (run artifacts, exports)
  Obs:       Grafana Cloud Pro  + OpenTelemetry  + Sentry
  CI/CD:     GitHub Actions      → Artifact Registry → Cloud Run + GKE
```

**Why this shape:**
- **Cloud Run for the API** — bursty, mostly idle, scale-to-zero saves real money. p95 well under 300ms with min-instance=1 to dodge cold start.
- **GKE Autopilot for workers** — Cloud Run can't host the subprocess-spawning brain reliably (long execution + container/runtime constraints). Autopilot gives us K8s without node management; HPA scales brain worker pods on Temporal queue depth.
- **Temporal Cloud over self-hosted** — At this tier the ops time to keep self-hosted Temporal healthy exceeds the cost of managed. Use it.
- **Cloud SQL with read replica** — promote read traffic (B/E queries) to the replica; primary handles run writes.
- **Cloudflare R2 (not GCS)** — zero egress fees. Run artifacts (exports, PDFs, dossiers) live here. Saves real money on a per-export workload.
- **Secret Manager + Workload Identity** — no static service-account JSON files. Brain workers fetch the Claude OAuth refresh token at boot.

**Bill of materials (Tier 2)**

| Item | Spec | Monthly |
|---|---|---|
| Cloud Run API | min=1, max=20, 1 vCPU/2GB | $40–120 |
| GKE Autopilot | 4–8 vCPU, 8–16 GB across pods | $250–500 |
| Cloud SQL Postgres | db-custom-2-7680, HA, replica | $200 |
| Qdrant Cloud | Dedicated 2GB | $100 |
| Temporal Cloud | Starter | $100–200 |
| Cloudflare (CDN+R2+WAF) | Pro plan | $25 |
| Secret Manager | Per-secret pricing | $5 |
| Grafana Cloud Pro | 8 traces/sec, 50GB logs | $50–150 |
| Sentry Team | | $26 |
| Artifact Registry | small | $5 |
| Egress (Cloud Run + GKE) | ~50GB | $5 |
| **Subtotal (infra)** | | **~$800–1300** |
| LLM costs (variable) | | Variable |

---

## 5. Tier 3 — "Multi-region, regulated, multi-thousand users"

**Target:** $3k–10k+/month. Dedicated SRE attention.

What changes:
- **Multi-region Cloud Run** (Singapore + Tokyo) with Cloudflare-routed failover.
- **Cloud SQL with cross-region replica** for DR. RPO ~15min, RTO ~30min.
- **Qdrant self-hosted on GKE** with replication, or Qdrant Cloud dedicated tier.
- **Dedicated Temporal cluster** (Cloud or self-hosted on GKE) with task queues partitioned by Mode.
- **Brain worker pools per Mode**, each with its own HPA + budget ceiling. `kyc_edd` workers can have higher RAM; `lead_gen` workers are throughput-tuned.
- **API-key Claude path** — single OAuth subscription becomes the bottleneck around this scale. Move heavy workloads to API keys with per-Mode key pools.
- **PgBouncer in front of Cloud SQL** to multiplex connections from autoscaling workers.
- **Read-path caching** — Redis for B-feature queries (hot entity lookups), TTL'd against PKG update events.
- **Compliance layer** — VPC-SC perimeter, audit logs to BigQuery, customer-data isolation per tenant via per-tenant Postgres schemas or per-tenant Qdrant collections.

This tier exists in the doc only as a north star; it doesn't need to be built now.

---

## 6. Component-by-component design notes

### 6.1 The brain worker (the dominant component)

This is the unusual piece. Most cloud-native apps don't spawn subprocesses; this one does.

**Constraints:**
- Long-running (one turn can be 30–180s; full run 5–20 min)
- Spawns `claude` CLI as a subprocess per turn
- Needs OAuth refresh token in env
- Memory-hungry (Python + subprocess + MCP server connection)
- Should restart cleanly on failure; Temporal retries the activity

**Design:**
- **Containers**, not functions. Cloud Run will time out; Lambda will time out; only K8s-ish workloads work.
- **HPA on Temporal queue depth**, not CPU. CPU is misleading because the brain spends most time waiting on IO (the LLM).
- **Pod resource budget**: 2 vCPU / 4 GB minimum, 4 vCPU / 8 GB ideal. Subprocess fork + MCP keepalive needs the headroom.
- **Brain pool by Mode**: separate node selectors / labels per Mode so `kyc_edd` can be bigger pods, `lead_gen` smaller and more numerous.
- **Graceful shutdown**: Temporal heartbeats from inside the activity; SIGTERM → finish current turn → exit. K8s preemption-safe.
- **OAuth token rotation**: pre-flight refresh token on pod start; cache decoded access token in pod memory; refresh on 401 from Claude.

### 6.2 Postgres

- **Pgvector enabled** if we want one less moving part; otherwise Qdrant is fine. Today we use both — Qdrant for vectors, Postgres for relational. Keep both at Tier 2; reconsider consolidation at Tier 3 only if Qdrant becomes a real maintenance burden.
- **Schema for cross-run memory** (`agent_sessions`, `working_memory_snapshots`, `kg_claims` once PKG ships) grows monotonically. Plan **retention**:
  - `working_memory_snapshots` — full-fidelity for 30 days, then keep only `phase` transitions + final snapshot.
  - `wallet_operations` — keep 90 days at full fidelity, then roll up daily aggregates.
  - `kg_claims` — never delete; supersede instead.
- **Indexes** on `(user_id, finished_at)` on runs, `(subject, predicate)` on claims, `(run_id, turn)` on snapshots — these are the hot paths.
- **Connection pooling** — PgBouncer in transaction mode. Cloud SQL's built-in is fine to start; PgBouncer becomes necessary when worker fanout >20.

### 6.3 Qdrant

- Tier 1: Qdrant Cloud free tier (1GB).
- Tier 2: Qdrant Cloud paid (2–10GB).
- Tier 3: self-host on GKE with replication OR Qdrant Cloud dedicated.
- **Collection layout**: one per `(user_id, scope)` to enforce isolation cheaply. Avoid a single global collection — query filters get expensive past a few million points.
- **Embedding model**: keep current (per `app/memory/embeddings.py`). When budget allows, evaluate moving to a smaller, faster, locally-hostable model and re-embed corpus.

### 6.4 Temporal

- Tier 1: self-host on Fly. One node, one volume, daily backup. Acceptable risk for early stage.
- Tier 2+: Temporal Cloud. Don't fight this.
- **Task queues**: `is-run-tasks` (today) splits at Tier 2 into `is-run-tasks-{mode}` so workers pool by Mode without cross-pollination.
- **Workflow history bloat** — keep `WorkingMemory` snapshots passed by `run_id` reference, not embedded. Already planned in the loop design doc.

### 6.5 Frontend

- **Static, CDN-served.** Tier 1: Cloudflare Pages or Fly static. Tier 2: same — frontend doesn't need to "scale" in any meaningful sense.
- **Auth callback** stays close to the API (Cloud Run) to avoid CORS hell.
- **Server-sent events / WebSockets** for run-progress UI: terminate at Cloud Run (it supports them; min-instances=1 to keep connections warm).

### 6.6 MCP server

- Today it runs as a sidecar service. In cloud, two options:
  - **Sidecar in the brain worker pod** — one MCP server per pod, low latency, lifecycle-bound to the pod. Recommended.
  - **Shared MCP service** — one Cloud Run service, multiple brain workers connect. Higher latency, single point of failure. Don't.
- The MCP server is small; the sidecar is the right call.

### 6.7 Object storage (R2 over GCS)

- **Run artifacts** (export PDFs, dossiers, attachments) — Cloudflare R2. Zero egress is the killer feature for an export-heavy product.
- **Backups** — Postgres dumps + Qdrant snapshots to R2 nightly.
- **Versioning on** for the audit trail.

---

## 7. Cost model (honest)

The **dominant cost is LLM tokens**, not infrastructure. Order of magnitude:

| Cost line | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|
| Infra (fixed-ish) | ~$100 | ~$1000 | ~$5000 |
| LLM (variable, per run) | $0.50 – $5 (loop) – $50 (audit + full PKG write) | same | same |
| **At 100 runs/mo** | infra dominates | infra dominates | infra dominates |
| **At 1,000 runs/mo** | LLM ≈ infra | LLM ≈ infra | infra still big |
| **At 10,000 runs/mo** | LLM dominates | LLM dominates | LLM dominates |

**Implications:**
- Don't over-optimize infra cost before you have load.
- **Per-Mode budget caps** are the most important cost lever (already in the loop spec).
- **Caching B-queries** (Redis at Tier 3) saves both LLM and DB.
- **Embedding caching** — never re-embed an unchanged document. Tag by content hash. Cheap and high-leverage.

---

## 8. Security

Layered by realistic threat model for this product.

### 8.1 Identity & access
- **Workload Identity** (GCP) so workers fetch secrets without static credentials.
- **GitHub OIDC** to GCP for deploys — no service-account JSON in CI.
- **App auth**: today JWT via `python-jose`. Fine. At Tier 3 consider Auth0 / WorkOS for SSO + audit.
- **Per-user OAuth scope discipline** — every absorption endpoint already filters by `user_id`. Audit this on every new endpoint. CI lint rule worth adding.

### 8.2 Secrets
- **GCP Secret Manager** (Tier 2+) for everything: Claude OAuth refresh token, DB creds, third-party API keys (Apollo, OpenCorporates, etc.).
- **No secrets in env vars in Compose** outside of `.env.local`. CI fails if a secret pattern lands in source.
- **Rotation**: Claude OAuth refresh token rotated quarterly (semi-manual, given subscription auth). Third-party API keys rotated on a Mode-by-Mode basis when keys leak.

### 8.3 Network
- **Cloudflare WAF** in front of everything user-facing. Rate-limit /research, /agent/message endpoints.
- **Egress allow-list** at the GKE level — workers only talk to known third-party APIs + LLM endpoints. Prevents an exfiltration scenario where a compromised brain phones home.
- **VPC peering** between GKE and Cloud SQL — no public IP on Postgres ever.

### 8.4 Data
- **Encryption at rest** — default on every managed service. Verify.
- **Backups encrypted + versioned** in R2.
- **Per-tenant isolation** at Tier 3 — per-user prefix in Qdrant collections + row-level on Postgres (`WHERE user_id = …` enforced at the model layer, audited via test).
- **PII handling**: investigations touch personal data. Document the data lifecycle. Add a "purge user" endpoint that cascades to claims, snapshots, runs, R2 objects. Required if you ever face a SAR (subject access request).

### 8.5 Application
- **Brain subprocess sandboxing** — the brain runs `claude` which runs MCP tools which hit the internet. Treat its output as untrusted: validate against Pydantic schemas before applying to WorkingMemory. (Already done; keep doing it.)
- **Prompt-injection defense at the boundary** — system reminders the brain might emit are *output*, never *input*. Sanitize tool-result text before re-injection.
- **Audit logs** — every run start/end, every export, every PKG mutation. Ship to a write-once log (BigQuery or R2 with object-lock).

---

## 9. Performance

### 9.1 Frontend
- **Static + CDN edge in PH-adjacent region** (Cloudflare has SG + JKT). p95 first paint <1s.
- **Code-splitting** by route — Research, Dashboard, Run drawer are independent bundles.
- **Aggressive caching** of immutable API responses (finished-run data) with short TTL on B (entity knowledge, which mutates).

### 9.2 API
- **Cloud Run min-instances ≥1** to dodge cold start. Otherwise the first dashboard load after idle takes 1–3s.
- **Endpoint-level timeouts** — every absorption endpoint has a 5s budget; B with PKG should hit <500ms p95 (it's just indexed reads).
- **Async DB driver** (asyncpg via SQLAlchemy 2.0 async) — current `psycopg2` is sync and blocks the event loop. Migration worth doing at Tier 2.

### 9.3 Workers
- **Concurrency per worker** = N. Today's brain worker is ~1 activity at a time. With per-turn subprocess, that's fine. The lever is *pod count*, not *concurrency per pod*. HPA tuning > internal threading.
- **Cold-start the OAuth refresh** at pod boot so the first turn isn't slowed by an auth round-trip.
- **Embedding batching** — collect findings in a turn, embed in one Qdrant batch insert, not N individual ones.

### 9.4 DB
- **Read replica for absorption endpoints** at Tier 2 — B/E/H/G are all reads against historical data and tolerate replica lag.
- **Materialized view for the user cost aggregate (G)** — refresh every 5 min instead of computing on each request. Cheap, dramatically faster.
- **Vacuum tuning** for `working_memory_snapshots` — high churn, benefits from aggressive autovacuum.

---

## 10. Observability

The product is opaque without proper observability — runs are long, expensive, and hard to debug post-hoc. This is non-negotiable.

### 10.1 The three signals
- **Metrics** (Prometheus → Grafana Cloud):
  - Per-Mode run count, success rate, p50/p95/p99 duration
  - Per-Mode RU spend (rolling 7d/30d)
  - Brain turn count distribution per run
  - Temporal queue depth per task queue
  - DB pool saturation
  - LLM tool-call error rate per source_tool
- **Traces** (OpenTelemetry → Grafana Cloud Tempo):
  - One trace per run, spanning workflow → activities → MCP calls → external HTTP
  - Brain turn spans show prompt size, output size, parse success
- **Logs** (Loki):
  - Structured JSON; include `run_id`, `user_id`, `turn`, `mode`, `phase` on every log line
  - Brain stdout/stderr captured at warn+ only (full capture is too noisy and contains tokens-in-flight)

### 10.2 Domain dashboards
- **Run health** — success rate × Mode × time. Investigate any drop >5pp.
- **Cost** — RU/run by Mode + 7d trend. Alert on Mode-level p95 RU/run growing >20% week-over-week.
- **PKG health** — claims/day, contradictions/day, supersession rate. Catches schema-extraction regressions.
- **Quality proxies** — citation density, source-class distribution, deception-score histogram. The brain regressing on quality is usually invisible without these.

### 10.3 Alerts (paging vs ticketing)
- **Page**: API 5xx >1% over 5min; Temporal worker queue >100 items >10min; DB CPU >80% >10min.
- **Ticket**: per-Mode RU/run growth; deception-score distribution shift; quota-related Claude 429 rate.
- **Silent (dashboard only)**: per-finding source-class drift; PKG growth rate.

### 10.4 Cost observability (its own thing)
- **Cloud cost** — GCP billing export to BigQuery, Grafana panel by service.
- **LLM cost** — `wallet_operations` table already provides this; visualize by Mode + user + phase.
- The two together let you answer "what does Mode X cost per run, all-in?" — the question every PM eventually asks.

---

## 11. Administration & developer experience

### 11.1 Deploy pipeline (rules already in CLAUDE.md)
- **All deploys through CI/CD.** Never direct.
- **GitHub Actions** → build → push to Artifact Registry → deploy to Cloud Run (API) + roll GKE deployment (workers).
- **Migrations** — Alembic, run as a CI step against staging on every PR; against prod as part of deploy with a manual approval gate.
- **Rollback** — Cloud Run revisions + GKE deployment history. One-click rollback to last green.

### 11.2 Environments
- **Three envs**: dev (local Docker), staging (Tier 2 sized down 50%), prod.
- **Branch deploy previews** for the frontend on Cloudflare Pages. Saves real review time.
- **Neon branching** at Tier 1 → equivalent at Tier 2 via Cloud SQL clones for risky migrations.

### 11.3 Admin surface
- **Admin app** (separate route, separate auth) for:
  - User management
  - Per-Mode budget controls
  - Force-cancel runaway runs
  - Rotate Claude OAuth token without redeploy
  - Manual PKG corrections (with audit trail)
- **Feature flags** via GrowthBook (already partly wired). Per-user and per-Mode flags. Critical for shipping Living Subjects + Adversarial Audit safely.

### 11.4 Runbooks (write these once, don't regret it)
- "Brain worker pool stuck at high queue depth"
- "Postgres connection pool saturated"
- "Claude 429 / quota exhausted — failover or queue?"
- "PKG contradiction storm — what changed?"
- "Cost spike investigation"

### 11.5 Data ops
- **Schema migrations**: Alembic, reviewed, additive-only by default. Destructive migrations require a separate PR and a runbook entry.
- **Backups**: Postgres PITR + nightly pg_dump → R2; Qdrant snapshots nightly → R2. Test restore quarterly (untested backups are a fiction).
- **PII purge endpoint** — testable, audited, time-bounded SLO (e.g., "we honor purge within 7 days").

---

## 12. Ecosystem integration

Info-Broker is partly defined by what it connects to. Cloud design must not box this in.

| Integration | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|
| Slack / Notion / webhook exports (gap #1) | Direct from API | Same | Same + per-tenant routing |
| MCP for external agents (already shipped) | Direct expose | API-key gated | Per-tenant key + rate limit |
| n8n / Zapier / Hightouch | Webhook out | Webhook out + REST poll | Native connectors |
| Crayon / Clearbit / Apollo / OpenCorporates / WorldCheck | Direct API calls from MCP | Same; rate-limit via local proxy | Cached via shared proxy w/ TTL |
| Email (run notifications) | Resend / Postmark | Same | Per-tenant sender domains |

**Design rule:** every external integration is a *Mode-configurable tool* (already true in `MCP_TOOL_CATEGORIES`). Don't hard-code integrations into business logic.

---

## 13. Migration path

Concrete sequence from current Docker-Compose-on-laptop to Tier 2:

1. **Week 1** — Lift Compose to Fly. One app per service. Neon for Postgres. Qdrant Cloud free. Self-hosted Temporal on Fly. Health checks + Grafana Cloud free tier.
2. **Week 2** — CI/CD via GitHub Actions to Fly. Branch deploy previews. Sentry wired.
3. **Month 2** — Audit secrets management. Migrate from Fly secrets to (still Fly secrets, but documented + rotation plan). PII purge endpoint shipped.
4. **Month 3–4** — Promotion to Tier 2 when triggers hit: Cloud Run + GKE Autopilot + Cloud SQL + Temporal Cloud. Async DB driver migration alongside.
5. **Month 6+** — Tier 3 as needed.

**Reversibility check:** every Tier 2 component has a documented downgrade path back to Tier 1. The whole stack is containers + managed Postgres + managed vector DB; there's no proprietary lock-in beyond what the application code chose.

---

## 14. Open decisions for the owner

1. **Cloud preference.** Recommendation is GCP at Tier 2+. Override if there's an existing vendor relationship.
2. **Claude auth model in cloud.** Single subscription via OAuth refresh, or move to API keys with per-Mode key pools? The subscription works today; the bottleneck appears at ~5–10 concurrent runs.
3. **Region.** Singapore is the obvious primary for PH users; Tokyo or Mumbai as DR.
4. **Compliance posture.** None now is fine. The day a customer asks for SOC2-shaped answers, Tier 3 starts.
5. **Tenant isolation level.** Shared schema with row-level isolation (cheap) vs per-tenant schema (medium) vs per-tenant DB (expensive). Recommendation: row-level until first enterprise customer asks otherwise.
6. **Multi-region readiness window.** When do we accept the cost of cross-region replica + dual-write complexity?

---

## 15. One-paragraph summary

**Start on Fly + Neon + Qdrant Cloud + self-hosted Temporal for ~$100/mo and ship.** Migrate to **GCP (Cloud Run for API, GKE Autopilot for brain workers, Cloud SQL with replica, Temporal Cloud, Cloudflare R2 for exports, Secret Manager + Workload Identity)** when concurrency or compliance forces it — roughly $800–1300/mo at Tier 2. The brain worker pool is the dominant operational concern; everything else is conventional cloud-native. The dominant cost is LLM tokens, not infrastructure, so per-Mode budget caps + embedding-cache + B-query cache are the highest-leverage optimizations. Observability is non-negotiable from day one: structured logs with `run_id`, traces per run, per-Mode RU dashboards. The whole design is reversible and avoids proprietary lock-in beyond containers + Postgres + vector DB, which are all portable.
