# File Import as Research Source — Design Spec

**Date:** 2026-05-08
**Status:** Draft
**Depends on:** Memory Phase 1 (research_memory collection + writer), IS Brain, RRF Retriever

---

## Problem

The IS brain can only research using web-sourced data from its MCP tools. Users often have existing files (spreadsheets, PDFs, reports, contact lists) that contain critical context for their research. Currently there is no way to feed these files into the research pipeline.

## Solution

Allow users to upload CSV, Excel, PDF, DOCX, and TXT files. Parse them into structured research findings and index them through the existing `index_research_findings()` writer into the `research_memory` Qdrant collection. The existing 5-signal RRF retriever automatically picks them up in future research. No new retrieval infrastructure needed.

## Core Principle

Uploaded files become **first-class research findings** — same pipeline as IS brain results. No separate collection, no new retrieval signals, no conventional RAG. The existing multi-signal fusion architecture handles everything.

---

## Architecture

```
User uploads file (drag-and-drop or button)
        |
        v
  POST /v3/sources/upload (multipart/form-data)
        |
        v
  File Parser (format-specific)
        |
        v
  Findings list: [{title, content, source, confidence}]
        |
        +-- Small (< 2K tokens): also stored for direct prompt injection
        |
        v
  index_research_findings(source_id, filename, findings)  -- existing writer
        |
        v
  Qdrant research_memory  -- existing collection, same vectors
        |
        v
  Available via fused_retrieve()  -- existing 5-signal RRF
```

---

## File Parsing

### Format-specific parsers

| Format | Library | Finding structure |
|--------|---------|-------------------|
| **CSV** | `pandas` | Finding 1: schema summary (columns, types, row count, 5 sample rows). Remaining: groups of 20 rows per finding. |
| **Excel** | `pandas` + `openpyxl` | Same as CSV, per sheet. Sheet name in finding title. |
| **PDF** | `pdfplumber` | One finding per page. Title = "Page N of filename". Tables extracted as Markdown. |
| **DOCX** | `python-docx` | One finding per heading section. Title = heading text. Content = paragraphs under that heading. |
| **TXT** | Built-in | Split by double newlines (paragraphs). Group into ~500 token chunks. |

### Finding fields

Each parsed finding gets:
- `source`: `"file_upload"`
- `confidence`: 85 (user-provided data is trusted by default)
- `title`: descriptive — `"{filename} - Page {N}"` or `"{filename} - {sheet_name} rows {start}-{end}"`
- `content`: parsed text, max 2000 chars per finding (matching existing writer limit)

### Chunking with contextual prefix

Each finding's content is prefixed with context before embedding:

```
[File: quarterly_report.pdf | Page 3 | Section: Revenue Analysis]
Revenue decreased 12% year-over-year due to reduced enterprise contracts...
```

This follows Anthropic's Contextual Retrieval pattern — prevents the "orphan chunk" problem where snippets lose meaning without document context.

### CSV/Excel specific handling

Schema summary finding is always created with:
- Column names and inferred types
- Total row count
- Sample of first 5 rows as a formatted table
- This summary is marked as `confidence: 95` (structural metadata, very reliable)

Row data is chunked in groups of 20 rows per finding, formatted as Markdown tables.

---

## Token Tiers for Prompt Injection

| Total parsed tokens | Prompt injection | Retrieval |
|---------------------|------------------|-----------|
| < 2,000 (~3 pages) | Full content in `{user_sources}` section | Also indexed for future runs |
| >= 2,000 | Manifest only (filename, summary, page/row count) | Full content via RRF retrieval |

The manifest tells the IS brain the file exists and what it contains, so it knows to search for specific details during the RECURSE phase.

---

## Storage

### Processing pipeline

1. **Upload**: file saved to `/tmp/uploads/{user_id}/{source_id}/` for processing
2. **Parse**: extract text, create findings
3. **Index**: `index_research_findings()` writes to Qdrant
4. **Archive**: upload raw file to S3/R2 (if configured via env vars)
5. **Cleanup**: remove `/tmp` copy after indexing

### S3/R2 archive (optional)

Uses the existing `upload_to_s3()` from `app/adapters/s3_upload.py`. If S3 credentials are not configured, files remain in `/tmp` only (acceptable for single-server deployments).

---

## Database Schema

### New table: `research_sources`

```sql
CREATE TABLE IF NOT EXISTS research_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES ui_users(id) ON DELETE CASCADE,
    run_id UUID,
    filename TEXT NOT NULL,
    file_type VARCHAR(16) NOT NULL,
    file_size_bytes INT,
    token_count INT,
    findings_count INT DEFAULT 0,
    s3_key TEXT,
    manifest JSONB,
    status VARCHAR(32) NOT NULL DEFAULT 'processing',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_research_sources_user ON research_sources(user_id);
CREATE INDEX IF NOT EXISTS idx_research_sources_status ON research_sources(status);
```

**Status values:** `processing` | `indexed` | `failed`

**Manifest JSONB** (varies by file type):
```json
{
    "type": "csv",
    "columns": ["name", "email", "company"],
    "row_count": 500,
    "sheet_count": 1,
    "summary": "Contact list with 500 entries...",
    "sample_rows": [["John Doe", "john@acme.com", "Acme Corp"], ...]
}
```

---

## API Endpoints

All endpoints require authentication via `Depends(get_current_user)`.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v3/sources/upload` | Upload file (multipart/form-data). Accepts file + optional `run_id`. Returns `{source_id, filename, status}`. Parsing runs async. |
| `GET` | `/v3/sources` | List user's uploaded sources. Returns metadata + findings_count. |
| `GET` | `/v3/sources/{id}` | Get source details including manifest and status. |
| `GET` | `/v3/sources/{id}/findings` | Preview the parsed findings (first 20). |
| `DELETE` | `/v3/sources/{id}` | Delete source metadata. Findings remain in Qdrant (they are research memory now). |

### Upload endpoint details

```
POST /v3/sources/upload
Content-Type: multipart/form-data

