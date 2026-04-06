# Auto Marketer: Phase Implementation TODO

This document details the roadmap for making the Auto Marketer AI agent self-improving. Multiple agents can work on these tickets in parallel, provided they update `tasks/agent-collab.md` first.

## Phase 1: Iterative Search & Self-Correction (Immediate)
- **Goal:** Implement a ReAct (Reason + Act) loop. The LLM should choose search queries dynamically instead of using a hardcoded search.
- **Tasks:**
  - Update `research_agent.py` to allow the LLM to call the `search_web` tool dynamically.
  - Wrap the search/analysis phase in a loop.
  - Ensure the agent evaluates if it has enough context before finalizing the JSON.
- **Dependencies:** None.

## Phase 2: Episodic Memory via Qdrant (Short-Term)
- **Goal:** Give the agent memory of its past mistakes using the vector database.
- **Tasks:**
  - Create a new Qdrant collection for `user_feedback`.
  - Write logic so that when a profile is graded (especially low grades), the profile context + feedback text is embedded and saved to Qdrant.
  - In `research_agent.py`, query Qdrant for similar past profiles before sending the prompt to the LLM.
  - Append relevant past feedback to the system prompt as "Warnings from past mistakes".
- **Dependencies:** Depends on grading data existing in Postgres.

## Phase 3: Dynamic Few-Shot Prompting (Medium-Term)
- **Goal:** Inject 5/5 and 1/5 examples into the prompt dynamically.
- **Tasks:**
  - Write a query in `research_agent.py` to fetch one perfect example and one failed example from Postgres.
  - Append these examples to the system prompt.
  - Ensure token limits are respected.
- **Dependencies:** Depends on graded data existing in Postgres.

## Phase 4: Multi-Agent Debate / Critic Pattern (Medium-Term)
- **Goal:** Introduce a secondary LLM call to double-check the work against historical feedback.
- **Tasks:**
  - Create a Critic Agent function that takes the Researcher's JSON and historical feedback as input.
  - The Critic should output a boolean (Approve/Reject) and a rationale.
  - Implement a retry loop (max 1-2 times) if the Critic rejects the initial analysis.
- **Dependencies:** Best implemented after Phase 2 or 3.

## Phase 5: Automated Fine-Tuning (Long-Term)
- **Goal:** Train the underlying model weights using highly graded data.
- **Tasks:**
  - Create a script (`export_dataset.py`) to dump 4/5 and 5/5 profiles into JSONL format.
  - Document the fine-tuning process.
  - Create an evaluation script to run the fine-tuned model against the base model using the `test_grading.py` suite.
- **Dependencies:** Requires a significant dataset of graded profiles (100+).

## Phase 6: Security — Sanitize Untrusted Data (Immediate)
- **Goal:** Treat all data flowing in from third parties (Apify/LinkedIn raw fields, DuckDuckGo search results, scraped web pages, LLM output, user CLI input) as untrusted, and sanitize it before it reaches the LLM, the network, or exported spreadsheets.
- **Threat model:**
  - **SSRF:** `scrape_url` and the Apify dataset fetch follow arbitrary URLs. Without host validation an attacker can pivot to `127.0.0.1`, RFC1918 ranges, or cloud-metadata IPs (`169.254.169.254`).
  - **Prompt injection:** Scraped page text and LinkedIn `headline`/`about` fields are concatenated directly into system/user messages, letting attacker-controlled content rewrite the agent's instructions or exfiltrate data via crafted search queries.
  - **CSV/XLSX formula injection:** Cells beginning with `=`, `+`, `-`, `@`, `\t`, or `\r` are executed as formulas by Excel/Sheets when an analyst opens an export.
  - **SQL / DB attacks:** All current queries are parameterized, but PostgreSQL TEXT/JSONB rejects `\x00`, identifier-injection is a risk for any future dynamic ALTER/SELECT, and oversized field values can DoS psycopg2, Qdrant, and the embedding model.
  - **Hostile ingestion payloads:** Apify (or anything proxied by `APIFY_DATASET_URL`) is third-party data. Unbounded `response.json()` is a memory-DoS, non-string field types crash the cursor, and a megabyte `about` field can lock the local embedding model.
  - **Scraping attacks:** A scraped URL may return non-HTML (binary, huge JSON, parser bombs); BeautifulSoup will happily try to parse it. LLM-supplied search queries can be unbounded or contain control characters.
  - **Untrusted CLI input:** `interactive_grading` writes raw `input()` straight into Postgres — needs NUL scrub + length cap.
- **Tasks:**
  - Shared `security.py` with `safe_fetch_url` (scheme allow-list, DNS-time private/loopback/link-local block, redirect off, body cap, optional Content-Type allow-list), `sanitize_for_prompt`, `escape_spreadsheet_cell` / `escape_dataframe_cells`, `coerce_db_text`, `scrub_jsonb`, `validate_search_query`, and `is_safe_sql_identifier`.
  - `research_agent.py`: SSRF guard + HTML Content-Type check on `scrape_url`; sanitize all untrusted strings before they reach the LLM; defensive system-prompt clause; validate LLM-chosen DDG queries; coerce CLI feedback before INSERT.
  - `ingest.py`: route the Apify fetch through `safe_fetch_url` (50 MiB cap, JSON Content-Type required); reject non-list payloads; coerce every profile field with `coerce_db_text`; `scrub_jsonb` before writing JSONB; cap embedding input length.
  - `export_data.py` / `generate_emails.py`: pass every export DataFrame through `escape_dataframe_cells`.
  - All SQL stays parameterized; `is_safe_sql_identifier` is the gate any future dynamic identifier interpolation must pass.
- **Dependencies:** None.
