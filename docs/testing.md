# Testing

All tests live at the repo root and run under `pytest`. External services (Postgres, Qdrant, LM Studio, the network) are mocked — the suite runs offline.

## Running the suites

```sh
# Full suite
uv run pytest -v

# Individual files
uv run pytest test_grading.py -v
uv run pytest test_security.py -v
uv run pytest test_no_sql_string_formatting.py -v
uv run pytest test_episodic_memory.py -v
uv run pytest test_phases_345.py -v
```

Lint gate (enforces the same SQL-safety rules at lint time):

```sh
uv run ruff check .
```

## `test_grading.py`

Covers `evaluate_grading.calculate_alignment_score` and `evaluate_system_performance`. Verifies the normalization from 1-10 system confidence to a 1-5 scale, the 100%/0% endpoints, partial matches, `None` handling, and the aggregate average. Postgres is mocked via `pytest-mock`: `mocker.patch('evaluate_grading.psycopg2.connect')` replaces the connection and `fetchall.return_value` feeds synthetic rows.

## `test_security.py`

The Phase 6 runtime hardening suite (60+ unit tests plus a few integration cases). Sections cover:

- **SSRF** — `safe_fetch_url` rejects non-http(s) schemes, loopback, RFC1918, link-local/metadata, multicast, and hosts that fail DNS resolution. Uses `unittest.mock.patch` on `socket.getaddrinfo` and `requests.get`.
- **Prompt injection** — `sanitize_for_prompt` strips control chars, caps length, and wraps output in `<<<BEGIN_...>>>` fences.
- **Formula injection** — `escape_spreadsheet_cell` and `escape_dataframe_cells` prepend `'` to cells starting with `= + - @ \t \r`.
- **NUL-byte / oversized fields** — `coerce_db_text` and `scrub_jsonb` strip `\x00` and cap lengths.
- **SQL identifier allow-list** — `is_safe_sql_identifier`.
- **Search query sanitization** — `validate_search_query` strips control chars, collapses whitespace, caps length.
- **Content-Type enforcement** — `safe_fetch_url` honors the `allowed_content_types` allow-list.

## `test_no_sql_string_formatting.py`

Defense-in-depth AST scanner that walks every Python file in the repo and fails the build if any call to `execute`, `executemany`, `read_sql*`, or similar passes an f-string, `.format(...)`, `%` interpolation, or `+` concatenation as the SQL argument. This is the same rule as `ruff`'s `S608`, duplicated as a pytest test so `# noqa` cannot silence it.

## `test_episodic_memory.py`

Phase 2 tests for `save_grading_to_memory`, `recall_similar_mistakes`, and the injection of recalled warnings inside `analyze_profile_with_react`. Mocks the Qdrant client and the LM Studio embedding endpoint — no live services are contacted. Uses `pytest.importorskip('research_agent')` so the suite skips cleanly on systems that do not have the runtime deps installed.

## `test_phases_345.py`

Covers Phase 3 (few-shot injection), Phase 4 (critic agent), and Phase 5 (fine-tune export).

- **Few-shot** — asserts that `fetch_few_shot_examples` returns best/worst pairs from the mocked Postgres cursor and that `_format_few_shot_block` renders them inside sanitization fences.
- **Critic** — asserts that `critic_agent` parses an approval/rejection JSON, that `process_pending_profiles` retries exactly once on rejection, and that critic errors and malformed JSON fail open (return `(True, rationale)`).
- **Fine-tune export** — asserts that `export_dataset.row_to_chat_example` builds the expected `{"messages": [system, user, assistant]}` shape and that `fetch_training_rows` applies the `min_grade` filter.

Mocks use `types.SimpleNamespace` to stand in for `openai` response objects and `unittest.mock.patch` for Postgres / Qdrant clients. Like `test_episodic_memory.py`, the file uses `pytest.importorskip` so it degrades gracefully when runtime deps are missing.
