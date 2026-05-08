# File Import as Research Source — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:[REDACTED:high-entropy-base64:27ch:hash=88f76bb3] (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow users to upload CSV, Excel, PDF, DOCX, and TXT files that get parsed into research findings and indexed into the existing research_memory collection for IS brain retrieval.

**Architecture:** Files are parsed into structured findings by format-specific parsers, indexed via the existing `index_research_findings()` writer into Qdrant research_memory, and automatically available via 5-signal RRF retrieval. Small files also get injected directly into the IS brain prompt.

**Tech Stack:** Python (pdfplumber, python-docx, pandas), FastAPI (upload endpoints), React (drag-and-drop UI)

---

### Task 1: Dependencies + Database Schema

**Files:**
- Modify: `pyproject.toml`
- Modify: `app/routers/v3/db.py`

- [ ] Add `pdfplumber` and `python-docx` to pyproject.toml dependencies
- [ ] Run `uv add pdfplumber python-docx`
- [ ] Add `research_sources` table to db.py migration string (before mcp_sessions). Columns: id UUID PK, user_id UUID FK, run_id UUID, filename TEXT, file_type VARCHAR(16), file_size_bytes INT, token_count INT, findings_count INT DEFAULT 0, s3_key TEXT, manifest JSONB, status VARCHAR(32) DEFAULT 'processing', created_at TIMESTAMPTZ DEFAULT now(). Indexes on user_id and status.
- [ ] Run tests: `uv run pytest tests/ -q --tb=short --ignore=tests/v3 --ignore=tests/e2e`
- [ ] Commit: `git add pyproject.toml uv.lock app/routers/v3/db.py && git commit -m "deps+schema: add pdfplumber, python-docx, research_sources table"`

---

### Task 2: File Parser — TXT + CSV (TDD)

**Files:**
- Create: `app/sources/__init__.py`
- Create: `app/sources/parser.py`
- Create: `tests/sources/test_parser.py`

- [ ] Write failing tests for TXT and CSV parsing:
  - `parse_txt(content, filename)` returns list of findings. Each finding has title, content, source="file_upload", confidence=85.
  - TXT: splits on double newlines, groups into ~500 token chunks
  - `parse_csv(file_path, filename)` returns findings. First finding is schema summary (confidence=95). Remaining are row groups of 20.
  - CSV schema summary includes column names, row count, sample 5 rows
  - Empty file returns empty list
  - `estimate_tokens(text)` returns rough token count (len/4)
- [ ] Run tests -- verify FAIL
- [ ] Implement `app/sources/__init__.py` (empty) and `app/sources/parser.py` with:
  - `estimate_tokens(text: str) -> int` — `len(text) // 4`
  - `parse_txt(content: str, filename: str) -> list[dict]` — split paragraphs, chunk to ~500 tokens
  - `parse_csv(file_path: str, filename: str) -> list[dict]` — pandas read, schema summary + row groups
  - Each finding gets contextual prefix: `[File: {filename} | {context}]`
- [ ] Run tests -- verify PASS
- [ ] Commit: `git add app/sources/ tests/sources/ && git commit -m "feat(sources): add TXT and CSV file parsers with contextual prefix"`

---

### Task 3: File Parser — Excel, PDF, DOCX (TDD)

**Files:**
- Modify: `app/sources/parser.py`
- Modify: `tests/sources/test_parser.py`

- [ ] Write failing tests:
  - `parse_excel(file_path, filename)` — same as CSV but per sheet, sheet name in title
  - `parse_pdf(file_path, filename)` — one finding per page, tables as Markdown
  - `parse_docx(file_path, filename)` — one finding per heading section
  - `parse_file(file_path, filename)` — dispatcher that routes by extension
  - Edge: unsupported extension raises ValueError
- [ ] Run tests -- verify FAIL
- [ ] Implement:
  - `parse_excel(file_path, filename)` — pandas per sheet, reuse CSV logic
  - `parse_pdf(file_path, filename)` — pdfplumber, page text + tables
  - `parse_docx(file_path, filename)` — python-docx, heading sections
  - `parse_file(file_path, filename)` — extension dispatcher
- [ ] Run tests -- verify PASS
- [ ] Commit: `git add app/sources/parser.py tests/sources/test_parser.py && git commit -m "feat(sources): add Excel, PDF, DOCX parsers and format dispatcher"`

---

### Task 4: Sources REST API

**Files:**
- Create: `app/routers/v3/sources_api.py`

