# Info-Broker — System Design Decisions (Architecture Conversation Log)

This document is the source-of-truth capture of the architecture conversation that produced the current direction. It supersedes the earlier-written scale doc on the specific question of 10-concurrent-user sizing, because that earlier doc assumed a multi-key Claude model that was later corrected.

The structure: brief log of decisions made in conversation order, then the **corrected 10-user design** anchored on the actual constraint (single Claude subscription = hard global concurrency limit).

---

## 1. Conversation log — decisions made, in order

### 1.1 Eight absorption features (A–H) built end-to-end
Built `app/routers/v3/absorption.py` and frontend integrations for: headline, entity knowledge + contradictions, run diff, finding annotations, hypothesis xrefs, continue-thread, cost dashboard, open-questions digest.

### 1.2 Persona simulations — 5 archetypes scored
KYC analyst (8/10), Marketing Manager (7/10), Marketing Analyst (9/10, best fit), GTM Engineer (6/10), Leads Engineer (6.5/10). Documented at `docs/intelligence/persona-simulations.md`. Universal winner: **B (entity knowledge + contradictions)**.

### 1.3 Generalist substrate + Modes — not domain-specific agents
Decision: **one brain, one loop, one cross-run memory**; persona behavior is configuration (`Mode` YAML). Avoids forking the brain by domain, which would fragment the cross-run memory layer. Launch Modes: `general / kyc_edd / competitive_intel / lead_gen` (+ `academic_lit_review` if research bias remains). Documented at `docs/intelligence/modes-and-roadmap.md`.

### 1.4 Feature B v2 — Personal Knowledge Graph
Promote findings from prose to atomic `Claim`s `(subject, predicate, object, source, source_class, confidence, valid_from, valid_to)`. Unlocks time-travel queries, supersession, cross-entity inference, negative-evidence as first-class. ~9 days of work. Postgres-native; no graph DB required.

### 1.5 Two groundbreaking feature proposals
- **Adversarial Audit Co-Agent** — separate run with inverse goal (find refutations) launches after synthesize. Updates claim confidence with verdicts. Only possible because we own the loop + budget engine.
- **Living Subjects** — subjects become watched entities; cron re-runs diff at claim level; push only deltas to Slack/email/webhook. Flips tool from pull to push.

The three (PKG + Audit + Living Subjects) compose into a flywheel: **PKG accumulates → Audit calibrates → Living Subjects push deltas.**

### 1.6 Cloud infrastructure analysis
Three-tier design (`docs/operations/cloud-infrastructure.md`): Fly Tier 1 → GCP Tier 2 → multi-region Tier 3. **Superseded** by the hybrid model below for the personal-scale build.

### 1.7 WSL2 / Windows 11 runtime brainstorm
Legion 5, 16 GB RAM, Docker Desktop. Constraints: memory binding, Claude Code OAuth (no macOS keychain), filesystem placement (repo in WSL, not `/mnt/c`), three Compose profiles (`lean / default / full`).

### 1.8 Targeted improvements
- **Cloudflare Tunnel + `infobroker.tech`** chosen over ngrok. Free, persistent, integrated with Access + Pages + R2.
- **Embedding model stays Gemini** — no perf win observed from local; revisit when monthly spend >$30 *or* PKG re-embed window arrives.
- **Neo4j moves to opt-in `--profile graph`** — saves ~1.5 GB on default `up`. PKG covers absorption needs without graph DB.
- **Multi-machine: Split B** — Legion + optional secondary Linux box on Tailscale, when/if available.

### 1.9 Hybrid architecture confirmed
Cloudflare absorbs the public internet (DNS, TLS, WAF, Pages, Access, R2, Workers). Postgres / Qdrant / Temporal / brain workers stay home. Hetzner CX22 (~$5/mo) provisioned **only when a queue-depth wall is hit**. Documented at `docs/operations/hybrid-architecture.md`.

Subdomain plan: `infobroker.tech` (Pages), `api.` / `mcp.` / `temporal.` / `admin.` (tunneled, some Access-gated). `dev.*` dropped — Pages preview deploys cover staging/blue-green.

