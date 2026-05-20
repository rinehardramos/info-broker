# Designing for 10 Concurrent Users — Hybrid Architecture

Companion to `hybrid-architecture.md`. Translates "support 10 parallel users" into the concrete capacity, queueing, caching, fallback, rate-limiting, and pay-per-use mechanisms that have to exist *before* the 10th user can run an investigation without the system falling over.

## Honest framing — what "10 users in parallel" actually means

There are two interpretations and they diverge by 5×.

| Interpretation | Implies | Steady-state runs/hour | Peak concurrent runs |
|---|---|---:|---:|
| 10 users *active in the app* | UI use, occasional investigation | ~5–15 | 1–3 |
| 10 users *each running an investigation* | Worst case | ~30–60 | **10** |

Design for the worst case, but instrument to confirm the realistic case. **Provisioning for "10 simultaneous investigations always" wastes ~70% of capacity most of the time.** The system below sizes for *peak of 10, expected of 3, with graceful degradation past peak*.

---

## The capacity model

### Run shape (from observed data)

- Avg run: ~10 min, ~$3 LLM cost, ~150 claims emitted, ~30 embeddings
- p95 run: ~20 min, ~$8 LLM cost
- p99 run: ~30 min, ~$15 LLM cost (audit + complex hypotheses)

### Worker capacity

- 1 brain worker pod = 1 subprocess at a time = 1 concurrent run
- p95 throughput per worker: ~3 runs/hour (10 min avg + 10 min slack)

### Capacity math for the 10-user target

| Scenario | Workers needed | Hardware |
|---|---:|---|
| 10 users running once/hour avg, accepting up to 5min queue | 4 workers | 1 home + 3 burst |
| 10 users hammering at full concurrency, zero queue wait | 10 workers | 1 home + 9 burst (overkill) |
| **Recommended: peak-of-10 with degradation** | **5–6 workers** | **1 home + 4–5 burst** |

The recommended size assumes:
- Concurrency arrivals are Poisson-distributed (real human behavior)
- 5min queue wait at peak is acceptable
- Past peak, degradation rules kick in (covered below) rather than infinite queue growth

**Hetzner CX22 × 5 = $26.50/month.** This is the structural cost of the 10-user target.

---

## Walls revisited under 10-user load

The walls from the earlier analysis shift dramatically.

| Wall | Single user | 10 users | Mitigation required |
|---|---|---|---|
| 1. Brain worker concurrency | Trivial | **Binding** | 5–6 worker pool |
| 2. Claude subscription quota | OK | **Will break** | Per-user credentials (BYOK) or paid API keys |
| 3. Embedding quota (Gemini free) | OK | **Will break** | Paid Gemini tier ($) + embedding cache |
| 4. Postgres connections | OK | Tight | PgBouncer in front of Postgres |
| 5. Storage growth | Slow | Slow | Retention policy on snapshots |
| 6. Edge/CDN | Never | Never | n/a |

**Wall 2 is the most important architectural change.** Subscription-only auth caps you at ~3–5 concurrent regardless of how many workers you provision. Solutions in order of cleanliness:

1. **BYOK (Bring Your Own Key)** — each user provides their own Claude API key, stored encrypted. Your platform never bottlenecks on quota; the user owns their LLM bill. Best for early monetization. *Recommended.*
2. **Platform API-key pool** — N Anthropic API keys, round-robin per Mode. Your platform owns billing. Cleaner UX, harder margins.
3. **Hybrid** — first 5 runs/month free on platform key; after that, user must BYOK or upgrade. *Recommended ramp.*

---

## System design — components

