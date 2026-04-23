# Changelog

All notable changes to info-broker are documented here.
Entries follow **Keep a Changelog** conventions (newest first).

---

## [Unreleased]

### Added — Playlist audio sourcing for PlayGen (design 2026-04-23)

- New endpoint `POST /v1/playlists/source-audio` to be implemented.
  - Receives `{ station_id, songs: [{song_id, title, artist}], callback_url }` from
    PlayGen's DJ pipeline (info-broker is the *receiver*, not the caller).
  - For each song, downloads audio via yt-dlp and uploads to Cloudflare R2 under key
    `songs/{stationId}/{songId}.mp3` in the `ownradio` bucket
    (`https://fa958caa19c273f07b49c49a09d76a60.r2.cloudflarestorage.com`).
  - R2 credentials are stored server-side in environment variables; callers do not
    supply credentials in the request body.
  - On completion, POSTs a result payload back to `callback_url` with per-song
    status, R2 object keys, and error details for any failures.
  - Accepts `X-API-Key` auth, same as all other `/v1/*` endpoints.
- R2 env vars (`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT`,
  `R2_BUCKET`) added to `.env.example`.

### Context

The existing `POST /v1/songs/source` endpoint handles single-song ad-hoc downloads
with caller-supplied S3 credentials. The new `/v1/playlists/source-audio` endpoint
is purpose-built for the PlayGen batch workflow: it accepts a full station playlist,
manages R2 credentials internally, and drives the callback lifecycle.

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