Fields:
  file: <binary file>
  run_id: <optional UUID, links to a research run>

Response:
  {
    "source_id": "uuid",
    "filename": "report.pdf",
    "file_type": "pdf",
    "file_size_bytes": 234567,
    "status": "processing"
  }
```

Max file size: 50 MB. Accepted extensions: `.csv`, `.xlsx`, `.xls`, `.pdf`, `.doc`, `.docx`, `.txt`.

### Async processing

File parsing and indexing runs as a background task (`asyncio.create_task`). The upload endpoint returns immediately with `status: "processing"`. Frontend polls `/v3/sources/{id}` for completion, or listens for a `source.indexed` WebSocket event.

---

## IS Brain Integration

### Prompt injection

`build_prompt()` in `is_prompt.py` gains a `{user_sources}` placeholder inserted after `{context_section}`.

For small files (< 2K tokens total):
```
## USER-PROVIDED SOURCES

[File: contacts.csv | 50 rows | 12 columns]
name,email,company,title,location
John Doe,john@acme.com,Acme Corp,CEO,Manila
Jane Smith,jane@widgets.com,Widgets Inc,CTO,Cebu
... (full content)
```

For large files (>= 2K tokens):
```
## USER-PROVIDED SOURCES

[File: quarterly_report.pdf | 142 pages | 38,000 tokens]
Topics: financial results, executive team, risk factors, market outlook
This file has been indexed in your research memory. Search for specific details using your tools.

[File: competitor_list.xlsx | 3 sheets | 2,400 rows]
Sheets: Companies (800 rows), Contacts (1200 rows), Deals (400 rows)
Columns [Companies]: name, industry, revenue, employees, location
This file has been indexed. Query specific rows via your research tools.
```

### Agent endpoint wiring

In `app/routers/v3/agent.py`, before calling `_run_is_research`:
1. Fetch user's active sources: `SELECT * FROM research_sources WHERE user_id = %s AND status = 'indexed'`
2. Build `user_sources` string from manifests
3. For small files, include full content
4. Pass to `run_research(user_sources=user_sources)`

---

## Frontend

### FileUploadZone component

Located above the chat input in AgentChat. Features:
- Drag-and-drop zone with file icon
- Click to browse
- Accepted types: .csv, .xlsx, .xls, .pdf, .doc, .docx, .txt
- Upload progress bar
- After parsing: chip/badge showing "report.pdf (42 findings)"
- Click chip to see findings preview
- X button to remove source

### WebSocket events

| Event | When | Payload |
|-------|------|---------|
| `source.processing` | Upload received | `{source_id, filename}` |
| `source.indexed` | Parsing + indexing complete | `{source_id, filename, findings_count, token_count}` |
| `source.failed` | Parsing failed | `{source_id, filename, error}` |

---

## New Dependencies

| Package | Purpose | Install |
|---------|---------|---------|
| `pdfplumber` | PDF text + table extraction | `uv add pdfplumber` |
| `python-docx` | DOCX paragraph extraction | `uv add python-docx` |

`pandas` and `openpyxl` already installed.

---

## New/Modified Files

### New files

| File | Purpose |
|------|---------|
| `app/sources/parser.py` | Format-specific parsing: PDF, DOCX, CSV, Excel, TXT to findings |
| `app/sources/__init__.py` | Package init |
| `app/routers/v3/sources_api.py` | Upload, list, delete, preview API |
| `tests/sources/test_parser.py` | Parser unit tests per format |
| `frontend/src/components/chat/FileUploadZone.tsx` | Drag-and-drop upload UI |

### Modified files

| File | Change |
|------|--------|
| `app/routers/v3/db.py` | Add `research_sources` table |
| `app/main.py` | Register sources_api router |
| `app/is_prompt.py` | Add `{user_sources}` placeholder |
| `app/is_brain.py` | Pass `user_sources` to `build_prompt()` |
| `app/routers/v3/agent.py` | Fetch user sources and inject into IS brain |
| `frontend/src/components/agent/AgentChat.tsx` | Add FileUploadZone above input |
| `pyproject.toml` | Add `pdfplumber`, `python-docx` |

---

## Testing Strategy

### Unit tests (test_parser.py)
- CSV: parse simple CSV, verify schema summary + row findings
- Excel: parse multi-sheet, verify per-sheet findings
- PDF: parse multi-page, verify page findings + table extraction
- DOCX: parse with headings, verify section findings
- TXT: parse with paragraphs, verify chunking
- Edge cases: empty file, binary garbage, huge file (> 50MB rejected)
- Token counting: verify tier classification (small vs large)

### Integration tests
- Upload file -> parse -> verify findings in Qdrant
- Upload CSV -> run IS research -> verify brain sees file content
- Delete source -> verify metadata removed

---

## Scope Boundaries

**In scope:**
- File upload API (multipart/form-data)
- Parsing: CSV, Excel, PDF, DOCX, TXT
- Indexing parsed findings into existing research_memory
- Prompt injection (small files: full content; large files: manifest)
- Frontend drag-and-drop upload zone
- S3/R2 archival (optional, based on env vars)
- research_sources PG table for metadata

**Out of scope:**
- Image/OCR extraction from PDFs (future enhancement)
- PowerPoint (.pptx) parsing
- Audio/video file transcription
- Real-time collaborative file editing
- File versioning