```
        Cloudflare Edge
        ├ rate-limit: 100 req/min/IP on /research
        ├ rate-limit: 10 req/min/IP on /agent/message
        ├ WAF (OWASP CRS)
        └ static assets cached at edge
                       │
                       ▼
        ┌──────────────────────────────────────┐
        │ FastAPI (Home Legion)                │
        │  ─ Pre-run gate (synchronous)        │
        │     • user_id concurrency check      │
        │     • user budget check              │
        │     • cost preview                   │
        │     • degradation level check        │
        │     • priority assignment            │
        │  ─ WebSocket: queue position updates │
        └──────────────┬───────────────────────┘
                       │
            ┌──────────┼────────────────┐
            ▼          ▼                ▼
       Redis        Temporal         Postgres
       (Home)       Server           (Home, PgBouncer)
       cache layers (Home)           
       
                       │
            ┌──────────┴────────────────────────────┐
            ▼                                       ▼
        Priority queues:                  Worker pool:
          is-run-urgent   (admin)         • home brain (1× Legion)
          is-run-paid     (paid users)    • burst-1..5 (Hetzner CX22)
          is-run-free     (trial users)   each reading user creds
                                          at activity start
```

### Redis — cache layer (the biggest LLM-cost lever)

| Cache | Key | TTL | Invalidation | Hit-rate target | Cost saved per hit |
|---|---|---|---|---:|---|
| Tool result | `tool:{tool}:{sha256(args)}` | 24h (URL fetches), 1h (search results) | TTL only | 30–50% | $0.01–0.10 |
| Embedding | `embed:{sha256(text)}` | infinite | content-hash | 60%+ on re-runs | $0.0001/vector |
| `fused_retrieve` | `fr:{user}:{query_hash}` | 5min | invalidate on new claim for user | 20–40% | LLM round-trip |
| PKG entity lookup (B) | `pkg:{user}:{subject}` | 60s | invalidate on claim insert | 70%+ on hot entities | DB query |
| Headline render | `hl:{run_id}` | immutable | never | 100% on re-fetch | LLM round-trip |
| Cost preview | `est:{prompt_hash}:{mode}` | 1h | TTL | 30%+ | small LLM call |

**Single Redis container, 256–512 MB, AOF every-second persistence.** ~$0 marginal cost; massive impact.

Realistic projection: **30–40% reduction in LLM spend** at 10-user scale from these caches alone (most savings in tool-result and embedding caches). That's the difference between $900/mo and $550/mo in LLM cost at 300 runs/month.

### Temporal — priority queues

Today: one queue `is-run-tasks`. For 10 users with mixed entitlement levels:

```
Queue            Polled by                  Priority
─────────────────────────────────────────────────
is-run-urgent    all workers (top priority) admin/escalation
is-run-paid      all workers                paying tier
is-run-free      all workers (low priority) trial tier
```

Workers poll all three with priority ordering. Free-tier users wait when paid users are running. **This is the lever that lets a free tier exist without starving paying users.**

Per-user concurrency cap enforced in the dispatcher (not in Temporal): max 2 concurrent runs per user_id. Third run goes to a per-user pending list, surfaced in UI with ETA.

### PgBouncer — Postgres connection multiplexing

At 5–6 workers + API container + cron jobs, Postgres connection count balloons. PgBouncer in transaction-mode pooling caps real connections at 20–30 even with hundreds of logical connections. One container, ~100MB, ~30min to configure.

Trigger to install: when worker count crosses 3, *or* connection-pool exhaustion error appears in logs once.

---

## Pre-run gate — the most important code change

Before any run reaches Temporal, the API runs a synchronous gate. Reject early, fast, with clear reasons. This is what makes 10-user load survivable.

