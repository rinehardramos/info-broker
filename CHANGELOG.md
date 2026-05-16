# Changelog

All notable changes to info-broker are documented here.
Entries follow **Keep a Changelog** conventions (newest first).

---

## [0.6.0] — 2026-05-16

### Added

- **Google + GitHub OAuth login.** Server-side authorization-code flow.
  - New routes: `GET /v3/auth/{google,github}/login`, `GET /v3/auth/{google,github}/callback`,
    `GET /v3/auth/providers` (probe).
  - First-login flow auto-creates user + personal org. Existing accounts match by email.
  - Secrets resolve from `core_settings` table first, env vars as fallback
    (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`).
  - `ui_users` gains `oauth_provider`, `oauth_sub`, `avatar_url` columns; `password_hash`
    NOT NULL constraint relaxed for SSO-only users. Coexists with password login.
- **Session-scoped file uploads with library opt-in.**
  - `research_sources` gains a nullable `session_id` column.
  - `POST /v3/sources/upload` accepts `session_id` form field.
  - `GET /v3/sources?session_id=…&include_library=…` filters appropriately.
  - `POST /v3/sources/{id}/attach` re-attaches a library item to a new session.
  - FileUploadZone reads active session from chatStore; refetches on session change.
  - New "Library" button opens a picker for prior uploads.
- **WebSocket event buffer with replay on reconnect.** Cloudflare-tunneled WS
  connections cycle every ~10s; buffering ensures cards emitted during disconnects
  are replayed on reconnect within a 120s TTL.
- **engine_v2 `start_run` flag wired end-to-end.** Frontend's preflight confirm now
  triggers the actual pipeline launch (previously a no-op).
- **Demo recording infrastructure.**
  - `e2e/demo-feature-tour.spec.ts` records a 6–12 min Chrome 1440×900 WebM video
    with overlay subtitles + parallel SRT sidecar covering all happy-path features.
  - `e2e/preflight-watch.spec.ts` for WS event diagnostics.
  - `e2e/gcp-oauth-bootstrap.spec.ts` semi-automates Google OAuth Client ID creation.
- **`/v3/sources/{id}/attach`** and **`/v3/auth/providers`** new public endpoints.

### Changed

- **Runs / History / Jobs pages consolidated into `/runs`.**
  - Both Runs and History rendered the same `listRuns()` data; History was a strict
    subset. `/jobs` page was a vestigial 23-line list using a different older endpoint.
  - Old routes `/history` and `/jobs` now `<Navigate to="/runs" replace />`.
  - Sidebar IconRail trimmed. The `/v3/jobs` backend endpoint and `listJobs()`
    function are kept (LiveStream.tsx still consumes them for real-time tracking).
- **PerformanceDashboard humanized:** snake_case tool / tactic / strategy / node IDs
  are converted to Title Case at the UI layer. Monospace styling removed where it
  made labels read as JSON-ish.
- **FindingView redesigned** with proper visual hierarchy: host strip · date · bold
  title · prose snippet · footer with confidence bar + "Open source ↗". Leading
  "N hours ago - " prefixes stripped from snippets.
- **`FindingRow` cleans up MCP snippets** with broken whitespace
  (BeautifulSoup `get_text(strip=True)` was stripping all inter-tag whitespace);
  multi_search.py now uses `get_text(" ", strip=True)`.
- **Modal redesign:** Raw Output tab folded into a "Details" tab (collapsed by default)
  alongside Input + Timing. Default tab now "Results" rendering proper FindingView,
  not JSON.
- **Dark theme by default.** Moved dark shadcn CSS vars to `:root` so navy mode
  no longer renders light cards/borders when `.dark` class absent.
- **Run cards no longer dump raw JSON.** Body falls back to a clean status line
  when the data isn't a recognizable finding shape.

### Fixed

- **Metrics router prefix bug** — was mounted at `/api/v3/metrics/...`; Vite proxy
  strips `/api` so backend never matched. Now mounted at `/v3`.
- **Button missing `forwardRef`** caused Radix `Primitive.button.SlotClone` warnings.
- **Null-unsafe `.toFixed()` calls** in dashboards: now use Number()-coerced
  `fmtNum` / `fmtPct` helpers that handle null + DB NUMERIC strings.
- **JSON-encoded nested string fields** in MCP tool results: `_deep_parse_json`
  recursively decodes so the modal renders structured data, not escape-soup.
- **FlowMiniPreview restored** for v2 runs (the v2 path had swapped to a vertical
  mini-DAG that was redundant with the phase pills above).
- **Dead vertical space removed** above the result cards (was a fixed
  `height: 200px` wrapper now that the swim lanes collapsed to a subtitle).

### Known issues — see filed tickets

- [#90] Test isolation: ~90 pytest failures when full suite runs (shared user fixtures)
- [#91] Frontend vitest: 33 test files fail to import (jsdom localStorage missing)
- [#92] Test collection: 2 stale imports break pytest (test_github_search, test_multi_search)
- [#93] Security: 2 moderate dev-dependency CVEs (esbuild + vite path traversal)
- [#94] Ruff: 14 S608 false positives (clause-constant SQL injection warnings)

---

## [0.5.0] — 2026-04-23

### Added

- **`POST /v1/playlists/source-audio`** — batch audio sourcing endpoint for PlayGen.
  Receives `{ station_id, songs: [{song_id, title, artist}], callback_url }`, downloads
  audio via yt-dlp for each song, uploads to Cloudflare R2 (`ownradio` bucket, key
  `songs/{station_id}/{song_id}.mp3`), and POSTs results back to `callback_url`. Per-song
  failures do not abort the batch. Returns `202 { job_id, status: "queued" }`.
- **`POST /v1/songs/source`** — individual song sourcing endpoint (caller supplies S3
  credentials inline; distinct from the batch endpoint above).
- **`INFO_BROKER_API_KEY`** env var — required shared secret; clients send it as `X-API-Key`.
- **`PLAYGEN_INTERNAL_URL`** env var — PlayGen callback base URL (e.g. `https://api.playgen.site`).
- **Deployed on Railway** in the PlayGen project. Internal hostname: `info-broker.railway.internal:8000`.

### Changed

- **R2 env vars renamed to S3_*** for consistency with the boto3 S3-compatible interface:
  `R2_BUCKET` → `S3_BUCKET`, `R2_ENDPOINT` → `S3_ENDPOINT`, `R2_REGION` → `S3_REGION`,
  `R2_ACCESS_KEY_ID` → `S3_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` → `S3_SECRET_ACCESS_KEY`.
  Update `.env` accordingly before deploying.

---

## [0.4.0] — 2026-04-12

### Added

- OSINT search-engine MVP (`/v2/` router): async DB layer (asyncpg), Qdrant result
  storage, plugin protocol with DuckDuckGo plugin, domain-tier heuristic scoring,
  parallel fan-out executor, JWT auth stub, feedback storage, E2E smoke test.

## [0.3.0] — 2026-04-08

### Fixed

- Qdrant AttributeError: migrated `client.search()` → `client.query_points()` for
  qdrant-client v1.17+ compatibility; updated episodic-memory test suite.

## [0.2.0] — 2026-04-07

### Added

- **Phase 1** ReAct loop: LLM-driven dynamic DuckDuckGo queries, scrape + analyse
  cycle, self-correction before finalising JSON.
- **Phase 2** Episodic memory via Qdrant `user_feedback` collection; `--backfill-memory`
  CLI for historical grades; 13-test suite.
- **Phase 3** Dynamic few-shot from best/worst Postgres grades injected into the
  system prompt.
- **Phase 4** Critic agent with single retry loop (fails open on error).
- **Phase 5** Fine-tuning JSONL exporter (`export_dataset.py`) and base-vs-finetuned
  evaluator (`evaluate_finetuned.py`); docs in `docs/fine-tuning.md`.
- **Phase 6** Runtime + supply-chain hardening: `security.py` with SSRF guard,
  prompt-injection sanitisation, CSV formula-injection escaping, and `ruff S608` SQL
  lint; 60 unit + 4 integration security tests; `SECURITY.md` threat model.
- Media surface (`/v1/*`) exposed for PlayGen DJ pipeline: weather, news, song
  enrichment (MusicBrainz), jokes, and single-song audio sourcing via yt-dlp with
  optional S3-compatible upload.
- Supply-chain hardening: `uv.lock` + hash-pinned `requirements.lock`; `pip-audit`
  CI gate; 0 CVEs.

## [0.1.0] — initial

- FastAPI wrapper around the OSINT/LinkedIn research pipeline extracted from
  `auto-marketer-project` (ingestion, ReAct research, critic grading, episodic
  memory, semantic search via Qdrant).
