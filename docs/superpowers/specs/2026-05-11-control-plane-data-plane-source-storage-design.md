# Control Plane / Data Plane Storage Boundary — Design Spec

**Date:** 2026-05-11
**Status:** Draft, Phase 1 implemented for tabular source uploads
**Depends on:** File Import as Research Source, IS Brain, MCP `query_uploaded_data`

---

## Problem

Uploaded files and user-specific outputs are research data, not system infrastructure. Storing raw rows, long chat histories, run outputs, extracted document text, and enrichment payloads directly in the same Postgres database used for users, sessions, pipelines, and settings creates three problems:

1. Large files can exceed API memory when parsed as in-memory data frames or rendered into Markdown chunks.
2. System tables become polluted with tenant/client data that has different retention, access, and scaling requirements.
3. Querying row-level or passage-level source data through vector memory alone loses structure and makes enrichment unreliable.

The failure case for run `7194102c-55dc-4ec1-9fd5-105f2d148cb5` came from this boundary violation: a 2,000-column spreadsheet was converted into giant Markdown table chunks and indexed into memory. The useful row fields were clipped or buried, so the brain could not reliably parse or enrich row-level data.

---

## Design Principle

Split storage into two planes.

**Control plane:** system Postgres stores ownership, permissions, workflow state, manifests, schemas, lineage, and pointers.

**Data plane:** user/client payloads live in artifact stores and specialized query indexes. The data plane answers content questions; the control plane answers system questions.

Postgres should answer:

> What exists, who owns it, where is it, what state is it in, and how should it be accessed?

The data plane should answer:

> Which rows, passages, records, entities, or outputs match this research/enrichment query?

---

## Storage Classes

| Data class | Control plane | Data plane |
| --- | --- | --- |
| Users, sessions, settings | Postgres canonical tables | none |
| Pipeline definitions and run state | Postgres canonical tables | none |
| Uploaded source metadata | `research_sources` manifest and pointers | raw file + normalized artifacts |
| Spreadsheet/SQL/Parquet rows | source/table manifests only | Parquet datasets queried by DuckDB |
| PDF/TXT/RTF/DOCX text | document manifest only | extracted text chunks + vector index |
| Chat messages/history | session/thread manifest and retention metadata | append-only transcript artifacts |
| Research results/output | run metadata and artifact pointers | JSON/Parquet/Markdown/PDF artifacts |
| Enrichment results | job metadata, schema, lineage | enriched datasets/artifacts |
| Semantic search | collection/index pointers | Qdrant vectors with source pointers |
| Entity relationships | extraction manifests and provenance | knowledge graph observations |

---

## Data Plane Components

### Object/Artifact Store

Stores original uploads and derived artifacts. Local development uses a filesystem root, production can use S3/R2/GCS/MinIO.

Default local root:

```text
SOURCE_DATASTORE_ROOT=/tmp/info-broker-datastore
```

Artifact examples:

```text
{root}/{user_id}/{source_id}/data.parquet
{root}/{user_id}/{source_id}/{sheet}.parquet
{root}/{user_id}/{run_id}/transcript.jsonl
{root}/{user_id}/{run_id}/results.json
{root}/{user_id}/{run_id}/export.pdf
```

### Parquet Dataset Store

Canonical normalized format for tabular or record-like data:

- CSV
- XLS/XLSX sheets
- uploaded Parquet
- SQL imports
- JSONL
- tables extracted from PDFs
- enrichment outputs

Parquet keeps data columnar, compressed, streamable, and queryable without loading the full file into API memory.

### DuckDB Query Layer

DuckDB queries Parquet artifacts directly. It is the default local/embedded query engine for user data plane scans.

The important lesson is that DuckDB is the query engine, not the database of record. The canonical data-plane record is the artifact set: raw uploads, normalized Parquet, JSONL transcripts, reports, exports, and derived tables. This keeps the architecture portable. If a tenant later needs ClickHouse, BigQuery, Snowflake, or a dedicated Postgres warehouse, the control plane can point to that backing store without changing system tables.