```python
# Pseudocode for the gate logic
def admit_run(user_id, mode, prompt):
    # 1. Degradation check
    if degradation_level >= 3:
        return reject("Service degraded; runs paused. Try again in N minutes.")
    
    # 2. Per-user concurrency
    active = active_runs_for(user_id)
    if len(active) >= USER_MAX_CONCURRENT:
        return reject(f"You have {len(active)} active runs. Wait for one to finish.")
    
    # 3. Per-user daily rate limit
    today_count = runs_today(user_id)
    if today_count >= user_daily_limit(user_id):
        return reject(f"Daily limit ({user_daily_limit(user_id)} runs) reached.")
    
    # 4. Budget check
    estimated_cost = estimate_cost(prompt, mode)
    user_balance = wallet_balance(user_id)
    if estimated_cost > user_balance:
        return reject(f"Estimated cost ${estimated_cost:.2f} exceeds balance ${user_balance:.2f}.")
    
    # 5. Cost preview (return for confirmation, don't auto-dispatch)
    if not request.confirmed:
        return preview(estimated_cost, estimated_duration_min, queue_position)
    
    # 6. Priority assignment
    priority = priority_for_tier(user_tier(user_id))
    
    # 7. Dispatch
    return temporal.start_workflow(
        IsLoopRunWorkflow,
        ISRunInput(...),
        task_queue=f"is-run-{priority}",
    )
```

Latency budget: <100ms p95. Everything is index lookups + cache reads.

---

## Incremental fallback — degradation levels

The system has a single `degradation_level` variable (0–4), recomputed every 30s from observability signals. Each level changes behavior automatically; users see a status banner.

| Level | Trigger | Behavior | UX |
|---|---|---|---|
| 0 — Healthy | All metrics green | Full features | No banner |
| 1 — Busy | Queue depth >5 OR p50 wait >1min | Skip Adversarial Audit on free tier; defer Living Subjects pushes by 5min | Banner: "Heavy load — premium features queued" |
| 2 — Strained | Queue depth >15 OR Claude 429 rate >0.1% OR Gemini errors >1% | Reduce turn budget by 30%; pause non-urgent Living Subjects; disable PKG cross-entity inference | Banner: "Service under load — runs may be slower" |
| 3 — Critical | Queue depth >30 OR Claude 429 rate >2% OR DB CPU >85% | Pause new free-tier runs (paid still admitted); existing runs continue; mass-notify free users | Banner: "Service degraded — new free runs paused" |
| 4 — Emergency | DB connection exhaustion OR Claude widespread errors OR worker pool down | Pause **all** new runs; existing runs may fail; admin alerted via page | Banner: "Service unavailable — fix in progress" |

Two non-obvious properties:
- **Automatic recovery.** Levels recompute every 30s. As soon as conditions clear, the system relaxes back. No manual intervention needed for transient spikes.
- **Per-tier graduation.** Levels 1–3 protect paid users by degrading free first. Free users see degradation; paid users see consistent service. This is the unit economics survivor: subscription revenue covers the floor.

---

## Caching strategy — the LLM-cost lever

The right caches at this scale aren't UI caches; they're cost caches. Re-evaluating which findings to embed, which tool results to re-fetch, which retrievals to re-run — that's where the dollars sit.

### Tool result cache
- Most expensive: `run_news_search`, `run_web_crawl`, `run_sec_lookup`, paid enrichment APIs.
- Key: `tool_name + canonicalized args` SHA256.
- TTL strategy:
  - News searches: 1 hour (news ages fast)
  - SEC/registry lookups: 7 days (corporate registries change slowly)
  - Web crawls: 24 hours
  - LinkedIn-style profile lookups: 24 hours
- **Cross-user cache?** Yes for non-PII queries; no for queries containing identifiable user-specific tokens. The simplest gate: cache only when `cache_safe=true` flag on the tool. Default false; opt in per tool.

### Embedding cache
Content-addressed, infinite TTL. The single biggest LLM-spend reduction at scale: identical findings across runs (same news article, same registry record) embed once, ever.

```python
def cached_embed(text: str) -> list[float]:
    key = f"embed:{sha256(text)}"
    if cached := redis.get(key):
        return msgpack.loads(cached)
    vec = embed_text(text)  # real Gemini call
    redis.set(key, msgpack.dumps(vec))  # no TTL
    return vec
```

Expected hit rate at 10-user steady state: 60–80%. Single biggest cost reduction in the system.

