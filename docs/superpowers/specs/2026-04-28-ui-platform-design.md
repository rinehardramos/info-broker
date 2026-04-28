# Info-Broker UI Platform — Design Spec

**Date:** 2026-04-28
**Status:** Approved
**Approach:** Separate `frontend/` service (Vite + React) alongside existing `app/` (FastAPI), same repo, Docker Compose

---

## Overview

A multi-user research intelligence platform layered on top of info-broker's existing data broker service. Users (marketing, analysts, researchers) interact with an agentic interface to ask questions, monitor feeds, and receive enriched information in multiple formats. Info-broker remains purely informational — it sources, scrapes, and synthesises; it never takes action. Actions are the responsibility of downstream services and agents.

The UI is a secondary surface. Info-broker's primary function remains API-first batch/background enrichment for other services.

---

## 1. Design Principles

- **Purely informational.** No call-to-action buttons. No "send email", no "post", no "create". The platform surfaces intelligence; other agents act on it.
- **Agentic.** Users express intent in natural language. The agent spawns sub-tasks (scrapers, searchers, crawlers) and surfaces results as they arrive.
- **Research-first.** The agent keeps digging until it has a sufficient picture. Users can ask for more depth at any time.
- **Multi-user isolated.** Each user has their own plugin configs, layout preferences, feed monitors, and research history.
- **Backend-first.** The UI is a thin shell over the existing FastAPI service. All intelligence lives in the backend.

---

## 2. UI Layout

### 2.1 Overall Structure

Tablet-landscape-optimised, right-handed. Three independently scrollable columns plus a fixed icon rail on the far right.

```
┌──────────────────────┬─────────────┬──────────┬───┐
│   COL 1 · RESULTS    │  COL 2      │  COL 3   │   │
│   (widest ~46%)      │  AGENT      │  LIVE    │ ⬡ │
│                      │  (~30%)     │  (~20%)  │   │
│  tabs: Profiles /    │             │          │ ✦ │
│  News / Social /     │  chat ↕     │  stream  │   │
│  Summary             │             │  ↕       │ ◉ │
│                      │  [input]    │          │   │
│  ↕ scrollable        │  pinned     │  tap →   │ ◈ │
│                      │  bottom     │  opens   │   │
│                      │             │  in col1 │ ▤ │
│                      │             │          │   │
│                      │             │          │ ⚙ │
│                      │             │          │   │
│                      │             │          │ R │
└──────────────────────┴─────────────┴──────────┴───┘
```

### 2.2 Column Behaviour

| Column | Default width | Content | Scrolls |
|--------|-------------|---------|---------|
| Col 1 — Results | ~46% | Profiles, news, social, summary. Tab bar switches data type. | Yes |
| Col 2 — Agent | ~30% | Conversation history. Input pinned at bottom. | Yes |
| Col 3 — Live stream | ~20% | Running jobs, completed tasks, feed monitors. Tap → opens in Col 1. | Yes |
| Icon rail | 28px (fixed) | Navigation icons only, no labels. Right-thumb reach. | No |

**Column interaction rules:**
- Each column header has a `⠿` drag handle — columns are reorderable by drag.
- Column borders are draggable for width resizing.
- Layout (order + widths) is persisted per user in `ui_preferences`.
- Tapping any item in the Live stream column opens its full detail in Col 1.

### 2.3 Icon Rail

28px wide, icons only (no text labels), fixed to the far right for right-handed tablet use. Always visible at 28px — no expand/collapse state.

| Icon | View |
|------|------|
| `⬡` | Logo / home |
| `✦` | Agent (default) |
| `◉` | Jobs |
| `◈` | Feed Monitors |
| `▤` | History |
| `⚙` | Settings + Plugin Config |
| `☀/🌙` | Mode toggle |
| `R` | User avatar / profile |

### 2.4 Modes

Two dark modes. Toggled via `☀/🌙` in the icon rail. Preference saved per user.

| Mode | Name | Background | Panels | Accent |
|------|------|------------|--------|--------|
| ☀ Light | Deep Navy | `#070e1a` | `#0d1b2a` / `#132030` | `#60a5fa` |
| 🌙 Dark | Hacker | `#050505` | `#0a0a0a` / `#0d0d0d` | `#22c55e` |

Signal colours (both modes): High = `#4ade80` / `#22c55e`, Medium = `#f59e0b`, Low = `#ef4444`.

### 2.5 Plugin Configuration Pages

Each plugin has a dedicated configuration page, accessible from `⚙ Settings → Plugins → [plugin name]`. The page is auto-rendered from the plugin's `config_schema` (JSON Schema). Users can tweak plugin-specific parameters (e.g. Apify actor ID, scraping depth, rate limits, geographic filters, API keys).

Examples:
- **Apify LinkedIn:** actor ID, max results, geographic filter, cookie session, rate limit
- **News plugin:** sources list, topics, language, freshness threshold
- **Weather plugin:** API key, default location, units
- **Proxycurl LinkedIn:** API key, fallback behaviour, credit budget per query

---

## 3. Frontend Architecture

### 3.1 Stack