### 1.10 Wall analysis (where load lands first)
1. Brain worker concurrency
2. Claude subscription quota
3. Gemini embedding quota
4. Postgres connection pool
5. Storage growth
6. Edge/API rate (never realistically)

**Walls 1 and 2 hit roughly together** under the subscription auth model — adding workers past the subscription's tolerance is wasted.

### 1.11 First-pass 10-user design — *contains a correction below*
Initial design (`docs/operations/scale-10-users.md`) assumed BYOK or multi-key Claude as the path past wall 2, with 5 burst workers. **This was the wrong default.** The corrected design is below, anchored on the actual constraint.

---

## 2. The correction — what changes when the only auth is one subscription

The earlier scale design treated subscription as "the bottleneck we engineer around." The user is engineering for the case where **subscription is the primary path** and BYOK/API is a **separate, paid track** that offloads cost to the user. Under that framing:

| Quantity | Subscription path | BYOK / API path |
|---|---|---|
| Quota source | One Claude Code subscription | User's own Anthropic API key (or their own subscription) |
| Concurrency ceiling | **~2–3 concurrent runs** (account-level) | Per-user quota, isolated from others |
| Cost to platform per run | LLM tokens come out of platform subscription budget | $0 (user pays Anthropic directly) |
| Who pays | Platform | User |
| Burst workers help? | **No** — workers can't multiply quota | Yes — multiple workers map to multiple user quotas |
| Design center | Aggressive queueing + global rate limit | Multi-worker pool + per-user concurrency |

These are two different products sharing one substrate. They should not be conflated in capacity planning.

---

## 3. Local hardware capacity check — Legion 5, 16 GB RAM

### 3.1 Memory budget under WSL2 + Docker Desktop

| Layer | RAM |
|---|---:|
| Windows host (browser, IDE, OS) | 4.0 GB |
| WSL2 cap (`.wslconfig` memory=12GB recommended) | 12.0 GB |
| Docker Desktop overhead inside WSL | 1.0 GB |
| **Available for containers** | **~11 GB** |

### 3.2 Fixed-cost containers (always running)

| Service | RAM | Notes |
|---|---:|---|
| postgres | 1.0 GB | tune `shared_buffers=256MB` |
| pgbouncer (when added) | 0.1 GB | transaction-mode pool |
| qdrant | 1.0 GB | small corpus default |
| temporal-server | 1.0 GB | single-node |
| redis (new) | 0.4 GB | cache layer |
| info-broker-api | 0.8 GB | FastAPI |
| non-brain temporal-worker | 0.5 GB | non-LLM activities |
| cloudflared | 0.1 GB | tunnel |
| MCP server (sidecar to brain) | 0.3 GB | per brain pod |
| **Fixed subtotal** | **~5.2 GB** | |

### 3.3 Brain worker budget

Per pod: **2.5–3.0 GB** peak (Python + subprocess + MCP context + headroom).

With ~5.8 GB free after fixed services:
- **2 brain worker pods** fit comfortably (5.0–6.0 GB used)
- 3 brain worker pods would oversubscribe; first OOM is a matter of when, not if

**Hardware ceiling on Legion alone: 2 brain workers.**

### 3.4 Subscription concurrency ceiling

Empirical observation of Claude Code subscription tolerating concurrent brain subprocesses:
- 1 concurrent: always fine
- 2 concurrent: reliable
- 3 concurrent: occasional 429 / throttling
- 4+ concurrent: regular 429s, degraded latency, eventual session-level rate-limit refusal

**Subscription ceiling on a Pro plan: ~2 concurrent reliably, 3 with degradation tolerance.** (Max 5×/20× plans are more permissive but documented per-account ceilings still apply.)

### 3.5 The two ceilings align

| Constraint | Limit |
|---|---:|
| Hardware (Legion RAM) | 2 brain workers |
| Subscription quota | 2–3 concurrent |
| **Effective concurrency** | **2** |

