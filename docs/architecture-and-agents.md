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

## Phase status

| Phase | Feature | Status |
|---|---|---|
| 1 | ReAct loop (search + scrape + LLM) | Implemented |
| 2 | Episodic memory via Qdrant `user_feedback` | Implemented (live in `analyze_profile_with_react`) |
| 3 | Dynamic few-shot from best/worst grades | Implemented |
| 4 | Critic agent with single retry | Implemented |
| 5 | Fine-tuning export + evaluator | Implemented |
| 6 | Runtime + supply-chain hardening | Implemented (see [../SECURITY.md](../SECURITY.md)) |
| — | Redis task queue / multi-worker parallelism | Planned / optional |

For the prompt internals, see [agents-and-prompts.md](agents-and-prompts.md).