| Layer | Technology |
|-------|-----------|
| Build | Vite |
| Framework | React 18 |
| Global state | Zustand |
| Server state / cache | React Query (TanStack Query) |
| Real-time | Native WebSocket (custom hook) |
| Styling | Tailwind CSS (dark-mode via class strategy) |
| Drag + resize | `@dnd-kit/core` + `react-resizable-panels` |
| Forms (plugin config) | React Hook Form + JSON Schema → auto-rendered fields |
| Auth | JWT stored in `httpOnly` cookie (set by API) |

### 3.2 Directory Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── layout/         # ThreeColumnLayout, IconRail, ColumnHeader
│   │   ├── results/        # ProfileCard, NewsCard, SocialCard, SummaryBlock
│   │   ├── agent/          # AgentChat, MessageBubble, TaskStatus
│   │   ├── live/           # LiveStream, JobItem, MonitorItem
│   │   └── plugins/        # PluginConfigPage, SchemaFormRenderer
│   ├── pages/
│   │   ├── Research.tsx    # Main 3-column view
│   │   ├── Jobs.tsx
│   │   ├── Monitors.tsx
│   │   ├── History.tsx
│   │   └── Settings.tsx    # Plugin list → links to PluginConfigPage
│   ├── hooks/
│   │   ├── useWebSocket.ts # Live stream connection
│   │   ├── useLayout.ts    # Column order/width persistence
│   │   └── useTheme.ts     # dark/light mode
│   ├── stores/
│   │   ├── layoutStore.ts  # Zustand: column positions, widths
│   │   └── sessionStore.ts # Zustand: current user, active job
│   └── api/
│       └── client.ts       # Axios instance with JWT interceptor
├── Dockerfile
├── nginx.conf              # Proxy /api/* → api:8000, ws → api:8000
└── vite.config.ts
```

### 3.3 Real-time (WebSocket)

Single WebSocket connection per session at `ws://host/v3/stream`. The backend pushes events as jobs progress. The frontend updates the Live stream column and the agent conversation in real time.

Event shape:
```json
{
  "type": "job.update",
  "job_id": "uuid",
  "plugin": "linkedin",
  "status": "running" | "completed" | "failed",
  "result_count": 9,
  "message": "Found 9 profiles",
  "timestamp": "2026-04-28T..."
}
```

Event types: `job.update`, `job.completed`, `job.failed`, `monitor.new_items`, `agent.message`, `agent.thinking`.

---

## 4. Backend Architecture

### 4.1 New API Routers (`/v3/*`)

All `/v3/*` routes require JWT auth. Existing `/v1/*` and `/v2/*` routes are unchanged.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v3/agent/message` | Send message to agent, returns job_id |
| GET | `/v3/jobs` | List user's jobs (paginated) |
| GET | `/v3/jobs/{job_id}` | Job detail + results |
| DELETE | `/v3/jobs/{job_id}` | Cancel running job |
| GET | `/v3/monitors` | List user's feed monitors |
| POST | `/v3/monitors` | Create feed monitor |
| DELETE | `/v3/monitors/{id}` | Remove monitor |
| GET | `/v3/plugins` | List plugins + user config |
| GET | `/v3/plugins/{name}/schema` | Plugin config JSON Schema |
| GET | `/v3/plugins/{name}/config` | User's current config for plugin |
| PUT | `/v3/plugins/{name}/config` | Save user plugin config |
| GET | `/v3/users/me` | Current user + preferences |
| PUT | `/v3/users/me/preferences` | Save layout, mode preference |
| WS | `/v3/stream` | WebSocket live event stream |
| POST | `/v3/auth/login` | Exchange credentials for JWT |
| POST | `/v3/auth/refresh` | Refresh JWT |

### 4.2 Plugin Protocol Extension

Existing `SearchPlugin` protocol is extended with `config_schema`:

```python
class SearchPlugin(Protocol):
    name: str
    description: str
    requires_api_key: bool
    config_schema: dict          # JSON Schema — new field

    async def search(self, query: str, *, max_results: int = 5, config: dict | None = None) -> list[PluginResult]
    def available(self) -> bool
    def configure(self, config: dict) -> None   # new: apply user config
```

`config_schema` example for Apify LinkedIn plugin:
```json
{
  "type": "object",
  "properties": {
    "actor_id":       { "type": "string", "title": "Actor ID", "default": "apify/linkedin-profile-scraper" },
    "max_results":    { "type": "integer", "title": "Max results", "default": 25, "minimum": 1, "maximum": 200 },
    "geo_filter":     { "type": "string", "title": "Geographic filter", "default": "" },
    "rate_limit_rps": { "type": "number", "title": "Rate limit (req/s)", "default": 0.5 }
  }
}
```

The frontend fetches this schema from `GET /v3/plugins/{name}/schema` and auto-renders a config form using React Hook Form.

### 4.3 New Postgres Tables

```sql
-- Multi-user auth
CREATE TABLE ui_users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username    VARCHAR(128) UNIQUE NOT NULL,
    email       VARCHAR(256),
    password_hash TEXT NOT NULL,
    is_active   BOOLEAN DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- JWT refresh tokens
