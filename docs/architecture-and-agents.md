# System architecture and multi-agent design

## Core components

1. **PostgreSQL** — the source of truth. Stores raw profile JSON, research state, analytical conclusions, grades, and generated emails.
2. **Qdrant** — the vector database. Two collections: `linkedin_profiles` (semantic search over prospects) and `user_feedback` (episodic memory of graded research).
3. **LLM provider** — pluggable via `LLM_PROVIDER`. Default is `google` (Gemini 2.5 Pro for chat, `text-embedding-004` for embeddings via the OpenAI-compatible Gemini endpoint). Set `LLM_PROVIDER=lmstudio` to use a local LM Studio server instead.
4. **DuckDuckGo + requests/bs4** — web search and scraping for the ReAct loop. All outbound fetches go through `safe_fetch_url` for SSRF protection.
5. **Redis (planned / optional)** — task queue for parallelizing research across worker agents. Not yet wired up; the current pipeline runs single-process batches of 5.

## Agent roles

- **Ingestion agent (`ingest.py`)** — fetches the Apify dataset, scrubs untrusted fields, writes rows to Postgres, embeds profile text, and upserts into the Qdrant `linkedin_profiles` collection.
- **Research agent (`research_agent.py --run`)** — pulls pending rows, runs the ReAct loop (DuckDuckGo + scrape + LLM), consults episodic memory for past mistakes, consults few-shot examples drawn from past grades, and writes the analysis back to Postgres.
- **Critic agent** — *implemented*. A second LLM call inside `research_agent.py` that approves or rejects each analysis. The researcher gets one retry on rejection. The critic fails open on error.
- **Grading / eval system (`research_agent.py --grade`, `evaluate_grading.py`)** — interactive CLI that captures a 1-5 human grade and optional feedback, persists it to Postgres, and embeds it into the Qdrant `user_feedback` collection. `evaluate_grading.py` computes alignment between the system confidence score and the human grade.
- **Fine-tuning pipeline (`export_dataset.py`, `evaluate_finetuned.py`)** — exports high-graded profiles as an OpenAI-format JSONL and evaluates a fine-tuned model against the base model. See [fine-tuning.md](fine-tuning.md).
- **Email generator (`generate_emails.py`)** — walks SMB prospects with completed research and asks the LLM for a personalized cold email, stored in `linkedin_profiles.generated_email`.

## Current Postgres schema (`linkedin_profiles`)

See [data-model.md](data-model.md) for full column documentation. In brief:

- Identity: `id`, `first_name`, `last_name`, `headline`, `about`, `raw_data`
- Research: `research_status`, `is_smb`, `needs_outsourcing_prob`, `needs_cheap_labor_prob`, `searching_vendors_prob`, `research_summary`, `system_confidence_score`, `confidence_rationale`, `search_queries_used`
- Grading: `user_grade`, `user_feedback`
- Outreach: `generated_email`

There is no `tags` column in the current implementation; segment campaigns via `is_smb`, `user_grade`, or `search_queries_used` instead.

## Media surface — `/v1/*` (PlayGen DJ integration)

In addition to the OSINT pipeline, info-broker hosts a `/v1/*` REST surface consumed
by the PlayGen DJ microservice. All `/v1/*` endpoints require `X-API-Key` and are
rate-limited via slowapi.

| Endpoint | Purpose |
|---|---|
| `GET /v1/weather` | Current weather for a city or lat/lon (OpenWeatherMap, 10 min TTL) |
| `GET /v1/news` | Top headlines by scope/topic (15 min TTL) |
| `GET /v1/songs/enrich` | Album/year/genre/trivia from MusicBrainz (7-day TTL) |
| `GET /v1/jokes` | Single joke, optionally styled and safety-filtered |
| `POST /v1/songs/source` | Ad-hoc: download audio via yt-dlp; caller supplies S3 credentials inline |
| `POST /v1/playlists/source-audio` | **Batch (PlayGen):** receive a playlist from PlayGen, source all audio, upload to R2, POST results to callback — **planned** |

### PlayGen → info-broker audio sourcing flow (designed 2026-04-23)

The data flow is **inbound**: PlayGen's DJ pipeline calls info-broker, not the reverse.
info-broker does not hold a PlayGen service account and makes no calls back to PlayGen
except via the `callback_url` supplied in each request.

```
PlayGen DJ worker
    │
    │  POST /v1/playlists/source-audio
    │  { station_id, songs: [{song_id, title, artist}], callback_url }
    ▼
info-broker (FastAPI)
    │
    ├── for each song:
    │     yt-dlp  ──→  MP3 download (temp file)
    │     boto3   ──→  Cloudflare R2 upload
    │                  key: songs/{station_id}/{song_id}.mp3
    │                  bucket: ownradio
    │
    └── POST callback_url
        { station_id, results: [{song_id, status, object_key, error}] }
```

**R2 configuration** (server-side env vars — not exposed to callers):

| Env var | Value |
|---|---|
| `R2_BUCKET` | `ownradio` |
| `R2_ENDPOINT` | `https://fa958caa19c273f07b49c49a09d76a60.r2.cloudflarestorage.com` |
| `R2_ACCESS_KEY_ID` | (secret — see `.env`) |
| `R2_SECRET_ACCESS_KEY` | (secret — see `.env`) |

Object key convention: `songs/{stationId}/{songId}.mp3`

The existing `POST /v1/songs/source` endpoint remains for single-song ad-hoc use
where the caller supplies their own S3 target. The new `/v1/playlists/source-audio`
endpoint is purpose-built for the PlayGen batch workflow.

## Phase status

| Phase | Feature | Status |
|---|---|---|
| 1 | ReAct loop (search + scrape + LLM) | Implemented |
| 2 | Episodic memory via Qdrant `user_feedback` | Implemented (live in `analyze_profile_with_react`) |
| 3 | Dynamic few-shot from best/worst grades | Implemented |
| 4 | Critic agent with single retry | Implemented |
| 5 | Fine-tuning export + evaluator | Implemented |
| 6 | Runtime + supply-chain hardening | Implemented (see [../SECURITY.md](../SECURITY.md)) |
| — | `POST /v1/playlists/source-audio` batch endpoint | Planned |
| — | Redis task queue / multi-worker parallelism | Planned / optional |

For the prompt internals, see [agents-and-prompts.md](agents-and-prompts.md).
