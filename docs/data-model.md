# Data model

Auto Marketer stores canonical state in PostgreSQL and secondary vector state in Qdrant.

## Postgres: `linkedin_profiles`

Created on first ingest by `ingest.py`, extended with research/grading columns by `research_agent.py`, and further extended with a `generated_email` column by `generate_emails.py`. All migrations use idempotent `CREATE TABLE IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` statements, so it is safe to re-run any script.

| Column | Type | Source | Meaning |
|---|---|---|---|
| `id` | `VARCHAR PRIMARY KEY` | Apify `id` | Upstream LinkedIn profile identifier. Capped at 128 chars. |
| `first_name` | `VARCHAR` | Apify `firstName` | Capped at 256 chars via `coerce_db_text`. |
| `last_name` | `VARCHAR` | Apify `lastName` | Capped at 256 chars. |
| `headline` | `TEXT` | Apify `headline` | Capped at 1024 chars. |
| `about` | `TEXT` | Apify `about` | Capped at 8000 chars. |
| `raw_data` | `JSONB` | Apify profile | Full raw object, NUL-scrubbed with `scrub_jsonb`. |
| `research_status` | `VARCHAR` | agent | `pending` (default), `researching`, `completed`, or `failed`. |
| `is_smb` | `BOOLEAN` | agent | True when the prospect is judged to be an SMB owner. |
| `needs_outsourcing_prob` | `DECIMAL` | agent | 0.0-1.0 probability the prospect needs outsourcing help. |
| `needs_cheap_labor_prob` | `DECIMAL` | agent | 0.0-1.0 probability the prospect needs lower-cost labor. |
| `searching_vendors_prob` | `DECIMAL` | agent | 0.0-1.0 probability the prospect is actively searching. |
| `research_summary` | `TEXT` | agent | Prose summary the critic and grader review. |
| `system_confidence_score` | `INT` | agent | 1-10, clamped in-code if the model emits percentages. |
| `confidence_rationale` | `TEXT` | agent | Why the agent picked that confidence. |
| `search_queries_used` | `TEXT` | agent | ` \| `-joined list of DuckDuckGo queries used for this profile. |
| `user_grade` | `INT` | human | 1-5 grade from `research_agent.py --grade`. |
| `user_feedback` | `TEXT` | human | Free-text correction, capped at 4000 chars. |
| `generated_email` | `TEXT` | `generate_emails.py` | LLM-generated cold-email subject + body for SMB prospects. |

Primary key is `id`; inserts use `ON CONFLICT (id) DO NOTHING` so replaying ingests is idempotent. All writes go through parameterized queries — see `test_no_sql_string_formatting.py` for the AST enforcement.

## Qdrant collections

Qdrant runs at `QDRANT_HOST:QDRANT_PORT` (default `localhost:6335` when using `docker-compose.yml`). Both collections use 768-dim vectors with cosine distance; the dimension must match your LM Studio embedding model.

### `linkedin_profiles` (semantic search)

- Created by `ingest.py` via `setup_qdrant`.
- Vector: embedding of `"{first_name} {last_name}\nHeadline: {headline}\nAbout: {about}"`, truncated to `DEFAULT_EMBEDDING_INPUT_MAX` (4000) characters.
- Point ID: `uuid.uuid5(uuid.NAMESPACE_DNS, profile_id)`.
- Payload: `apify_id`, `first_name`, `last_name`, `headline`.
- Purpose: nearest-neighbor lookup by persona.

### `user_feedback` (episodic memory)

- Created on first grade by `research_agent.py` via `setup_feedback_collection`.
- Vector: embedding of the grading text (`profile_text` + `Grade: N/5` + feedback).
- Point ID: `uuid.uuid5(uuid.NAMESPACE_DNS, profile_id)`.
- Payload: `profile_id`, `profile_text` (≤2000 chars), `grade` (int), `feedback` (≤2000 chars).
- Recall: `recall_similar_mistakes` returns the top-K hits filtered to `grade <= LOW_GRADE_THRESHOLD` (3). Results are injected into the researcher's system prompt as warnings.

## Export formats

`export_data.py` reads profiles with `research_status IN ('completed', 'failed')` and writes JSON, CSV, or XLSX in one of two modes.

### `--mode full`

Every column of `linkedin_profiles` plus every flattened `raw_data.*` key prefixed `apify_`. Use when you need the full Apify payload per row.

### `--mode light`

Every column of `linkedin_profiles` except `raw_data`, plus these derived columns:

- `apify_linkedinUrl`
- `apify_emails` (comma-joined list of email strings)
- `apify_companyWebsites` (comma-joined list of URLs)
- `apify_connectionsCount`
- `apify_currentCompany` (first entry of `raw_data.currentPosition`)

CSV and XLSX output is passed through `escape_dataframe_cells` so cells beginning with `= + - @ \t \r` get a leading single quote to neutralize spreadsheet formula injection. JSON output is not escaped (spreadsheets don't parse it).

`generate_emails.py` uses its own lightweight export that includes `generated_email`, `linkedin_url`, `emails`, `company_websites`, and `company_name`, filtered to profiles with a non-null `generated_email`.

## Fine-tuning dataset

`export_dataset.py` produces a JSONL of OpenAI chat-format training examples. See [fine-tuning.md](fine-tuning.md) for the full workflow and [agents-and-prompts.md](agents-and-prompts.md) for how the training system prompt mirrors the inference prompt.