CREATE TABLE ui_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES ui_users(id) ON DELETE CASCADE,
    refresh_token TEXT UNIQUE NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Per-user layout + mode preferences
CREATE TABLE ui_preferences (
    user_id     UUID PRIMARY KEY REFERENCES ui_users(id) ON DELETE CASCADE,
    theme       VARCHAR(16) DEFAULT 'navy',        -- 'navy' | 'hacker'
    column_layout JSONB DEFAULT '{}',              -- order + widths
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Per-user plugin configuration
CREATE TABLE plugin_configs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES ui_users(id) ON DELETE CASCADE,
    plugin_name VARCHAR(64) NOT NULL,
    config      JSONB NOT NULL DEFAULT '{}',       -- validated against plugin config_schema
    updated_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, plugin_name)
);

-- Feed monitors (RSS, social accounts)
CREATE TABLE feed_monitors (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES ui_users(id) ON DELETE CASCADE,
    name        VARCHAR(128) NOT NULL,
    type        VARCHAR(32) NOT NULL,              -- 'rss' | 'twitter' | 'facebook' | 'linkedin'
    target      TEXT NOT NULL,                     -- URL or @handle
    poll_interval_minutes INT DEFAULT 60,
    last_polled_at TIMESTAMPTZ,
    last_item_count INT DEFAULT 0,
    is_active   BOOLEAN DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT now()
);
```

### 4.4 Agent Router (`/v3/agent/message`)

When the user sends a message, the agent:
1. Parses intent (NLP via LLM — what data sources are needed?)
2. Spawns sub-tasks per relevant plugin (LinkedIn search, OSINT, news scan, social crawl, etc.)
3. Returns `job_id` immediately (202)
4. Pushes `job.update` events over WebSocket as each sub-task completes
5. When all sub-tasks are done: synthesises a summary, pushes `agent.message` event
6. Results queryable via `GET /v3/jobs/{job_id}`

```python
# POST /v3/agent/message
{
  "message": "Find CTOs at Manila SMBs in fintech with outsourcing needs",
  "context_job_id": "uuid | null"   # optional: continue from prior research
}
# → 202 { "job_id": "uuid", "stream_url": "ws://host/v3/stream" }
```

---

## 5. Docker Compose (Local Dev)

```yaml
services:
  frontend:
    build: ./frontend
    ports: ["5173:5173"]          # Vite dev server with HMR
    volumes: ["./frontend:/app"]  # hot-reload
    environment:
      VITE_API_URL: http://localhost:8000
      VITE_WS_URL: ws://localhost:8000/v3/stream
    depends_on: [api]

  api:
    build: .
    ports: ["8000:8000"]
    volumes: ["./app:/app/app"]   # hot-reload via uvicorn --reload
    env_file: .env
    depends_on: [postgres, qdrant]

  postgres:
    image: postgres:16
    ports: ["5432:5432"]
    environment:
      POSTGRES_DB: info_broker
      POSTGRES_USER: info_broker
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes: ["pgdata:/var/lib/postgresql/data"]

  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333"]
    volumes: ["qdrantdata:/qdrant/storage"]

volumes:
  pgdata:
  qdrantdata:
```

Production adds nginx in the frontend container to proxy `/api/*` → `api:8000` and WebSocket.

---

## 6. New Environment Variables

| Variable | Service | Purpose |
|----------|---------|---------|
| `JWT_SECRET` | api | HS256 signing key (already exists as stub) |
| `JWT_EXPIRY_HOURS` | api | Access token lifetime (default: 1) |
| `JWT_REFRESH_DAYS` | api | Refresh token lifetime (default: 30) |
| `PROXYCURL_API_KEY` | api | Proxycurl LinkedIn enrichment |
| `PLAYWRIGHT_PROXY_URL` | api | Proxy for Playwright scraping (optional) |
| `VITE_API_URL` | frontend | Backend base URL |
| `VITE_WS_URL` | frontend | WebSocket URL |

---

## 7. File Structure Changes

```
info-broker/
├── frontend/                    # NEW — Vite + React app
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── stores/
│   │   └── api/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── vite.config.ts
│   ├── package.json
│   └── tsconfig.json
├── app/
│   ├── routers/
│   │   └── v3/                  # NEW
│   │       ├── agent.py
│   │       ├── jobs.py
│   │       ├── monitors.py
│   │       ├── plugins.py
│   │       ├── users.py
│   │       └── stream.py        # WebSocket handler
│   ├── adapters/
│   │   └── linkedin.py          # NEW (from LinkedIn plugin spec)
│   ├── lib/
│   │   └── playwright_scraper.py # NEW
│   └── search_engine/
│       └── plugins/
│           └── linkedin.py      # NEW (from LinkedIn plugin spec)
├── docker-compose.yml           # UPDATED — add frontend service
└── docker-compose.prod.yml      # NEW — production overrides
```

---

## 8. Out of Scope

- Native mobile app (web responsive covers mobile)
- Real-time collaboration (multiple users in same session)
- Role-based access control (all users have same permissions for now)
- Email / push notifications (feed monitors surface in UI only)
- Any action-taking features (send email, post to social, etc.)
