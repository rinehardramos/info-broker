# Run Exports & Benchmark Reports

Two admin/user-facing reporting surfaces: **downloadable run reports** (PDF / Word / Excel / CSV / JSON) and the **admin Benchmark Reports page**.

---

## Run exports

Every research run can be downloaded as a detailed report via the **Download** menu
(on the run list / result drawer / results panel). Five formats are offered:

| Format | What it contains | Best for |
|--------|------------------|----------|
| **PDF report (detailed)** | Run-info header (query, status, dates, tool-calls, phases, counts) → **ranked candidates** (each with evidence snippets + source URLs) → **full findings** → analysis (entities / relationships / insights) | A shareable human report |
| **Word (.docx)** | Same structure as the PDF, as an editable Word document (headings, run info, ranked candidates, findings, analysis) | Editing / pasting into other docs |
| **Excel (.xlsx)** | Sheets: **Run Info**, **Ranked Candidates**, **Findings**, **Entities**, **Relationships**, **Insights** | Spreadsheet analysis / filtering |
| **CSV** | One row per finding: `rank, title, source_class, url, confidence, phase, content` | Quick import / grep |
| **JSON (full data)** | The complete structured report: `metadata + findings + ranked_candidates + analysis` | Programmatic use / archival |

### How it works

`POST /v3/exports/research/{run_id}` with `{ "format": "pdf|csv|xlsx|json|docx", "include_analysis": true }`
generates the file **synchronously** and returns `{ "filename", "url" }`. The file is
fetched from `GET /v3/exports/files/{filename}` (ephemeral; the URL is the token).
The frontend downloads it as a blob through the authenticated API client.

The export reads the run's `research_trails` row (findings, trail, analysis) plus
`pipeline_runs` metadata (status, started/finished, tool_calls). Findings are passed
through `_normalize_finding`, which maps the real trail shape
(`candidate_name` / `source_url` / `source_class` / `evidence_snippet` / `phase_id`)
onto the export columns — earlier exports were near-empty because the generators read
`title`/`source`/`content`/`url`, which the findings don't use.

> **Note:** PDF text uses `wrapmode="CHAR"` so long unbreakable tokens (e.g. listing
> URLs) don't raise fpdf2's "Not enough horizontal space" error.

### Validated end-to-end

A fresh run (preflight → confirm → engine_v2 → trail, status `succeeded`, 20 findings)
exported cleanly in all five formats: PDF (valid `%PDF-`), DOCX (valid zip), XLSX,
CSV (21 rows — addresses, prices, source URLs, confidence, phase), JSON (metadata +
20 findings + 20 ranked candidates + analysis).

---

## Benchmark Reports (admin)

`/admin/benchmarks` (admin nav → **Benchmark Reports**) surfaces gold-set benchmark
runs: the headline **mean-score rating** + letter grade + a 0-gamed badge, a
run-history selector, a per-item table, aggregate cost stats, severity-ranked
recommendations, and a methodology/analysis section.

### Scoring model

`item_score = coverage × source_quality`, with four anti-gaming guards that **hard-zero**
any run that fabricates from training data, uses unregistered tools, skips phases, or
RAG-shortcuts. So a clean run with 0% gamed is doing real live research.

- `coverage` — fraction of the item's curated authoritative facts matched.
- `source_quality` — best source-class weight: `primary_official`/`live_official` = 1.0,
  `registry` = 0.95, `live_search` = 0.75, `news`/`aggregator`/`social` lower,
  `training` = 0.
- `field_coverage` — fraction of the 10 lead fields surfaced run-wide (enrichment breadth).

### Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/v3/benchmarks/reports` | API-key | Ingest a report (run_benchmark posts here) |
| GET | `/v3/benchmarks/reports` | admin | List run history |
| GET | `/v3/benchmarks/reports/{id}` | admin | Full report |
| POST | `/v3/benchmarks/run` | admin | Trigger a run in the background (single concurrent; 409 if active) |
| GET | `/v3/benchmarks/run/status` | admin | Is a run active? |

### Running the benchmark

- **From the UI:** the **Run benchmark** button spawns a background run (real brain
  time — several minutes per item); the new report appears in the list when done.
- **From the CLI:** `python -m benchmarks.run_benchmark --items <ids> --out-json <path>`.
  Set `BENCHMARK_INGEST_URL=http://localhost:8000` (+ `INFO_BROKER_API_KEY`) to have the
  run POST its report to the page automatically.

### Honest caveats (shown on the page)

- Scores are the **no-key** free-capability baseline unless a run had keys configured.
- Runs are **stochastic** — a single item can swing (e.g. a thin run); trust the trend
  across multiple reports, not one number.
- The leads gold-set is curated (4 items), not a broad statistical sample.
