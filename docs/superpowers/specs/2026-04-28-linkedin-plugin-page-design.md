# LinkedIn Plugin Page Design

**Date:** 2026-04-28

## Goal

Add a dedicated LinkedIn harvester page to the info-broker UI that lets users configure Apify credentials, define a scrape run config (job titles, locations, etc.), trigger Apify actor runs from the browser, monitor run status in real time, and auto-ingest results into the profiles DB + Qdrant on success.

---

## Architecture

A new FastAPI router (`/v3/apify`) handles all backend concerns. The frontend gets a new icon-rail entry and a dedicated `LinkedInPage` with a two-column layout. Apify credentials live in the existing `core_settings` table; run-config defaults and run history get two new tables.

---

## Data Model

Two new tables added to `_MIGRATION` in `app/routers/v3/db.py`:

```sql
-- saved run-config defaults (one row per user)
CREATE TABLE IF NOT EXISTS apify_run_configs (
    user_id        UUID PRIMARY KEY REFERENCES ui_users(id) ON DELETE CASCADE,
    job_titles     JSONB DEFAULT '[]',
    locations      JSONB DEFAULT '[]',
    max_items      INT DEFAULT 300,
    scraper_mode   VARCHAR(64) DEFAULT 'Full + email search',
    updated_at     TIMESTAMPTZ DEFAULT now()
);

-- one row per scrape run triggered from the UI
CREATE TABLE IF NOT EXISTS apify_runs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID REFERENCES ui_users(id) ON DELETE CASCADE,
    apify_run_id   TEXT,
    status         VARCHAR(20) DEFAULT 'queued',
    item_count     INT DEFAULT 0,
    started_at     TIMESTAMPTZ DEFAULT now(),
    finished_at    TIMESTAMPTZ
);
```

Apify API key and actor ID are stored in the existing `core_settings` table under keys `apify_api_key` and `apify_actor_id`. Secrets are masked (returned as `null`) on read.

---

## Backend API

**New file:** `app/routers/v3/apify.py`  
**Prefix:** `/v3/apify`  
**Auth:** all endpoints use `Depends(get_current_user)`

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/v3/apify/config` | Return masked API key, actor ID, and saved run-config defaults for current user |
| `POST` | `/v3/apify/config` | Upsert API key + actor ID in `core_settings`; upsert run defaults in `apify_run_configs` |
| `POST` | `/v3/apify/run` | Validate credentials exist, POST to Apify REST API to start actor run, insert row in `apify_runs`, return internal run UUID and Apify run ID |
| `GET` | `/v3/apify/runs` | List all runs for current user, newest first |
| `GET` | `/v3/apify/runs/{run_id}/status` | Poll Apify API for run status; on `SUCCEEDED` trigger ingest from the run's dataset, update `apify_runs` row, return current status + item count |

### Ingest on success

The status-poll endpoint fetches the Apify dataset for that specific run (using `datasetId` from the Apify run response) and calls the same ingest logic as `ingest.py` — writing profiles to `linkedin_profiles` (Postgres) and the `linkedin_profiles` Qdrant collection. `apify_runs.item_count` and `finished_at` are updated on completion.

### Apify REST API calls

- Start run: `POST https://api.apify.com/v2/acts/{actor_id}/runs?token={api_key}`  
  Body: the run-config JSON (job titles, locations, maxItems, scraper mode, fixed booleans).
- Poll status: `GET https://api.apify.com/v2/actor-runs/{apify_run_id}?token={api_key}`
- Fetch dataset: `GET https://api.apify.com/v2/datasets/{dataset_id}/items?token={api_key}&format=json`

---

## Frontend

### Navigation

Add `Linkedin` icon (lucide-react) to the icon rail in `AppShell.tsx`, route `/linkedin` → `LinkedInPage`.

### New files

- `frontend/src/pages/LinkedInPage.tsx` — page component
- `frontend/src/components/linkedin/TagInput.tsx` — reusable tag/pill input
- `frontend/src/api/apify.ts` — typed API client functions

### Layout

Two-column split (left: credentials + run config form; right: run history):

```
┌─────────────────────────────────┬──────────────────────────┐
│  ⚙ Credentials                  │  Run History             │
│  API Key   [••••••••]  [Save]   │  ─────────────────────── │
│  Actor ID  [_______]            │  • 2026-04-28 14:02      │
│                                 │    running  ⟳            │
│  Run Config                     │  • 2026-04-27 09:15      │
│  Job Titles  [tag input]  [+]   │    succeeded  312 items  │
│  Locations   [tag input]  [+]   │  • 2026-04-26 11:30      │
│  Max Items   [300]              │    failed                │
│  Mode        [dropdown ▾]       │                          │
│                                 │                          │
│              [▶ Run Scrape]     │                          │
└─────────────────────────────────┴──────────────────────────┘
```

### TagInput component

Local component, no external dependency. Renders existing tags as dismissible pills. User types a value and presses Enter (or comma) to add; clicks × on a pill to remove. Controlled via `value: string[]` + `onChange` props.

### Run status polling

When a run has status `queued` or `running`, TanStack Query refetches `GET /v3/apify/runs/{run_id}/status` every 5 seconds. On `succeeded`, invalidates the runs list query and shows item count in the history panel.

---

## Error Handling

- Missing credentials on "Run Scrape": frontend disables the button and shows inline hint; backend also validates and returns 400.
- Apify API error on run start: backend returns 502 with Apify's error message; UI shows toast.
- Ingest failure on succeeded run: logged as warning, `apify_runs.status` set to `ingest_failed` (distinct from `failed` = Apify actor failure).

---

## Out of Scope

- Multi-user run isolation (all users share the same Apify credentials from `core_settings`)
- Scheduling / recurring runs
- Editing the advanced Apify fields (autoQuerySegmentation, country targeting) — these are fixed at their reference-config defaults
- Viewing ingested profiles in this page (profiles visible in the existing Profiles tab of ResultsPanel)