**Adding burst workers on Hetzner doesn't raise this** when on the subscription path — they would consume the same shared quota. Burst workers only help when on BYOK/API path with per-user keys.

---

## 4. Corrected 10-user design — subscription-first

### 4.1 The product positioning shift

**Investigation tools don't need instant gratification.** A submit-and-walk-away UX is acceptable — possibly even desirable — when the alternative is "your subscription gets throttled and 8 users see failures."

The product becomes:
1. Submit a research question.
2. See a queue position and ETA up front.
3. Walk away. Browser tab can close.
4. Notification (email / Slack / webhook / push) when done.
5. Open the result via a permalink.

This is the same shape as `gh run watch`, Substack post processing, or any well-designed async batch tool. Not novel; not a downgrade.

### 4.2 Queue dynamics at 10 concurrent users on 2-slot capacity

With avg run time = 10 min, 2 concurrent slots:

| User position in queue | Expected wait |
|---|---:|
| #1 (submitted while a slot is free) | 0 min |
| #2 | 0 min |
| #3 | ~10 min |
| #4 | ~10 min |
| #5 | ~20 min |
| #6 | ~20 min |
| #10 (worst case for the 10-user burst) | **~40–45 min** |

This is the honest worst case if 10 users all submit at the same instant. In normal Poisson-distributed arrivals it's much milder. Mitigations below limit how often the worst case shows up.

### 4.3 Core mechanisms

#### A. **Global rate limit, not per-user rate limit**
The brain pool is one shared resource. The limit lives at the pool, not at the user. `BRAIN_GLOBAL_MAX_CONCURRENT=2`, enforced at the pre-run gate. A 3rd run dispatches to the queue regardless of which user submitted it.

#### B. **Strict per-user concurrency = 1 on subscription tier**
On the subscription path, **one user can only have one run executing at a time**. They can have multiple queued; only one runs. Prevents a single user from filling both slots and starving the other nine.

#### C. **Priority queue, 3 levels**
- `is-run-urgent` (admin / paid users)
- `is-run-standard` (paying-but-non-priority)
- `is-run-free` (free tier)
Workers poll in priority order. A paying user's submission jumps the queue ahead of free-tier waits.

#### D. **Daily run cap per user**
- Free: 3 runs/day
- Hobby ($10): 10 runs/day
- Pro on subscription tier ($30): 30 runs/day, jumps queue
- BYOK: unbounded (their quota, their bill)
Prevents power users from monopolizing the global pool.

#### E. **Cost preview + estimated wait at submit**
Before dispatch, return: estimated cost, estimated duration, **estimated queue wait based on current depth**. User confirms with full information.

```json
{
  "estimated_cost_usd": 1.20,
  "estimated_duration_min": 12,
  "estimated_queue_wait_min": 18,
  "queue_position": 4,
  "total_until_complete_min": 30,
  "confirm_token": "abc123"
}
```

#### F. **Aggressive caching to reduce per-run work**
- Tool result cache (Redis, 1h–7d by tool type) — 30–50% hit rate
- Embedding cache (Redis, content-hash, infinite TTL) — 60–80% hit rate at steady state
- Retrieval cache (5min)
- PKG entity cache (60s)
Caching doesn't increase concurrency but it **shortens average run duration** which proportionally raises effective throughput. A 30% run-time reduction = ~30% more runs through the same 2 slots.

#### G. **Notification when done — multiple channels**
- In-app toast on next dashboard visit
- Email (default for free)
- Webhook (BYOK / Pro tier)
- Slack (Pro tier)
- Push notification (mobile, future)

#### H. **Permalinks to runs** so the user can come back hours later from any device.

#### I. **Graceful degradation levels** (unchanged from earlier design, but rebalanced):

| Level | Trigger | Behavior |
|---|---|---|
| 0 | Queue depth ≤2 | Full features |
| 1 | Queue depth >3 | Skip Adversarial Audit on free tier; defer Living Subjects pushes |
| 2 | Queue depth >8 or any Claude 429 in last 5min | Reduce turn budget 30%; pause Living Subjects; warn users |
| 3 | Queue depth >15 *or* Claude 429 rate >5% | Pause new **free-tier** runs; existing runs continue; banner |
| 4 | Worker crash / DB exhaustion / sustained Claude block | All new runs paused; admin paged |