A second Postgres database is still a valid optional data-plane connector, but it is not the best default for arbitrary uploads. It works well when imported data has stable relational schemas and needs transactional row updates. It is weaker as the default file-ingestion layer because user data may be wide, sparse, semi-structured, evolving, or document-like. Forcing every CSV/XLSX/PDF/SQL/RTF/chat-output artifact into relational tables creates schema churn and operational coupling.

Default rule:

- Use Parquet artifacts plus DuckDB for heterogeneous research/enrichment data.
- Use a tenant/user Postgres data-plane connector only when the data is intentionally becoming relational application data.
- Use Qdrant for semantic discovery pointers, not canonical row storage.
- Use the knowledge graph for extracted entities/relationships, not raw imported records.

Query path:

```text
query_uploaded_data
  -> read source manifest from control Postgres
  -> resolve Parquet artifact paths
  -> DuckDB query over Parquet
  -> return compact row records
```

### Qdrant Semantic Index

Qdrant stores embeddings for discovery and semantic ranking, not canonical source data.

Allowed payloads:

- source id
- artifact/table id
- row number or chunk id
- document page/section
- compact preview
- pointer to canonical artifact

For large structured data, Qdrant should point to rows/chunks and Postgres/data-plane metadata should resolve authority.

### Knowledge Graph

Neo4j or the existing knowledge graph stores extracted entities and relationships, not raw upload rows.

Examples:

- person `works_at` company
- company `owns_domain` domain
- source row `supports` observation
- document `mentions` entity

---

## Ingestion Flow

### Tabular Sources

```text
Upload
  -> save raw file artifact
  -> stream parse rows
  -> normalize columns
  -> write Parquet artifact(s)
  -> store schema/table manifest in research_sources.manifest
  -> index schema-only findings in Qdrant
```

Control manifest must not include row values. It may include:

- storage type
- artifact format
- artifact path/pointer
- table/sheet names
- row counts
- column names
- ingestion status

### Document Sources

Phase 2 design:

```text
Upload
  -> save raw file artifact
  -> extract text/pages/tables
  -> write text chunks as JSONL/Parquet artifacts
  -> write extracted tables as Parquet
  -> store document manifest in control plane
  -> index chunks in Qdrant with artifact pointers
```

### User-Specific Outputs

Phase 3 design:

```text
Research/chat/run output
  -> write append-only artifact JSONL/JSON/Markdown
  -> store control row with owner, run id, artifact pointer, retention policy
  -> index selected summaries/chunks in Qdrant if searchable
```

This applies to chat messages, branch traces, final reports, exports, and enrichment outputs.

---

## Phase 1 Implementation

Implemented first because it fixes the row-level enrichment failure:

1. Add `app.sources.datastore`.
2. Normalize CSV/XLS/XLSX/Parquet uploads into Parquet artifacts under `SOURCE_DATASTORE_ROOT`.
3. Store only schema/table manifest and artifact pointers in `research_sources.manifest`.
4. Index only schema findings in Qdrant for tabular uploads.
5. Update `/v3/sources/query` and MCP `query_uploaded_data` path to query Parquet artifacts through DuckDB.
6. Return compact row records with `source_tool = "file_upload_row"` for enrichment.

Out of scope for Phase 1:

- migrating existing chat/session/run output payloads
- moving PDF/DOCX/TXT chunks out of Qdrant-first storage
- cloud object store adapter
- retention/tenant encryption policies

---

## Migration Path For Existing User-Specific Data

1. Add artifact pointer fields to existing control tables where needed.
2. Write new payloads to the data plane first, keeping current columns for compatibility.
3. Backfill old payloads into artifacts with provenance metadata.
4. Replace read paths to prefer artifact pointers.
5. Retain only compact summaries and pointers in Postgres.
6. Add retention/deletion jobs that operate on both control rows and data-plane artifacts.

Candidate control tables for future migration:

- `agent_sessions.conversation_thread`
- `agent_sessions.accumulated_summary`
- `agent_sessions.key_findings`
- `research_trails.trail`
- `research_trails.findings`
- `pipeline_runs` final output fields, if added
- export/output records
- enrichment datasets

---

## Non-Goals

- Do not use system Postgres as a client data warehouse.
- Do not put raw spreadsheets into Neo4j.
- Do not put full row payloads into Qdrant.
- Do not require a distributed data stack before local DuckDB/Parquet limits are reached.
