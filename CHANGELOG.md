# Changelog

All notable changes to info-broker are documented here.
Entries follow **Keep a Changelog** conventions (newest first).

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