#### J. **Estimated wait gate**
If estimated wait at submit exceeds a tier-configurable ceiling (e.g., free: 60min, paid: 20min), the gate refuses with: *"Queue is full. Try again in N min, upgrade to BYOK for guaranteed concurrency, or submit and be notified."*

### 4.4 What the platform spends per month, subscription-only tier

| Item | Monthly |
|---|---:|
| Cloudflare (free) | $0 |
| Hetzner burst workers | **$0** — they don't help, skip |
| Home electricity | sunk |
| Gemini paid embedding (with cache) | $5–10 at 10-user scale |
| Domain | $1 |
| R2 storage | $0.50 |
| Stripe fees (when billing live) | ~$5 |
| **Infrastructure** | **~$10–17** |
| **Claude subscription (the only LLM line)** | **$20 (Pro) / $100–200 (Max)** |
| **Total** | **$30–220/mo, flat regardless of usage** |

**Critical property: cost is flat.** 10 users on subscription tier cost the same as 1 user. Margins improve with utilization, not degrade. This is the unit economics insight that the earlier design missed.

### 4.5 BYOK / API track — separate design, parallel substrate

When a user provides their own credentials:

- **Their concurrency budget is their own.** A BYOK user with their own Pro subscription gets the same 2-concurrent ceiling, but it's *their* ceiling, not the platform pool.
- **They bypass the global queue.** Their runs hit a separate `is-run-byok` queue served by the same worker pool, with a *separate per-user concurrency limit* (e.g., 2).
- **They pay for compute via Anthropic, not us.** Platform charges a flat $5–10/mo for infra access.
- **Burst workers re-enter the picture for this tier only.** When a heavy BYOK user starts running 5 concurrent investigations, provision additional brain workers on Hetzner so home isn't starved. The worker checks credentials at activity start, picks them from the BYOK user's encrypted record.

This is the path that grows past the subscription ceiling without changing the subscription design.

| Tier | Auth | Concurrency | Daily cap | Price |
|---|---|---|---|---:|
| Free | Platform subscription | Pool-shared, 1/user | 3 | $0 |
| Hobby | Platform subscription | Pool-shared, 1/user, priority | 10 | $10/mo |
| Pro Sub | Platform subscription | Pool-shared, 1/user, urgent priority | 30 | $30/mo |
| Pro BYOK | User's API key | Per-user, 2 concurrent | unlimited | $10/mo infra |
| Enterprise | User's API key, pooled | Per-user, 5 concurrent + dedicated worker | unlimited | $200/mo+ |

The subscription tiers compete for the platform pool. BYOK tiers compete only with themselves. Both share the substrate, observability, and UI — but never share quota.

### 4.6 Build order — corrected for subscription-first

**Week 1 — Foundation (queueing + caching + gate)**
1. Redis container + tool-result and embedding caches (~1 day)
2. Pre-run gate: per-user concurrency = 1, global concurrency = 2 (~0.5 day)
3. Cost + wait estimate endpoint (~1 day)
4. Daily-cap enforcement (~0.5 day)
5. Temporal priority queues (`urgent` / `standard` / `free`) (~1 day)
6. Notification system (in-app + email) (~1 day)

**Week 2 — UX for async**
7. Queue position WebSocket + UI (~1 day)
8. Run permalinks + auth-aware history (~0.5 day)
9. "You'll be notified" submit confirmation (~0.5 day)
10. Degradation level state machine + banner (~1.5 days)
11. Estimated-wait refusal at gate (~0.5 day)

