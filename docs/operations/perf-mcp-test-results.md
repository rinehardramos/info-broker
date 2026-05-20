# Performance + MCP Smoke Test Results — 2026-05-21

Live end-to-end testing against `https://infobroker.tech` (Cloudflare Pages →
tunnel → home FastAPI) with admin session, plus MCP server functional smoke.

## Cold-load Web Vitals (homepage)

| Metric | Value | Target | Verdict |
|---|---:|---:|:---:|
| Total wall time | 409 ms | — | ✓ |
| TTFB | 85 ms | <500 ms | ✓ |
| LCP (Largest Contentful Paint) | 432 ms | <2.5 s (good) | ✓ excellent |
| DOMContentLoaded | 341 ms | — | ✓ |
| Load event | 341 ms | — | ✓ |
| Initial HTML transfer | 1 KB | — | ✓ |

## Admin session — per-route navigation

After `admin/admin` login (2.18 s flow):

| Route | TTI | API calls |
|---|---:|---:|
| `/dashboard` | 897 ms | 10 |
| `/research` | 1.75 s | 14 |
| `/runs` | 764 ms | 2 |
| `/wallet` | 890 ms | 6 |
| `/settings` | 772 ms | 2 |
| `/monitors` | 824 ms | 2 |

**Warm cache re-nav:** `/dashboard` 782 ms, `/runs` 700 ms (modest improvement; cache mostly serves static assets, not API responses).

## API latency (50 calls from browser, full session)

- Total: 50 requests
- 2xx: 50
- Errors (≥400): 0
- Median: ~600 ms (estimated from per-route)
- Slowest endpoints:
  - `GET /v3/templates` — 1.11 s
  - `GET /v3/agent/brain/status` — 1.06 s
  - `GET /v3/open-questions/digest` — 1.04 s

These three are pure-backend slow (DB query patterns); the Cloudflare tunnel hop is ~260 ms, leaving ~800 ms inside FastAPI for the slowest ones. Worth optimizing if they become hot.

## Tunnel overhead

| Path | Latency |
|---|---:|
| Direct `http://localhost:8000/healthz` | 6 ms |
| Via `https://api.infobroker.tech/healthz` | 266 ms |
| **Tunnel + CDN edge overhead** | **~260 ms** |

This is the cost of public reachability. Acceptable for an LLM-bound workload where API calls are negligible against eventual 30-180 s brain runs.

## Security headers (from `public/_headers`)

All shipped + serving on every response:
- `strict-transport-security: max-age=31536000; includeSubDomains; preload` ✓
- `permissions-policy: geolocation=(), microphone=(), camera=()` ✓
- `referrer-policy: strict-origin-when-cross-origin` ✓
- `x-content-type-options: nosniff` ✓
- `x-frame-options: DENY` ✓

## CORS

`Origin: https://infobroker.tech` → `access-control-allow-origin: https://infobroker.tech`, `access-control-allow-credentials: true`. 50 cross-origin requests succeeded in the admin session test.

## Cache behavior

Pages root (HTML) returns `cf-cache-status: DYNAMIC` — Cloudflare doesn't cache HTML by default. That's fine; the React shell is ~1 KB and the JS/CSS bundles are aggressively cached at the edge (long cache headers from Vite hashed filenames).

---

## MCP smoke test

**Server**: `mcp_server/server.py` running as a subprocess inside the API container.

**Tools registered:** 58

First 15 (alphabetically by registration order):

```
 1. run_web_search                      Multi-engine web search with consensus ranking and auto-translation to E…
 2. run_qdrant_search                   Semantic vector search over Qdrant collections.
 3. export_research                     Export run findings as PDF/markdown/JSON.
 4. run_web_crawl                       Crawl a list of URLs with depth-limited fetch + content extraction.
 5. search_obsidian                     Semantic search over an Obsidian vault stored in Qdrant.
 6. search_local_files                  Search local text/document files by content.
 7. run_wikipedia_api                   Fetch a structured Wikipedia article summary and content by title.
 8. run_apollo_search                   Search Apollo.io for people or companies.
 9. run_ph_sec_dti                      Search Philippine SEC/DTI business registry.
10. run_clutch_goodfirms                Search Clutch and GoodFirms for IT service companies.
11. run_linkedin_profile_search         Search LinkedIn profiles by job title and location via Apify.
12. run_apify_actor_generic             Run any Apify actor with arbitrary input.
13. run_web_search_fetch                Web search with optional full page content fetching.
14. run_facebook_pages                  Search Facebook pages for company info, executives, and contact details.
15. run_twitter_search                  Search Twitter/X for tweets and user profiles matching a query.
… and 43 more.
```

**Live invocation:** `run_wikipedia_api(title="Anthropic", language="en")`

| Metric | Value |
|---|---|
| Duration | 372 ms |
| Output size | 740 bytes |
| Output shape | `{"status": "success", "items": [...], "count": N}` |
| Sample preview | `"Anthropic is an American artificial intelligence (AI) company headquartered in San Francisco..."` |

Tool executed successfully end-to-end: server received the call, hit Wikipedia REST API, parsed response, returned structured JSON. The same path is what the brain subprocess hits during a real research run.

---

## Verdict

Production deploy is healthy:
- Static frontend delivery is fast (sub-500ms TTFB and LCP from PH).
- All in-app navigations complete under 1.8 s including API calls.
- Tunnel + tunnel-backed API is operational; 260 ms overhead is acceptable.
- All security headers ship correctly.
- 58 MCP tools are registered and at least one verified working live.
- Zero errors across the test session.

## Backlog from this test run

| Item | Priority |
|---|---|
| `GET /v3/templates` is 1.1 s — investigate the query plan | medium |
| `GET /v3/agent/brain/status` is 1.0 s — likely an external subprocess check | low |
| `GET /v3/open-questions/digest` is 1.0 s — aggregate query; consider materialized view (already in scale-10-users.md) | medium |
| OPTIONS preflight returns 405 + CORS headers on `/v3/agent/message` — verify browsers accept; if not, add explicit OPTIONS handler | low |
| Run Lighthouse/WebPageTest for richer metrics (PageSpeed score, accessibility, SEO) | low |

## How to re-run

```bash
cd frontend
pnpm playwright test e2e/perf-and-mcp.spec.ts --reporter=line
```

The MCP test inside that spec has a shell-escaping issue. To re-run the MCP smoke directly:

```bash
# Copy + run the script inside the API container
TMP=$(mktemp /tmp/mcp_smoke.XXXXXX.py)
# (paste the script body from the inline session)
docker cp "$TMP" info-broker-info-broker-api-1:/tmp/mcp_smoke.py
docker compose exec -T info-broker-api /app/.venv/bin/python /tmp/mcp_smoke.py
```
