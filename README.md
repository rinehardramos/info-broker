# info-broker

Information-gathering and OSINT research service exposed as a REST API.

> This project is **derived from** `auto-marketer-project` with the
> marketing/outreach code paths removed (no more email generation or
> campaign exports). What remains — Apify ingestion, ReAct-driven web
> research, critic-gated grading, episodic memory, and Qdrant semantic
> search — is now wrapped in a small FastAPI app so other services can
> call it over HTTP.

## What it does

- **Ingests** LinkedIn profile data from an Apify dataset into Postgres + Qdrant.
- **Researches** each profile with a local LLM via a ReAct loop (DuckDuckGo + scrape).
- **Critic-gates** every analysis with a second LLM pass and one retry.
- **Remembers** past human grades as episodic memory and injects them into future prompts.
- **Searches** ingested profiles semantically via Qdrant.
- **Exposes** all of the above behind an `X-API-Key`-protected REST API.

## Quickstart

```bash
cp .env.example .env
# Edit .env: set INFO_BROKER_API_KEY and APIFY_DATASET_URL
docker compose up -d
# API is now on http://localhost:8000
# Interactive docs (Swagger): http://localhost:8000/docs
```

Or run locally with uv:

```bash
uv sync --extra dev
uv run uvicorn app.main:app --reload
```

## API endpoints

All endpoints except `/healthz` require the `X-API-Key` header.

### OSINT / profile surface

| Method | Path                          | Purpose                                  |
|--------|-------------------------------|------------------------------------------|
| GET    | `/healthz`                    | Liveness probe (no auth)                 |
| GET    | `/profiles`                   | List ingested profiles (paginated)       |
| GET    | `/profiles/{id}`              | Profile detail + research status         |
| GET    | `/profiles/{id}/raw`          | Raw scraped JSON for a profile           |
| POST   | `/ingest`                     | Pull a fresh batch from Apify            |
| POST   | `/research`                   | Run the research agent on pending rows   |
| POST   | `/profiles/{id}/grade`        | Save a 1-5 grade + feedback              |
| POST   | `/search`                     | Semantic search via Qdrant               |

### Media surface — `/v1/*` (consumed by PlayGen DJ)

| Method | Path                              | Purpose                                                                 |
|--------|-----------------------------------|-------------------------------------------------------------------------|
| GET    | `/v1/weather`                     | Current weather for a city or lat/lon (OpenWeatherMap, 10 min TTL)      |
| GET    | `/v1/news`                        | Top headlines by scope/topic (15 min TTL)                               |
| GET    | `/v1/songs/enrich`                | Album/year/genre/trivia from MusicBrainz (7-day TTL)                    |
| GET    | `/v1/jokes`                       | A single joke, optionally styled and safety-filtered                    |
| POST   | `/v1/songs/source`                | Ad-hoc audio download via yt-dlp; caller supplies S3 credentials inline |
| POST   | `/v1/playlists/source-audio`      | **Planned.** Batch audio sourcing from PlayGen; uploads to R2, POSTs callback |

### PlayGen → info-broker audio sourcing

info-broker is the **receiver** in this integration. PlayGen's DJ pipeline POSTs a
playlist to `/v1/playlists/source-audio`; info-broker downloads audio via yt-dlp,
uploads each file to the `ownradio` Cloudflare R2 bucket under key
`songs/{station_id}/{song_id}.mp3`, and then POSTs results back to the caller's
`callback_url`. info-broker does not call the PlayGen API and holds no PlayGen
service account. See [`docs/architecture-and-agents.md`](docs/architecture-and-agents.md)
for the full flow diagram.

### curl examples

```bash
KEY=replace-with-your-key
BASE=http://localhost:8000

curl -s $BASE/healthz

curl -s -H "X-API-Key: $KEY" "$BASE/profiles?limit=10"

curl -s -H "X-API-Key: $KEY" "$BASE/profiles/abc123"

curl -s -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"overwrite": false}' "$BASE/ingest"

curl -s -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"limit": 5}' "$BASE/research"

curl -s -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"grade": 4, "feedback": "good summary"}' \
  "$BASE/profiles/abc123/grade"

curl -s -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"query": "fintech founder San Francisco", "limit": 10}' \
  "$BASE/search"
```

## Security

See [`SECURITY.md`](./SECURITY.md) for the threat model and supply-chain
controls. All SQL is parameterized (psycopg2 `%s`), all untrusted text
flows through `security.py` sanitizers, and `ruff S608` blocks any
attempt to reintroduce string-built SQL.

## Tests

```bash
uv run pytest -v
```
