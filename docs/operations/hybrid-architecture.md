# Info-Broker Hybrid Architecture — Light Cloud, Heavy Local, Burst-Cheap

Canonical deployment model. Supersedes the tier-based cloud design in `cloud-infrastructure.md` for the home/personal-scale build; that doc remains relevant if and when the project moves to a fully-managed hyperscaler footprint.

## The shape

```
                      ┌──────────────────────────────────────┐
                      │  Cloudflare — infobroker.net         │
                      │  DNS · TLS · WAF · DDoS · CDN        │
                      │  Pages (frontend static)             │
                      │  Access (zero-trust auth)            │
                      │  R2 (exports, backups, artifacts)    │
                      │  Workers (rate-limit, edge logic)    │
                      └────────────────┬─────────────────────┘
                                       │  Cloudflare Tunnel
                                       │  (no port-forward, no public IP)
                                       ▼
        ┌──────────────────────────────────────────────────────────┐
        │  HOME — Legion 5 (+ optional second Linux box)            │
        │  ──────────────────────────────────────────────           │
        │   cloudflared ─► FastAPI ─► Postgres                      │
        │                  │           Qdrant                       │
        │                  │           Temporal server              │
        │                  └─► IS-brain worker (subprocess+MCP)     │
        │                      Non-brain worker                     │
        │                      MCP server (sidecar)                 │
        └──────────────────────────────┬───────────────────────────┘
                                       │  Tailscale mesh
                                       │  (private, end-to-end)
                                       ▼
              ┌────────────────────────────────────────────┐
              │  Hetzner CX22 (~$5/mo) — burst worker      │
              │  Spawned/joined when home queue saturates  │
              │  • is-temporal-worker container            │
              │  • Connects home Postgres + Temporal       │
              │    over tailnet hostnames                  │
              └────────────────────────────────────────────┘
```

## Why this shape

| Concern | How it's solved |
|---|---|
| Public reachability without exposing home IP | Cloudflare Tunnel — outbound-only from home |
| TLS, DDoS, WAF | Cloudflare edge (free tier covers it) |
| Static frontend latency | Cloudflare Pages serves from global edge |
| Auth on sensitive surfaces (temporal-ui, admin) | Cloudflare Access (email OTP / Google SSO, free for ≤50 users) |
| Data sovereignty | Postgres + Qdrant never leave home; R2 only holds explicit user exports |
| Subscription quota | Claude Code OAuth lives on home machines; burst worker uses same token (quota is per-account, machine-agnostic) |
| Burst capacity | Hetzner CX22 joined to Tailscale becomes a Temporal worker; queue depth + Temporal handle distribution natively — no orchestration glue |
| Cost discipline | Edge is free, home is sunk cost, burst is $5/mo *only if used* |

## Subdomain layout (`infobroker.net`)

| Host | Backed by | Public? |
|---|---|---|
| `infobroker.net`, `www.infobroker.net` | Cloudflare Pages → built frontend | Public |
| `api.infobroker.net` | Tunnel → FastAPI on home | Public (app-layer JWT) |
| `mcp.infobroker.net` | Tunnel → MCP server | Access-gated initially; API-key-gated later |
| `temporal.infobroker.net` | Tunnel → Temporal UI | **Access-gated** (you only) |
| `admin.infobroker.net` | Tunnel → admin app (when shipped) | **Access-gated** |
| `webhooks.infobroker.net` | Cloudflare Workers → tunnel forward | Public, HMAC-verified |

Reserve subdomains in DNS even before they're used. Cheap, prevents squatting friction later.

## Embedding model — stay with Gemini

Decision locked: embeddings continue through `llm_providers.embed_text` (Gemini). Reasons captured for posterity:

- No measured latency or quality gap against current model.
- Local serving (TEI + Jina v3) would add a GPU-bound container and re-embed cost.
- Migration creates a dual-collection / re-embed problem that is real, not theoretical.
- **Re-evaluation trigger:** if monthly Gemini embedding spend exceeds $30, *or* offline mode becomes a product requirement, *or* PKG (B v2) ships and we have a natural one-time re-embed window — then revisit. Until then, status quo.

## What goes cloud vs local

| Component | Where | Why |
|---|---|---|
| DNS | Cloudflare | Free, fast, ACME for TLS |
| TLS termination | Cloudflare | Auto-renew, edge offload |
| Frontend static | Cloudflare Pages | Edge cache, free, CI-deployed |
| FastAPI / API | Home (Legion) | Stateful, low-latency to DB |
| Postgres | Home (Legion or secondary) | Primary state, low-latency required |
| Qdrant | Home | Same — co-locate with API + workers |
| Temporal server | Home | Owns workflow state |
| Brain worker | Home (+ Hetzner overflow) | Needs OAuth + subprocess + DB-adjacency |
| Non-brain worker | Home | Cheap, co-located |
| MCP server | Home (sidecar) | Lifecycle-tied to brain pod |
| Exports / backups | Cloudflare R2 | Zero-egress object storage |
| Edge rate-limit / WAF | Cloudflare Workers (free tier) | Pre-filter abuse before it hits home |
| Webhook receivers | Cloudflare Workers → tunnel | Public surface absorbed at edge |
| Burst worker | Hetzner CX22 (Tailscale) | $5/mo, joins as Temporal worker only when needed |
| Backups storage | R2 (encrypted, versioned) | Nightly pg_dump + Qdrant snapshots |