- [ ] Create router with prefix="/v3/sources", tag="v3-sources". Endpoints:
  - `POST /upload` — accepts `UploadFile` + optional `run_id` Form field. Saves to /tmp/uploads/{user_id}/{source_id}/. Inserts research_sources row with status=processing. Launches background task for parsing+indexing. Returns {source_id, filename, file_type, status}.
  - `GET /` — list user's sources. Returns research_sources rows.
  - `GET /{id}` — get source details.
  - `GET /{id}/findings` — fetch first 20 findings from Qdrant filtered by source_id in payload.
  - `DELETE /{id}` — delete metadata row. (Findings stay in Qdrant — they are memory now.)
  - Background task `_process_source(source_id, user_id, file_path, filename)`:
    1. Parse file via `parse_file()`
    2. Index via `index_research_findings(source_id, filename, findings)`
    3. Update research_sources: status=indexed, findings_count, token_count, manifest
    4. Push WS event source.indexed
    5. On error: status=failed, push source.failed
  - Validate: max 50MB, accepted extensions only
- [ ] Register router in app/main.py (import + include_router)
- [ ] Commit: `git add app/routers/v3/sources_api.py app/main.py && git commit -m "feat(sources): add upload, list, delete API with async parsing"`

---

### Task 5: IS Brain Integration — user_sources prompt

**Files:**
- Modify: `app/is_prompt.py`
- Modify: `app/is_brain.py`
- Modify: `app/routers/v3/agent.py`

- [ ] In `app/is_prompt.py`: add `{user_sources}` placeholder after `{context_section}` in the RESEARCH_PROMPT. Add `user_sources: str = ""` param to `build_prompt()` and pass to `.format()`.
- [ ] In `app/is_brain.py`: add `user_sources: str = ""` param to `run_research()`, pass through to `build_prompt()`.
- [ ] In `app/routers/v3/agent.py`, in `_run_is_research` before calling run_research:
  - Query: `SELECT * FROM research_sources WHERE user_id = %s AND status = 'indexed' ORDER BY created_at DESC`
  - For each source, build a manifest line: `[File: {filename} | {file_type} | {findings_count} findings]`
  - For small sources (token_count < 2000), fetch and include full parsed content
  - For large sources, include manifest + summary only
  - Pass combined string as `user_sources=` to run_research
- [ ] Run tests: `uv run pytest tests/ -q --tb=short --ignore=tests/v3 --ignore=tests/e2e`
- [ ] Commit: `git add app/is_prompt.py app/is_brain.py app/routers/v3/agent.py && git commit -m "feat(sources): inject uploaded file context into IS brain prompt"`

---

### Task 6: Frontend — FileUploadZone

**Files:**
- Create: `frontend/src/components/chat/FileUploadZone.tsx`
- Modify: `frontend/src/components/agent/AgentChat.tsx`

- [ ] Create FileUploadZone component:
  - Drag-and-drop zone with file icon (use lucide-react Upload icon)
  - Click to browse (hidden input[type=file])
  - Accept: .csv,.xlsx,.xls,.pdf,.doc,.docx,.txt
  - On file select: POST /v3/sources/upload as FormData
  - Show upload progress
  - After upload: show chip with filename + "processing..."
  - On WS event source.indexed: update chip to "filename (N findings)"
  - On WS event source.failed: show error chip
  - X button on each chip calls DELETE /v3/sources/{id}
  - Compact design: single row of file chips, expandable drop zone
- [ ] In AgentChat.tsx: import and render FileUploadZone above the chat input textarea. Add WS event handlers for source.processing, source.indexed, source.failed.
- [ ] Commit: `git add frontend/src/components/chat/FileUploadZone.tsx frontend/src/components/agent/AgentChat.tsx && git commit -m "feat(fe): add drag-and-drop file upload zone in chat"`

---

### Task 7: Integration Test + Docker Deploy

- [ ] Run all unit tests: `uv run pytest tests/ -q --tb=short --ignore=tests/v3 --ignore=tests/e2e`
  Expected: 748+ existing + ~20 new parser tests, all pass
- [ ] Docker build: `docker compose build info-broker-api frontend`
- [ ] Docker deploy: `docker compose up -d`
- [ ] Verify upload endpoint works:
  ```bash
  echo "name,email\nJohn,john@test.com\nJane,jane@test.com" > /tmp/test.csv
  TOKEN=$(curl -s -X POST localhost:8000/v3/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
  curl -X POST -H "Authorization: Bearer $TOKEN" -F "file=@/tmp/test.csv" localhost:8000/v3/sources/upload
  ```
  Expected: {source_id, filename: "test.csv", file_type: "csv", status: "processing"}
- [ ] Wait 5s, verify source is indexed: `curl -H "Authorization: Bearer $TOKEN" localhost:8000/v3/sources`
- [ ] Push: `git push origin main`