### Retrieval cache
`fused_retrieve(query, user_id)` results cached 5 minutes, invalidated when a new claim is written for that user. Cuts redundant retrievals within a single run's turn cycle.

### PKG query cache (B-feature reads)
Dashboard B-widget polled on every visit. Cache `{user, subject}` 60s, invalidate on claim insert for that user/subject. Cuts DB hits ~10×.

---

## Rate limits — three layers

| Layer | What it limits | Why here |
|---|---|---|
| Cloudflare WAF | IP-level abuse (>100 req/min) | Catches bots before tunnel cost |
| FastAPI middleware | Per-user endpoint rate (e.g. 60 GET /pkg /min) | Protects DB + Redis |
| Pre-run gate | Per-user concurrency + daily count | Protects worker pool + LLM budget |

Each layer is independent. A burst of 1000 dashboard refreshes from one user can hit Cloudflare's 100/min and never reach FastAPI; a user trying to start 20 runs hits the gate's daily cap regardless of how many dashboard refreshes they did.

---

## Pay-per-use — the economics

### Cost-per-run (your cost, with 30% cache savings baked in)

| Cost line | Avg | p95 | p99 |
|---|---:|---:|---:|
| Claude tokens (with cache) | $0.70 | $2.50 | $5.00 |
| Gemini embeddings (with cache) | $0.005 | $0.02 | $0.04 |
| Tool API costs (3rd party enrichment) | $0.10 | $0.50 | $1.00 |
| Compute (CX22 amortized) | $0.05 | $0.10 | $0.15 |
| **Total per run** | **$0.85** | **$3.10** | **$6.20** |

### Pricing tier proposals

| Tier | Price | Runs included | BYOK option | Behavior past quota |
|---|---:|---:|---|---|
| Trial | $0 | 3 lifetime | — | Locked until upgrade |
| Free | $0 | 5/month | Yes (no charge) | Degraded queue priority |
| Hobby | $10/mo | 20/mo | Yes (discount) | Hard cap with overage at $1/run |
| Pro | $30/mo | 100/mo | Yes (preferred) | Soft cap; overage at $0.50/run |
| BYOK Only | $5/mo | unlimited (you pay LLM) | Required | Pass-through |
| Enterprise | $200/mo+ | Unlimited + priority queue + audit | Yes | Custom |

Notes:
- **BYOK is the unit-economics savior at 10-user scale.** Users with their own Claude keys cost the platform ~$0.15/run (compute + enrichment). Margin is healthy.
- **Platform-key tiers have thinner margins.** Hobby at $10 covers ~12 platform-paid runs cost-wise; the "20 included" works only because real usage averages 60–70% of allowance (industry norm).
- **Overage charging avoids the "free tier got hit" cliff.** Soft caps with metered overage prevent angry users while preserving margin.

### Wallet system (already partly built — extend it)

Today `wallet_operations` tracks RU per run. For pay-per-use:
- Add `wallet_credits` table — credits purchased, expiry, source (subscription / topup / referral).
- Pre-run gate consumes estimated credits; refund delta after actual usage.
- Stripe integration for top-up + subscription billing.
- Per-Mode pricing multipliers — `kyc_edd` runs are heavier; charge 1.5× credits.

---

## What this costs the platform to run

| Item | Monthly |
|---|---:|
| Home electricity (already paid) | — |
| Cloudflare (free tier covers 10 users) | $0 |
| Hetzner CX22 × 5 burst workers | $26.50 |
| Gemini paid tier embedding (cached) | $5–15 |
| Domain | $1 |
| R2 storage + bandwidth | $1–3 |
| Stripe fees (variable, ~3%) | ~$10 at $300 MRR |
| Sentry/monitoring (free tier) | $0 |
| **Infrastructure** | **~$45–55** |
| Platform Claude costs (if no BYOK) | $200–800 |
| **Total worst case** | **$250–850/mo** |