## Burst worker — how it actually works

**The key insight**: Temporal already solves this. A worker is just a process that polls a task queue. Add another worker, polling the same queue, from anywhere reachable — Temporal load-balances automatically. No orchestration glue, no autoscaler, no Kubernetes.

```
┌────────────────────────────────────────────────────────────┐
│ Provisioning the burst worker (one-time, ~1 hour):         │
│                                                            │
│  1. Hetzner Cloud → create CX22 (Ubuntu 24.04, ~$5.30/mo)  │
│  2. Install Docker + Tailscale                             │
│  3. Pull is-temporal-worker image                          │
│  4. .env: POSTGRES_HOST=home.tailnet.ts.net                │
│            TEMPORAL_HOST=home.tailnet.ts.net               │
│            CLAUDE_CODE_OAUTH_REFRESH_TOKEN=…               │
│  5. docker compose up -d                                   │
│  6. Worker auto-registers with Temporal, drains queue      │
└────────────────────────────────────────────────────────────┘
```

That's the entire mechanism. No cold-start latency (worker stays running), no autoscaling code, no separate cron.

**Three burst flavors, from simplest to fanciest:**

1. **Always-on** ($5.30/mo) — recommended default. Worker is always polling; if home is idle, this one picks up. If home is busy, both run concurrently. Capacity ≈ 2× home.
2. **Scheduled** ($0 most days) — provision in Hetzner via API the night before a heavy day; deprovision after. Effort to wire up: ~2 hours of scripting against Hetzner API.
3. **Reactive autoscale** — Temporal queue-depth metric triggers Hetzner API spin-up. Most elegant; ~1 day of work. Skip until you actually need it.

**Recommendation: ship flavor 1 *when* a queue depth problem appears, not before.** Until then, home is enough.

**Important quota nuance.** Adding a burst worker does *not* add Claude quota. Both workers consume from the same subscription. Burst worker buys you **more CPU/RAM in parallel**, not more LLM throughput. If LLM rate-limits become the bottleneck (not local CPU), the fix is API keys with a separate budget — not more workers.

## Cloudflare Tunnel setup — the load-bearing piece

A tunnel is a long-running outbound connection from `cloudflared` (running at home, in Docker) to Cloudflare's edge. Cloudflare forwards traffic from configured hostnames to local services via this connection. **No port-forward, no public IP, no dynamic DNS, no ISP business-plan upsell.**

**Compose addition:**

```yaml
cloudflared:
  image: cloudflare/cloudflared:latest
  restart: unless-stopped
  mem_limit: 100M
  command: tunnel --no-autoupdate run
  environment:
    - TUNNEL_TOKEN=${CLOUDFLARED_TOKEN}
  depends_on:
    - info-broker-api
    - frontend
```

**Configuration is at Cloudflare**, not in compose — ingress rules map hostname → local service:

```yaml
# Cloudflare dashboard or cloudflared config.yml
ingress:
  - hostname: api.infobroker.net
    service: http://info-broker-api:8000
  - hostname: mcp.infobroker.net
    service: http://mcp-server:8765
  - hostname: temporal.infobroker.net
    service: http://temporal-ui:8080
  - service: http_status:404
```

**Why this beats ngrok**: persistent hostnames you own, zero per-request cost, Cloudflare Access integration, R2 in the same control plane, no banner injection, no rotating URLs.

## Security posture (concrete, not aspirational)

| Layer | Control |
|---|---|
| Edge | Cloudflare WAF rules (OWASP CRS + custom rate-limits on `/research`, `/agent/message`) |
| Public auth | Cloudflare Access on temporal-ui, admin, MCP. Email OTP, free, 1-click |
| App auth | Existing JWT (`python-jose`) on api.infobroker.net |
| Webhook integrity | HMAC signature verification at the Worker layer before tunnel |
| Secrets at rest | Local: `.env` outside repo + `chmod 600`. Burst worker: secrets via Hetzner project env. R2 access keys: rotate annually |
| Egress from home | Outbound-only; tunnel breaks if compromised but does not expose inbound surface |
| Burst worker compromise | Limited blast radius — has Postgres credentials. Mitigate: scoped DB user with no destructive grants. No PII purge rights from burst |
| Tailscale ACLs | Burst worker can only reach `postgres:5432`, `temporal:7233`; cannot reach `qdrant:6333` or `host:22` |

