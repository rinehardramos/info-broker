# Getting started

This guide takes a fresh checkout to a working pipeline: ingest, research, and grade one profile end-to-end.

## Prerequisites

- Python 3.10 or newer.
- [`uv`](https://github.com/astral-sh/uv) package manager.
- Docker Desktop (or any Docker Engine) for Postgres and Qdrant.
- A **Gemini API key** (`GEMINI_API_KEY`) for the default `google` provider, which uses `gemini-2.5-pro` for chat and `text-embedding-004` (768-dim) for embeddings. Alternatively, set `LLM_PROVIDER=lmstudio` and run [LM Studio](https://lmstudio.ai/) locally with a 768-dim embedding model.
- An Apify dataset URL containing LinkedIn profiles in the shape the ingest script expects (`id`, `firstName`, `lastName`, `headline`, `about`, `currentPosition`, `emails`, `companyWebsites`, etc.).

## 1. Clone and install

```sh
git clone <repo-url> auto-marketer-project
cd auto-marketer-project
uv sync --frozen --extra dev
```

`--frozen` fails if `uv.lock` is out of date and verifies every wheel hash. `--extra dev` pulls in `pytest`, `pytest-mock`, `ruff`, and `pip-audit`.

## 2. Start Postgres and Qdrant

```sh
docker compose up -d
```

`docker-compose.yml` maps Postgres to host port **5433** and Qdrant's HTTP API to host port **6335** (gRPC on 6336). The containers keep data in named volumes `postgres_data` and `qdrant_data`.

## 3. Configure LLM provider

The default provider is **Google Gemini**. Set `GEMINI_API_KEY` in your `.env` and you're done — no local server needed.

To use LM Studio instead, set `LLM_PROVIDER=lmstudio` and:
1. Load a chat-capable model and an embedding model that returns 768-dim vectors.
2. Start the local server from the LM Studio UI (default `http://localhost:1234/v1`).

## 4. Create `.env`

Create a `.env` file in the repo root with the variables below. Every variable here is read by one or more scripts in the repo (`ingest.py`, `research_agent.py`, `export_data.py`, `export_dataset.py`, `generate_emails.py`, `evaluate_finetuned.py`, `evaluate_grading.py`).

```sh
# --- Apify ---
APIFY_DATASET_URL=https://api.apify.com/v2/datasets/<dataset-id>/items?token=<token>

# --- LLM provider (google = Gemini, lmstudio = local LM Studio) ---
LLM_PROVIDER=google
GEMINI_API_KEY=your-gemini-api-key

# --- LM Studio (only needed when LLM_PROVIDER=lmstudio) ---
# LM_STUDIO_BASE_URL=http://localhost:1234/v1
# LM_STUDIO_API_KEY=lm-studio
# CHAT_MODEL_NAME=mistralai/mistral-nemo-instruct-2407
# EMBEDDING_MODEL_NAME=text-embedding-nomic-embed-text-v2-moe

# Only needed for Phase 5 evaluation:
FINETUNED_MODEL_NAME=local-model-ft

# --- Postgres (matches docker-compose.yml) ---
POSTGRES_DB=info_broker
POSTGRES_USER=user
POSTGRES_PASSWORD=password
POSTGRES_HOST=localhost
POSTGRES_PORT=5433

# --- Qdrant ---
QDRANT_HOST=localhost
QDRANT_PORT=6335
```

Note: `research_agent.py` and `export_dataset.py` default `POSTGRES_PORT` to `5432` if unset; `export_data.py` and `generate_emails.py` default to `5433`. Set the variable explicitly to avoid the mismatch.

## 5. First ingest

```sh
uv run python ingest.py
```

This creates the `linkedin_profiles` table in Postgres if missing, creates the `linkedin_profiles` Qdrant collection (768-dim, cosine) if missing, fetches the Apify dataset through `safe_fetch_url` (SSRF-checked, 50 MiB cap), and writes rows plus embeddings. Rows land with `research_status = 'pending'`.

## 6. First research run

```sh
uv run python research_agent.py --run
```

Pulls up to 5 pending profiles, runs the ReAct loop (max 3 searches + 1 final answer per profile), invokes the critic agent, and writes the analysis back to Postgres. On failure the row is marked `research_status = 'failed'`.

## 7. Grade the results

```sh
uv run python research_agent.py --grade
```

Shows one ungraded completed profile at a time, prompts for a 1-5 grade and optional free-text feedback, writes the grade to Postgres, and embeds the graded record into the Qdrant `user_feedback` collection so future runs can recall it.

If you already have historical grades sitting in Postgres but no entries in `user_feedback`, seed the memory once:

```sh
uv run python research_agent.py --backfill-memory
```

## Next steps

- [operations.md](operations.md) for running the pipeline on a schedule.
- [agents-and-prompts.md](agents-and-prompts.md) for how the ReAct loop, critic, and memory interact.
- [fine-tuning.md](fine-tuning.md) once you have ~100 profiles graded 4/5 or 5/5.