Revenue at modest 10-user adoption:
- 5 Hobby × $10 = $50
- 3 Pro × $30 = $90
- 2 BYOK × $5 = $10
- **MRR: $150**

So: BYOK and Pro tiers must be a real percentage of users for the unit economics to work without overage. Otherwise the platform subsidizes free/hobby on Claude. The architecture supports both models; pick based on which segment you're recruiting first.

---

## Build sequence — what to ship in what order

Sized for "want this live in 4 weeks for a 10-user beta."

### Week 1 — Foundation (caches + queues + gate)
1. **Redis container** + cache middleware for tool results and embeddings. *~1 day*
2. **Per-user concurrency cap** in pre-run gate. *~0.5 day*
3. **Cost-preview endpoint** (estimates before dispatch). *~1 day*
4. **Per-user budget enforcement** (extends `wallet_operations`). *~1 day*
5. **Temporal priority queues** (free/paid/urgent). *~1 day*

### Week 2 — Multi-tenant credentials + worker pool
6. **Per-user credential storage** (encrypted at rest, `kg_user_creds` table). *~1 day*
7. **Brain worker reads user creds at activity start.** *~1 day*
8. **BYOK UI** — settings page for API keys. *~1 day*
9. **Provision Hetzner CX22 × 5 + Tailscale + runbook.** *~1 day*
10. **PgBouncer** in front of Postgres. *~0.5 day*

### Week 3 — Degradation + observability
11. **Degradation level state machine** + metric inputs. *~1.5 days*
12. **Status banner UI** + WebSocket for live updates. *~1 day*
13. **Queue position display** in run-pending UI. *~0.5 day*
14. **Prometheus + Grafana home dashboards** for the new metrics. *~1 day*
15. **Cloudflare WAF rules** + FastAPI rate-limit middleware. *~1 day*

### Week 4 — Billing + tiers
16. **Stripe integration** — subscriptions + top-up. *~2 days*
17. **Tier enforcement** in pre-run gate. *~1 day*
18. **Usage dashboard** — user-visible RU consumed, runs remaining, projected month-end. *~1 day*
19. **Overage handling** + soft-cap notifications. *~1 day*

### Total ~ 4 weeks, 1 engineer.

---

## What this design does *not* do (boundaries worth naming)

- **Multi-region.** Single home + EU burst workers. PH users see ~150ms API latency. Fine for 10; revisit at 100.
- **Real-time collaboration.** No two users sharing a run/dashboard live. Cross-user PKG remains per-user-scoped.
- **Audit-grade SLA.** If home goes down, the service is down. No automatic cloud failover. Documented as "best effort" in tier contracts.
- **GDPR DSR automation.** PII purge endpoint exists but is operator-triggered, not user-self-service. Acceptable at 10 users; not at 1000.
- **HA Postgres / DR.** Nightly backups to R2; manual restore. RPO 24h, RTO 4h. Acceptable for this scale.

If any of these become real requirements, the answer is "promote to the Tier 2 hyperscaler design in `cloud-infrastructure.md`", not "patch this design."

---

## Decisions to confirm before I cut code

1. **BYOK first or platform-paid first?** Affects week 2 priorities (BYOK UI vs API-key pool). *My pick: BYOK first; platform-paid is a v2 layer.*
2. **5 CX22s now, or 1 home + scale on demand?** I'd start with 1 home + 1 CX22 to validate the burst-worker pipeline, scale to 5 only when queue metrics demand. *My pick: 1+1 to start.*
3. **Stripe in week 4, or defer billing until product validation?** Free beta with 10 users first means no Stripe in v1, saves a week. *My pick: defer Stripe; track usage in `wallet_operations` but don't charge yet.*
4. **Degradation levels manual override?** Should you have a "force level 3" button to test? *My pick: yes, behind admin auth.*
5. **Per-Mode pricing multipliers?** Charge `kyc_edd` runs more credits than `lead_gen`? *My pick: yes, makes economics honest.*