**The two non-obvious moves worth doing on day one:**
1. **Scoped Postgres role for the burst worker** — its own user with INSERT/SELECT on the tables it actually touches, no DROP/ALTER/DELETE-on-other-tables. If the cheap VPS is ever pwned, the blast radius is bounded.
2. **Tailscale ACLs restricting what the burst node can see** — it's `tag:burst`, allow `home:postgres,home:temporal`, deny everything else.

## Performance characteristics (real numbers, not aspirational)

| Path | Latency budget |
|---|---|
| Browser → `infobroker.net` (Pages, edge-cached) | <100ms p95 from PH |
| Browser → `api.infobroker.net` (edge → tunnel → home) | 50–150ms p95 from PH (extra hop through Cloudflare) |
| API → Postgres (local) | <2ms |
| API → Postgres from burst worker (Tailscale over WAN) | 30–100ms — **avoid chatty endpoints from burst** |
| Brain turn (subprocess + LLM + tools) | 30–180s — dominates; network overhead negligible |
| Tunnel throughput | Cloudflare free tier has no documented per-tunnel cap; trial showed 50+ Mbps sustained |

The tunnel adds ~30–50ms vs naked port-forward, which is invisible against an API that does anything meaningful. The browser → tunnel hop is the only path where it's measurable.

## Observability adjustments for this topology

- **Edge metrics** from Cloudflare (free analytics) — requests, status codes, cache hit rate, top URLs. Already there.
- **Tunnel health** — `cloudflared` exposes Prometheus metrics on `:2000/metrics`. Scrape into Grafana.
- **Home stack** — Prometheus + Grafana running locally (own container), no cloud cost. Optional Grafana Cloud forwarding if you want off-site dashboards.
- **Burst worker** — same Temporal worker metrics; surfaces in the same dashboard as home worker, distinguishable by `worker_identity` label.

**Heartbeat alert** — Cloudflare Health Checks (free) ping `/healthz` on `api.infobroker.net` every minute, email on 3 consecutive failures. Covers the "is my home box up" question with zero infrastructure.

## What this costs

| Line item | Monthly |
|---|---:|
| Domain (`infobroker.net`, amortized) | ~$1 |
| Cloudflare (DNS + Tunnel + Pages + Access + Workers free tier) | $0 |
| R2 storage (10–50 GB) | $0.15–0.75 |
| Tailscale Personal | $0 |
| Hetzner CX22 burst worker (when needed) | $5.30 |
| Home electricity (already paid) | — |
| LLM tokens (Gemini embed + Claude) | variable |
| **Marginal infra cost** | **~$1–7/month** |

Compare to Tier 2 hyperscaler ($800–1300/mo) and the case for staying hybrid is overwhelming until either (a) home reliability becomes a customer-facing SLO or (b) compliance requires audited managed infrastructure.

## Build order

Numbered, dependency-ordered, with rough effort:

1. **Register / confirm `infobroker.net`** — Cloudflare Registrar if not already there. *15 min*
2. **DNS up at Cloudflare** — point nameservers. *15 min*
3. **Create Cloudflare Tunnel** in dashboard, get token, add `cloudflared` to compose. *30 min*
4. **Map first ingress: `api.infobroker.net` → local FastAPI.** Verify externally. *20 min*
5. **Cloudflare Pages connected to repo** — auto-deploy frontend on push to main. *30 min*
6. **Map `infobroker.net` → Pages** + `api.infobroker.net` already from step 4. *10 min*
7. **Cloudflare Access policies** on `temporal.infobroker.net` + `admin.infobroker.net` (when admin exists). *30 min*
8. **R2 bucket** for backups + exports. Wire nightly pg_dump cron at home. *1 hour*
9. **Tailscale on Legion** + tailnet ACL stub. *20 min*
10. **WSL2 baseline complete** (separate brainstorm doc — neo4j off, memory caps). *2–3 hours*
11. **(Defer until needed)** Hetzner burst worker with scoped Postgres role + tailnet ACL. *1 hour when triggered*
12. **(Defer until needed)** Workers for webhook receiver + rate-limit. *2 hours when first integration ships*

Steps 1–10 are pure setup and unblock everything else. Step 11 waits for an actual queue-depth problem. Step 12 waits for the first webhook integration (likely concurrent with Living Subjects work).

## Decisions to confirm before I cut config

1. **Is `infobroker.net` already registered, and where?** If at Cloudflare already, easier. If elsewhere, transfer recommended (free, takes 5 days).
2. **Cloudflare Pages or tunnel for the frontend?** Pages is cheaper and faster (edge-served, no home dependency). Tunnel-to-frontend lets you dev in real time but routes every static request through home. **My pick: Pages, with a `dev.infobroker.net` tunneled for live-reload dev.**
3. **Email for Cloudflare Access OTP** — what address should be the "you" account? (Personal Gmail vs project-dedicated.)
4. **Cloudflare account: free or Pro ($20/mo)?** Free covers everything in this doc. Pro adds image optimization, more page rules, lossless image compression — none load-bearing here.
5. **Burst worker timing — provision now or defer?** My pick: defer. Provisioning before there's queue depth is wasted $5/mo and adds an unused attack surface.