**Week 3 — Hardening + observability**
12. PgBouncer in front of Postgres (~0.5 day)
13. Grafana home dashboards (queue depth, 429 rate, turn-time, cache hit rate) (~1 day)
14. Cloudflare WAF rules + FastAPI rate-limit middleware (~1 day)
15. Cloudflare Tunnel finalize + Pages connect + Access policies (~1 day)
16. WSL `mem_limit` / `mem_reservation` / profiles cleanup (~0.5 day)
17. Neo4j → opt-in `--profile graph` (~0.5 day)

**Week 4 — BYOK track (separate, parallel)**
18. Encrypted credential storage (`kg_user_creds`) (~1 day)
19. Brain worker reads credentials at activity start (~1 day)
20. BYOK settings UI (~1 day)
21. Separate `is-run-byok` queue + per-user concurrency on BYOK (~1 day)
22. Hetzner CX22 runbook for BYOK overflow (~0.5 day)

**Week 5 — Billing (optional, defer for beta)**
23. Stripe subscriptions ($10 / $30 / $200) (~2 days)
24. Tier enforcement in pre-run gate (~1 day)
25. Usage dashboard (~1 day)

Total: 4 weeks for subscription path live, week 5 adds BYOK and billing.

### 4.7 What the user sees — UX of an async tool

**Submit screen:**
```
Subject: Maridel Holdings Inc. — beneficial ownership

Estimated cost:    $1.20
Estimated runtime: 12 min
Queue position:    #4 (3 ahead)
Estimated total:   ~32 min until complete

Notify me by:  ✓ in-app  ✓ email  ☐ Slack  ☐ webhook

  [ Submit and notify ]    [ Cancel ]
```

**Queue screen (live, WebSocket):**
```
Your run is queued (#4 → #3 → #2 → running)
Started: in 18 min
Notification will arrive when done. You can close this tab.
```

**Completion notification (email):**
```
Subject: Maridel Holdings investigation ready (12 min, 6 findings)

View the result: https://infobroker.tech/runs/abc123

3 hypotheses tested
1 contradiction surfaced
6 findings (4 registry, 2 news)
Cost: $1.12 (under estimate)
```

This is what 10 concurrent users get on a 2-slot subscription pool — and it works.

---

## 5. Resolved questions from prior turns

- **Domain**: `infobroker.tech` registered at `domain.com`, point nameservers to Cloudflare.
- **Frontend**: Cloudflare Pages on `infobroker.tech`. No `dev.*`. Preview deploys cover branches.
- **Cloudflare account**: Gmail-based; free plan + free Zero Trust + R2 (already provisioned).
- **Embedding model**: stay on Gemini; revisit when monthly spend >$30 *or* PKG re-embed window.
- **Neo4j**: opt-in `--profile graph`. Default `up` skips it.
- **Burst workers**: deferred; only meaningful on BYOK path, not subscription.
- **Multi-machine**: deferred until a secondary Linux box is actually available.

---

## 6. Open decisions still on the table

1. **Subscription plan to run the platform pool on** — Pro ($20), Max 5× ($100), or Max 20× ($200)? Affects how many concurrent slots are realistic and how often 429s show up. Recommend starting on whatever plan you have and measuring 429 rate; promote only if data forces it.
2. **Notification channels at MVP** — in-app + email is the floor. Slack and webhook are P1.
3. **Tier pricing** — $10 / $30 / $200 above is illustrative. Final pricing requires market test.
4. **Free tier daily cap** — 3 runs/day proposed. Adjust based on actual completion times.
5. **Estimated-wait refusal ceiling** — proposed 60min free / 20min paid. Adjust after observing real waits.
6. **Stripe in week 5 or defer** — recommend defer for closed beta; track usage in `wallet_operations`, charge nothing yet.

---

## 7. Reading order for someone new to this design

1. `docs/intelligence/persona-simulations.md` — why we shipped A–H and what users actually want
2. `docs/intelligence/modes-and-roadmap.md` — generalist substrate + Modes
3. `docs/operations/hybrid-architecture.md` — Cloudflare + home + tunnel
4. **This file** — capacity, queueing, fallback, two-track auth model
5. `docs/operations/cloud-infrastructure.md` — reference for if/when this design grows past home

The other docs are reference; this one is the *current direction*.
