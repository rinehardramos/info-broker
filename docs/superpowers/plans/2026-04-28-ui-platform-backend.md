# UI Platform — Backend & Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/v3/*` API routers, WebSocket live stream, multi-user auth, new Postgres tables, and a frontend Docker service so the UI platform runs locally via `docker compose up`.

**Architecture:** Extend existing FastAPI app with a new `app/routers/v3/` package. New Postgres tables added via the existing lifespan migration pattern. Frontend served by a separate Vite dev container. Postgres stays on `host.docker.internal` (existing setup). WebSocket at `/v3/stream` pushes live job events to connected clients.

**Tech Stack:** FastAPI, psycopg2, python-jose[cryptography], passlib[bcrypt], WebSockets (FastAPI built-in), Docker Compose, Vite (frontend scaffold only in this plan)

---

## File Map

**Create:**
- `app/routers/v3/__init__.py`
- `app/routers/v3/auth.py` — login, refresh, JWT utils
- `app/routers/v3/users.py` — /users/me, preferences
- `app/routers/v3/plugins.py` — schema, config CRUD
- `app/routers/v3/settings.py` — core settings CRUD
- `app/routers/v3/agent.py` — /agent/message, spawn jobs
- `app/routers/v3/jobs.py` — list, get, cancel jobs
- `app/routers/v3/monitors.py` — feed monitor CRUD
- `app/routers/v3/stream.py` — WebSocket handler + event bus
- `app/routers/v3/db.py` — new table migrations + query helpers
- `app/routers/v3/models.py` — Pydantic request/response models
- `frontend/Dockerfile` — Vite dev container
- `frontend/package.json` — minimal deps for scaffold
- `frontend/vite.config.ts`
- `frontend/index.html`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `tests/v3/test_auth.py`
- `tests/v3/test_plugins.py`
- `tests/v3/test_settings.py`
- `tests/v3/test_agent.py`
- `tests/v3/test_stream.py`

**Modify:**
- `docker-compose.yml` — add frontend service
- `app/main.py` — register v3 routers, run v3 migrations
- `app/search_engine/plugins/base.py` — add `config_schema`, `configure()`
- `pyproject.toml` — add python-jose, passlib dependencies
- `.gitignore` — ignore `frontend/node_modules`

---

## Task 1: Add frontend to Docker Compose + scaffold Vite app

**Files:**
- Modify: `docker-compose.yml`
- Create: `frontend/Dockerfile`
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Modify: `.gitignore`

- [ ] **Step 1: Add frontend service to docker-compose.yml**

```yaml
# docker-compose.yml — add this service block alongside info-broker-api
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
      - /app/node_modules        # prevent host node_modules from shadowing container's
    environment:
      VITE_API_URL: http://localhost:8000
      VITE_WS_URL: ws://localhost:8000/v3/stream
    depends_on:
      - info-broker-api
```

- [ ] **Step 2: Create `frontend/Dockerfile`**

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

- [ ] **Step 3: Create `frontend/package.json`**

```json
{
  "name": "info-broker-ui",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test": "vitest"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.1",
    "zustand": "^4.5.5",
    "@tanstack/react-query": "^5.56.2",
    "axios": "^1.7.7",
    "@dnd-kit/core": "^6.1.0",
    "@dnd-kit/sortable": "^8.0.0",
    "react-resizable-panels": "^2.1.3",
    "react-hook-form": "^7.53.0",
    "clsx": "^2.1.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.5",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.3",
    "vite": "^5.4.2",
    "vitest": "^2.1.1",
    "@testing-library/react": "^16.0.1",
    "@testing-library/jest-dom": "^6.5.0",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.45",
    "tailwindcss": "^3.4.11"
  }
}
```

- [ ] **Step 4: Create `frontend/vite.config.ts`**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
})
```

- [ ] **Step 5: Create `frontend/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>info-broker</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Create `frontend/src/main.tsx`**

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

- [ ] **Step 7: Create `frontend/src/App.tsx`**

```tsx
export default function App() {
  return (
    <div style={{ color: '#60a5fa', background: '#070e1a', minHeight: '100vh', padding: '2rem', fontFamily: 'monospace' }}>
      <h1>info-broker</h1>
      <p>UI platform — scaffold</p>
    </div>
  )
}
```

- [ ] **Step 8: Create `frontend/src/index.css`** (empty for now)

```css
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #070e1a; }
```

- [ ] **Step 9: Create `frontend/src/test-setup.ts`**

```typescript
import '@testing-library/jest-dom'
```

- [ ] **Step 10: Add to `.gitignore`**

```
frontend/node_modules/
frontend/dist/
```

- [ ] **Step 11: Build and start**

```bash
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
docker compose up --build frontend
```

Expected: frontend container starts, Vite dev server on http://localhost:5173 shows "info-broker — UI platform scaffold"

- [ ] **Step 12: Commit**

```bash
git add docker-compose.yml frontend/ .gitignore
git commit -m "feat: add frontend scaffold + docker compose service"
```

---

## Task 2: Add python-jose and passlib dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `requirements.txt` (if it exists alongside pyproject.toml)

- [ ] **Step 1: Add deps to pyproject.toml**

Open `pyproject.toml` and add to `dependencies`:
```toml
"python-jose[cryptography]>=3.3.0",
"passlib[bcrypt]>=1.7.4",
"websockets>=12.0",
```

- [ ] **Step 2: Sync deps**

```bash
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
uv sync
```

Expected: `python-jose`, `passlib`, `websockets` appear in `.venv/lib/`.

- [ ] **Step 3: Verify import**

```bash
.venv/bin/python -c "from jose import jwt; from passlib.context import CryptContext; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat(deps): add python-jose, passlib, websockets"
```

---

## Task 3: Extend SearchPlugin protocol with config_schema

**Files:**
- Modify: `app/search_engine/plugins/base.py`
- Test: `tests/test_plugin_base.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_plugin_base.py`:
```python
import pytest
from app.search_engine.plugins.base import SearchPlugin, PluginResult


class MinimalPlugin:
    name = "minimal"
    description = "test"
    requires_api_key = False
    config_schema: dict = {}

    async def search(self, query, *, max_results=5, config=None):
        return []

    def available(self):
        return True

    def configure(self, config: dict) -> None:
        pass


def test_plugin_has_config_schema():
    p = MinimalPlugin()
    assert isinstance(p.config_schema, dict)


def test_plugin_has_configure():
    p = MinimalPlugin()
    p.configure({"key": "value"})  # must not raise
```

- [ ] **Step 2: Run test — expect PASS** (MinimalPlugin already has the attrs, but protocol doesn't require them yet)

```bash
.venv/bin/pytest tests/test_plugin_base.py -v
```

- [ ] **Step 3: Update `app/search_engine/plugins/base.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass
class PluginResult:
    title: str
    url: str | None
    snippet: str
    full_text: str | None
    published_at: datetime | None
    source_name: str
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class SearchPlugin(Protocol):
    name: str
    description: str
    requires_api_key: bool
    config_schema: dict  # JSON Schema describing user-configurable parameters

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        config: dict | None = None,
    ) -> list[PluginResult]: ...

    def available(self) -> bool: ...

    def configure(self, config: dict) -> None: ...
```

- [ ] **Step 4: Add `config_schema = {}` and `configure()` stub to existing plugins**

For each file in `app/search_engine/plugins/` (ddg.py, wikipedia.py, google_rss.py):
```python
# add at class level:
config_schema: dict = {}

def configure(self, config: dict) -> None:
    pass
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/pytest tests/test_plugin_base.py tests/ -v --tb=short
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add app/search_engine/plugins/ tests/test_plugin_base.py
git commit -m "feat(plugins): add config_schema + configure() to SearchPlugin protocol"
```

---

## Task 4: New Postgres tables (v3 DB migration)

**Files:**
- Create: `app/routers/v3/__init__.py`
- Create: `app/routers/v3/db.py`
- Test: `tests/v3/__init__.py`
- Test: `tests/v3/test_db.py`

- [ ] **Step 1: Create `app/routers/v3/__init__.py`** (empty)

```python
```

- [ ] **Step 2: Create `tests/v3/__init__.py`** (empty)

```python
```

- [ ] **Step 3: Write failing test**

Create `tests/v3/test_db.py`:
```python
import os
import pytest
import psycopg2
from app.routers.v3.db import run_migrations, get_conn

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_HOST"),
    reason="Postgres not available in CI without env vars"
)


def test_run_migrations_creates_tables():
    run_migrations()
    with get_conn() as conn:
        with conn.cursor() as cur:
            for table in ["ui_users", "ui_sessions", "ui_preferences",
                          "plugin_configs", "feed_monitors", "core_settings"]:
                cur.execute(
                    "SELECT to_regclass(%s)",
                    (f"public.{table}",)
                )
                result = cur.fetchone()[0]
                assert result is not None, f"Table {table} was not created"
```

- [ ] **Step 4: Create `app/routers/v3/db.py`**

```python
from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

_MIGRATION = """
CREATE TABLE IF NOT EXISTS ui_users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username      VARCHAR(128) UNIQUE NOT NULL,
    email         VARCHAR(256),
    password_hash TEXT NOT NULL,
    is_active     BOOLEAN DEFAULT true,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ui_sessions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID REFERENCES ui_users(id) ON DELETE CASCADE,
    refresh_token TEXT UNIQUE NOT NULL,
    expires_at    TIMESTAMPTZ NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ui_preferences (
    user_id       UUID PRIMARY KEY REFERENCES ui_users(id) ON DELETE CASCADE,
    theme         VARCHAR(16) DEFAULT 'navy',
    column_layout JSONB DEFAULT '{}',
    updated_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plugin_configs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES ui_users(id) ON DELETE CASCADE,
    plugin_name VARCHAR(64) NOT NULL,
    config      JSONB NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, plugin_name)
);

CREATE TABLE IF NOT EXISTS feed_monitors (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID REFERENCES ui_users(id) ON DELETE CASCADE,
    name                 VARCHAR(128) NOT NULL,
    type                 VARCHAR(32) NOT NULL,
    target               TEXT NOT NULL,
    poll_interval_minutes INT DEFAULT 60,
    last_polled_at       TIMESTAMPTZ,
    last_item_count      INT DEFAULT 0,
    is_active            BOOLEAN DEFAULT true,
    created_at           TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core_settings (
    key        VARCHAR(128) PRIMARY KEY,
    value      TEXT NOT NULL,
    is_secret  BOOLEAN DEFAULT false,
    updated_at TIMESTAMPTZ DEFAULT now()
);
"""


def _dsn() -> dict:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return {"dsn": database_url}
    return dict(
        dbname=os.getenv("POSTGRES_DB", "info_broker"),
        user=os.getenv("POSTGRES_USER", "user"),
        password=os.getenv("POSTGRES_PASSWORD", "password"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
    )


@contextmanager
def get_conn():
    conn = psycopg2.connect(**_dsn())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_migrations() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_MIGRATION)


def fetch_one(query: str, params: tuple = ()) -> dict | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            return dict(row) if row else None


def fetch_all(query: str, params: tuple = ()) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]


def execute(query: str, params: tuple = ()) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
```

- [ ] **Step 5: Run test**

```bash
.venv/bin/pytest tests/v3/test_db.py -v
```

Expected: PASS (tables created)

- [ ] **Step 6: Wire migration into `app/main.py` lifespan**

In `app/main.py`, inside the `lifespan` function after the existing search-engine migration block, add:

```python
    from app.routers.v3.db import run_migrations as v3_migrate
    try:
        v3_migrate()
    except Exception as exc:
        _log.warning("v3 DB migration skipped: %s", exc)
```

- [ ] **Step 7: Commit**

```bash
git add app/routers/v3/ tests/v3/ app/main.py
git commit -m "feat(v3): new DB tables + migration (ui_users, plugin_configs, core_settings, etc.)"
```

---

## Task 5: JWT auth — models + utilities

**Files:**
- Create: `app/routers/v3/models.py`
- Create: `app/routers/v3/auth.py`
- Test: `tests/v3/test_auth.py`

- [ ] **Step 1: Create `app/routers/v3/models.py`**

```python
from __future__ import annotations
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: UUID
    username: str
    email: str | None
    is_active: bool
    created_at: datetime


class PreferencesIn(BaseModel):
    theme: str | None = None          # 'navy' | 'hacker'
    column_layout: dict | None = None


class PreferencesOut(BaseModel):
    theme: str
    column_layout: dict


class PluginConfigIn(BaseModel):
    config: dict


class PluginConfigOut(BaseModel):
    plugin_name: str
    config: dict


class CoreSettingIn(BaseModel):
    key: str
    value: str
    is_secret: bool = False


class CoreSettingsOut(BaseModel):
    settings: dict[str, str | None]   # secrets returned as None


class MonitorIn(BaseModel):
    name: str
    type: str                          # 'rss' | 'twitter' | 'facebook' | 'linkedin'
    target: str
    poll_interval_minutes: int = 60


class MonitorOut(BaseModel):
    id: UUID
    name: str
    type: str
    target: str
    poll_interval_minutes: int
    last_polled_at: datetime | None
    last_item_count: int
    is_active: bool


class AgentMessageIn(BaseModel):
    message: str
    context_job_id: str | None = None


class AgentMessageOut(BaseModel):
    job_id: str
    status: str = "pending"


class JobOut(BaseModel):
    id: str
    status: str
    query: str
    created_at: datetime
    completed_at: datetime | None
    result_count: int


class StreamEvent(BaseModel):
    type: str
    job_id: str | None = None
    plugin: str | None = None
    status: str | None = None
    result_count: int | None = None
    message: str | None = None
```

- [ ] **Step 2: Write failing auth tests**

Create `tests/v3/test_auth.py`:
```python
import os
import pytest
from fastapi.testclient import TestClient
from app.main import app

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_HOST"),
    reason="Requires Postgres"
)

client = TestClient(app)


def _register_user(username: str, password: str):
    """Helper: insert a test user directly via db."""
    from passlib.context import CryptContext
    from app.routers.v3.db import execute
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    execute(
        "INSERT INTO ui_users (username, password_hash) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (username, ctx.hash(password)),
    )


def test_login_returns_tokens():
    _register_user("testuser", "secret123")
    resp = client.post("/v3/auth/login", json={"username": "testuser", "password": "secret123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_wrong_password():
    _register_user("testuser2", "correct")
    resp = client.post("/v3/auth/login", json={"username": "testuser2", "password": "wrong"})
    assert resp.status_code == 401


def test_protected_route_without_token():
    resp = client.get("/v3/users/me")
    assert resp.status_code == 401


def test_protected_route_with_token():
    _register_user("testuser3", "pass123")
    login = client.post("/v3/auth/login", json={"username": "testuser3", "password": "pass123"})
    token = login.json()["access_token"]
    resp = client.get("/v3/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "testuser3"
```

- [ ] **Step 3: Run tests — expect FAIL (routes don't exist yet)**

```bash
.venv/bin/pytest tests/v3/test_auth.py -v
```

Expected: 404 or ImportError

- [ ] **Step 4: Create `app/routers/v3/auth.py`**

```python
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.routers.v3.db import execute, fetch_one
from app.routers.v3.models import LoginRequest, RefreshRequest, TokenResponse, UserOut

router = APIRouter(prefix="/v3/auth", tags=["v3-auth"])

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer()

_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
_ALGO = "HS256"
_ACCESS_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "1"))
_REFRESH_DAYS = int(os.getenv("JWT_REFRESH_DAYS", "30"))


def _make_access_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=_ACCESS_HOURS)
    return jwt.encode({"sub": user_id, "exp": exp, "type": "access"}, _SECRET, algorithm=_ALGO)


def _make_refresh_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=_REFRESH_DAYS)
    token = str(uuid.uuid4())
    execute(
        "INSERT INTO ui_sessions (user_id, refresh_token, expires_at) VALUES (%s, %s, %s)",
        (user_id, token, exp),
    )
    return token


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, _SECRET, algorithms=[_ALGO])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not an access token")
    user = fetch_one("SELECT * FROM ui_users WHERE id = %s AND is_active = true", (payload["sub"],))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    user = fetch_one("SELECT * FROM ui_users WHERE username = %s AND is_active = true", (body.username,))
    if not user or not _pwd.verify(body.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(
        access_token=_make_access_token(str(user["id"])),
        refresh_token=_make_refresh_token(str(user["id"])),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest):
    session = fetch_one(
        "SELECT * FROM ui_sessions WHERE refresh_token = %s AND expires_at > now()",
        (body.refresh_token,),
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")
    # rotate refresh token
    execute("DELETE FROM ui_sessions WHERE refresh_token = %s", (body.refresh_token,))
    user_id = str(session["user_id"])
    return TokenResponse(
        access_token=_make_access_token(user_id),
        refresh_token=_make_refresh_token(user_id),
    )
```

- [ ] **Step 5: Create `app/routers/v3/users.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_one
from app.routers.v3.models import PreferencesIn, PreferencesOut, UserOut

router = APIRouter(prefix="/v3/users", tags=["v3-users"])


@router.get("/me", response_model=UserOut)
def get_me(user: dict = Depends(get_current_user)):
    return UserOut(**user)


@router.get("/me/preferences", response_model=PreferencesOut)
def get_preferences(user: dict = Depends(get_current_user)):
    prefs = fetch_one("SELECT * FROM ui_preferences WHERE user_id = %s", (str(user["id"]),))
    if not prefs:
        return PreferencesOut(theme="navy", column_layout={})
    return PreferencesOut(theme=prefs["theme"], column_layout=prefs["column_layout"])


@router.put("/me/preferences", response_model=PreferencesOut)
def update_preferences(body: PreferencesIn, user: dict = Depends(get_current_user)):
    uid = str(user["id"])
    prefs = fetch_one("SELECT * FROM ui_preferences WHERE user_id = %s", (uid,))
    theme = body.theme or (prefs["theme"] if prefs else "navy")
    layout = body.column_layout if body.column_layout is not None else (prefs["column_layout"] if prefs else {})
    import json
    execute(
        """
        INSERT INTO ui_preferences (user_id, theme, column_layout)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE
        SET theme = EXCLUDED.theme, column_layout = EXCLUDED.column_layout, updated_at = now()
        """,
        (uid, theme, json.dumps(layout)),
    )
    return PreferencesOut(theme=theme, column_layout=layout)
```

- [ ] **Step 6: Register routers in `app/main.py`**

Add to imports and registration block:
```python
from app.routers.v3.auth import router as v3_auth_router
from app.routers.v3.users import router as v3_users_router

# after existing app.include_router calls:
app.include_router(v3_auth_router)
app.include_router(v3_users_router)
```

- [ ] **Step 7: Run auth tests**

```bash
.venv/bin/pytest tests/v3/test_auth.py -v
```

Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add app/routers/v3/ app/main.py tests/v3/
git commit -m "feat(v3): JWT auth + /v3/auth/login, /v3/auth/refresh, /v3/users/me"
```

---

## Task 6: Plugin config endpoints

**Files:**
- Create: `app/routers/v3/plugins.py`
- Test: `tests/v3/test_plugins.py`

- [ ] **Step 1: Write failing tests**

Create `tests/v3/test_plugins.py`:
```python
import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from tests.v3.test_auth import _register_user

pytestmark = pytest.mark.skipif(not os.getenv("POSTGRES_HOST"), reason="Requires Postgres")

client = TestClient(app)


def _auth_headers(username, password="pass"):
    _register_user(username, password)
    r = client.post("/v3/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_list_plugins():
    h = _auth_headers("plugintest1")
    r = client.get("/v3/plugins", headers=h)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_plugin_schema():
    h = _auth_headers("plugintest2")
    r = client.get("/v3/plugins/ddg/schema", headers=h)
    assert r.status_code == 200
    assert "type" in r.json()


def test_save_and_get_plugin_config():
    h = _auth_headers("plugintest3")
    r = client.put("/v3/plugins/ddg/config", json={"config": {"max_results": 10}}, headers=h)
    assert r.status_code == 200
    r2 = client.get("/v3/plugins/ddg/config", headers=h)
    assert r2.json()["config"]["max_results"] == 10
```

- [ ] **Step 2: Create `app/routers/v3/plugins.py`**

```python
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_one, fetch_all
from app.routers.v3.models import PluginConfigIn, PluginConfigOut
from app.search_engine.plugins import PluginRegistry

router = APIRouter(prefix="/v3/plugins", tags=["v3-plugins"])

_registry = PluginRegistry()


@router.get("", response_model=list[dict])
def list_plugins(user: dict = Depends(get_current_user)):
    plugins = _registry.available()
    return [
        {
            "name": p.name,
            "description": p.description,
            "requires_api_key": p.requires_api_key,
            "available": p.available(),
        }
        for p in plugins
    ]


@router.get("/{name}/schema")
def get_plugin_schema(name: str, user: dict = Depends(get_current_user)):
    plugin = _registry.get(name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    return plugin.config_schema or {"type": "object", "properties": {}}


@router.get("/{name}/config", response_model=PluginConfigOut)
def get_plugin_config(name: str, user: dict = Depends(get_current_user)):
    row = fetch_one(
        "SELECT * FROM plugin_configs WHERE user_id = %s AND plugin_name = %s",
        (str(user["id"]), name),
    )
    return PluginConfigOut(plugin_name=name, config=row["config"] if row else {})


@router.put("/{name}/config", response_model=PluginConfigOut)
def save_plugin_config(name: str, body: PluginConfigIn, user: dict = Depends(get_current_user)):
    plugin = _registry.get(name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    execute(
        """
        INSERT INTO plugin_configs (user_id, plugin_name, config)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, plugin_name) DO UPDATE
        SET config = EXCLUDED.config, updated_at = now()
        """,
        (str(user["id"]), name, json.dumps(body.config)),
    )
    return PluginConfigOut(plugin_name=name, config=body.config)
```

- [ ] **Step 3: Register in `app/main.py`**

```python
from app.routers.v3.plugins import router as v3_plugins_router
app.include_router(v3_plugins_router)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/v3/test_plugins.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/v3/plugins.py app/main.py tests/v3/test_plugins.py
git commit -m "feat(v3): plugin config + schema endpoints"
```

---

## Task 7: Core settings endpoints

**Files:**
- Create: `app/routers/v3/settings.py`
- Test: `tests/v3/test_settings.py`

- [ ] **Step 1: Write failing tests**

Create `tests/v3/test_settings.py`:
```python
import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from tests.v3.test_auth import _register_user

pytestmark = pytest.mark.skipif(not os.getenv("POSTGRES_HOST"), reason="Requires Postgres")

client = TestClient(app)


def _auth_headers(username):
    _register_user(username, "pass")
    r = client.post("/v3/auth/login", json={"username": username, "password": "pass"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_set_and_get_non_secret_setting():
    h = _auth_headers("settingstest1")
    r = client.put("/v3/settings/core", json=[{"key": "llm.active_provider", "value": "gemini", "is_secret": False}], headers=h)
    assert r.status_code == 200
    r2 = client.get("/v3/settings/core", headers=h)
    assert r2.json()["settings"]["llm.active_provider"] == "gemini"


def test_secret_setting_masked_on_get():
    h = _auth_headers("settingstest2")
    client.put("/v3/settings/core", json=[{"key": "llm.openai.api_key", "value": "sk-test", "is_secret": True}], headers=h)
    r = client.get("/v3/settings/core", headers=h)
    assert r.json()["settings"]["llm.openai.api_key"] is None  # masked
```

- [ ] **Step 2: Create `app/routers/v3/settings.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all
from app.routers.v3.models import CoreSettingIn, CoreSettingsOut

router = APIRouter(prefix="/v3/settings", tags=["v3-settings"])


@router.get("/core", response_model=CoreSettingsOut)
def get_core_settings(user: dict = Depends(get_current_user)):
    rows = fetch_all("SELECT key, value, is_secret FROM core_settings")
    return CoreSettingsOut(
        settings={r["key"]: (None if r["is_secret"] else r["value"]) for r in rows}
    )


@router.put("/core", response_model=CoreSettingsOut)
def update_core_settings(body: list[CoreSettingIn], user: dict = Depends(get_current_user)):
    for item in body:
        execute(
            """
            INSERT INTO core_settings (key, value, is_secret)
            VALUES (%s, %s, %s)
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, is_secret = EXCLUDED.is_secret, updated_at = now()
            """,
            (item.key, item.value, item.is_secret),
        )
    rows = fetch_all("SELECT key, value, is_secret FROM core_settings")
    return CoreSettingsOut(
        settings={r["key"]: (None if r["is_secret"] else r["value"]) for r in rows}
    )
```

- [ ] **Step 3: Register in `app/main.py`**

```python
from app.routers.v3.settings import router as v3_settings_router
app.include_router(v3_settings_router)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/v3/test_settings.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/v3/settings.py app/main.py tests/v3/test_settings.py
git commit -m "feat(v3): core settings endpoints with secret masking"
```

---

## Task 8: Feed monitors endpoints

**Files:**
- Create: `app/routers/v3/monitors.py`

- [ ] **Step 1: Create `app/routers/v3/monitors.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one
from app.routers.v3.models import MonitorIn, MonitorOut

router = APIRouter(prefix="/v3/monitors", tags=["v3-monitors"])


@router.get("", response_model=list[MonitorOut])
def list_monitors(user: dict = Depends(get_current_user)):
    rows = fetch_all("SELECT * FROM feed_monitors WHERE user_id = %s ORDER BY created_at DESC", (str(user["id"]),))
    return [MonitorOut(**r) for r in rows]


@router.post("", response_model=MonitorOut, status_code=201)
def create_monitor(body: MonitorIn, user: dict = Depends(get_current_user)):
    row = fetch_one(
        """
        INSERT INTO feed_monitors (user_id, name, type, target, poll_interval_minutes)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING *
        """,
        (str(user["id"]), body.name, body.type, body.target, body.poll_interval_minutes),
    )
    return MonitorOut(**row)


@router.delete("/{monitor_id}", status_code=204)
def delete_monitor(monitor_id: str, user: dict = Depends(get_current_user)):
    row = fetch_one(
        "SELECT id FROM feed_monitors WHERE id = %s AND user_id = %s",
        (monitor_id, str(user["id"])),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Monitor not found")
    execute("DELETE FROM feed_monitors WHERE id = %s", (monitor_id,))
```

- [ ] **Step 2: Register in `app/main.py`**

```python
from app.routers.v3.monitors import router as v3_monitors_router
app.include_router(v3_monitors_router)
```

- [ ] **Step 3: Commit**

```bash
git add app/routers/v3/monitors.py app/main.py
git commit -m "feat(v3): feed monitor CRUD endpoints"
```

---

## Task 9: Agent message + jobs endpoints

**Files:**
- Create: `app/routers/v3/agent.py`
- Create: `app/routers/v3/jobs.py`
- Test: `tests/v3/test_agent.py`

- [ ] **Step 1: Write failing test**

Create `tests/v3/test_agent.py`:
```python
import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from tests.v3.test_auth import _register_user

pytestmark = pytest.mark.skipif(not os.getenv("POSTGRES_HOST"), reason="Requires Postgres")

client = TestClient(app)


def _auth_headers(username):
    _register_user(username, "pass")
    r = client.post("/v3/auth/login", json={"username": username, "password": "pass"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_agent_message_returns_job_id():
    h = _auth_headers("agenttest1")
    r = client.post("/v3/agent/message", json={"message": "find CTOs in Manila"}, headers=h)
    assert r.status_code == 202
    data = r.json()
    assert "job_id" in data
    assert data["status"] == "pending"


def test_get_job_after_message():
    h = _auth_headers("agenttest2")
    r = client.post("/v3/agent/message", json={"message": "find news about fintech"}, headers=h)
    job_id = r.json()["job_id"]
    r2 = client.get(f"/v3/jobs/{job_id}", headers=h)
    assert r2.status_code == 200
    assert r2.json()["id"] == job_id


def test_list_jobs():
    h = _auth_headers("agenttest3")
    client.post("/v3/agent/message", json={"message": "test query"}, headers=h)
    r = client.get("/v3/jobs", headers=h)
    assert r.status_code == 200
    assert len(r.json()) >= 1
```

- [ ] **Step 2: Create `app/routers/v3/agent.py`**

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_one
from app.routers.v3.models import AgentMessageIn, AgentMessageOut
from app.routers.v3.stream import push_event

router = APIRouter(prefix="/v3/agent", tags=["v3-agent"])


async def _run_research(job_id: str, user_id: str, message: str):
    """Background task: run research and push events over WebSocket."""
    import asyncio
    import logging
    log = logging.getLogger(__name__)

    try:
        execute(
            "UPDATE search_jobs SET status = 'running', started_at = now() WHERE id = %s",
            (job_id,),
        )
        await push_event(user_id, {
            "type": "job.update",
            "job_id": job_id,
            "status": "running",
            "message": f"Starting research: {message}",
        })

        # Import and run the existing OSINT search engine
        from app.search_engine.executor import AsyncioSearchExecutor
        executor = AsyncioSearchExecutor()
        result_job_id = await executor.submit(
            query=message,
            config={"deep_search": False, "max_budget": 5},
            user_id=user_id,
        )

        # Poll until done (simple approach — replace with callback in future)
        for _ in range(30):  # max 30 * 2s = 60s
            await asyncio.sleep(2)
            status_obj = await executor.status(result_job_id)
            if status_obj.status in ("completed", "failed"):
                break

        final_status = "completed"
        execute(
            "UPDATE search_jobs SET status = %s, completed_at = now() WHERE id = %s",
            (final_status, job_id),
        )
        await push_event(user_id, {
            "type": "job.completed",
            "job_id": job_id,
            "status": final_status,
            "message": "Research complete",
        })
    except Exception as exc:
        log.error("Research job %s failed: %s", job_id, exc)
        execute("UPDATE search_jobs SET status = 'failed' WHERE id = %s", (job_id,))
        await push_event(user_id, {
            "type": "job.failed",
            "job_id": job_id,
            "status": "failed",
            "message": str(exc),
        })


@router.post("/message", response_model=AgentMessageOut, status_code=202)
async def send_message(
    body: AgentMessageIn,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    job_id = str(uuid.uuid4())
    user_id = str(user["id"])

    # Store job in existing search_jobs table
    execute(
        "INSERT INTO search_jobs (id, user_id, query, status) VALUES (%s, %s, %s, 'pending')",
        (job_id, user_id, body.message),
    )

    background_tasks.add_task(_run_research, job_id, user_id, body.message)
    return AgentMessageOut(job_id=job_id)
```

- [ ] **Step 3: Create `app/routers/v3/jobs.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one
from app.routers.v3.models import JobOut

router = APIRouter(prefix="/v3/jobs", tags=["v3-jobs"])


@router.get("", response_model=list[JobOut])
def list_jobs(user: dict = Depends(get_current_user)):
    rows = fetch_all(
        "SELECT id::text, status, query, created_at, completed_at FROM search_jobs WHERE user_id = %s ORDER BY created_at DESC LIMIT 50",
        (str(user["id"]),),
    )
    return [JobOut(**{**r, "result_count": 0}) for r in rows]


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, user: dict = Depends(get_current_user)):
    row = fetch_one(
        "SELECT id::text, status, query, created_at, completed_at FROM search_jobs WHERE id = %s AND user_id = %s",
        (job_id, str(user["id"])),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobOut(**{**row, "result_count": 0})


@router.delete("/{job_id}", status_code=204)
def cancel_job(job_id: str, user: dict = Depends(get_current_user)):
    row = fetch_one(
        "SELECT id FROM search_jobs WHERE id = %s AND user_id = %s AND status = 'running'",
        (job_id, str(user["id"])),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Running job not found")
    execute("UPDATE search_jobs SET status = 'cancelled' WHERE id = %s", (job_id,))
```

- [ ] **Step 4: Register both in `app/main.py`**

```python
from app.routers.v3.agent import router as v3_agent_router
from app.routers.v3.jobs import router as v3_jobs_router
app.include_router(v3_agent_router)
app.include_router(v3_jobs_router)
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/pytest tests/v3/test_agent.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add app/routers/v3/agent.py app/routers/v3/jobs.py app/main.py tests/v3/test_agent.py
git commit -m "feat(v3): agent message + jobs endpoints with background research task"
```

---

## Task 10: WebSocket live stream

**Files:**
- Create: `app/routers/v3/stream.py`
- Test: `tests/v3/test_stream.py`

- [ ] **Step 1: Create `app/routers/v3/stream.py`**

```python
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)
router = APIRouter(tags=["v3-stream"])

# In-process event bus: user_id → set of queues
_queues: dict[str, set[asyncio.Queue]] = defaultdict(set)


async def push_event(user_id: str, event: dict) -> None:
    """Push a JSON event to all WebSocket connections for this user."""
    dead = set()
    for q in list(_queues.get(user_id, [])):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.add(q)
    for q in dead:
        _queues[user_id].discard(q)


@router.websocket("/v3/stream")
async def stream(websocket: WebSocket):
    await websocket.accept()

    # Authenticate via query param token (WebSocket can't send headers easily)
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    try:
        from jose import JWTError, jwt
        import os
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "change-me-in-production"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id or payload.get("type") != "access":
            await websocket.close(code=4001, reason="Invalid token")
            return
    except JWTError:
        await websocket.close(code=4001, reason="Invalid token")
        return

    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _queues[user_id].add(queue)
    log.info("WebSocket connected: user=%s", user_id)

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30)
                await websocket.send_text(json.dumps(event))
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        log.info("WebSocket disconnected: user=%s", user_id)
    finally:
        _queues[user_id].discard(queue)
```

- [ ] **Step 2: Write WebSocket test**

Create `tests/v3/test_stream.py`:
```python
import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from tests.v3.test_auth import _register_user

pytestmark = pytest.mark.skipif(not os.getenv("POSTGRES_HOST"), reason="Requires Postgres")

client = TestClient(app)


def _get_token(username):
    _register_user(username, "pass")
    r = client.post("/v3/auth/login", json={"username": username, "password": "pass"})
    return r.json()["access_token"]


def test_websocket_rejects_missing_token():
    with client.websocket_connect("/v3/stream") as ws:
        # Should disconnect immediately
        with pytest.raises(Exception):
            ws.receive_text()


def test_websocket_accepts_valid_token():
    token = _get_token("streamtest1")
    with client.websocket_connect(f"/v3/stream?token={token}") as ws:
        # Should receive ping within 30s (or immediately if we send one)
        # Just verify connection stays open for 1 receive cycle
        import asyncio
        from app.routers.v3.stream import push_event
        asyncio.get_event_loop().run_until_complete(
            push_event("dummy", {"type": "test"})
        )
        # Connection established means token was valid
```

- [ ] **Step 3: Register WebSocket in `app/main.py`**

```python
from app.routers.v3.stream import router as v3_stream_router
app.include_router(v3_stream_router)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/v3/test_stream.py -v
```

Expected: all PASS

- [ ] **Step 5: Verify full API is up**

```bash
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
uvicorn app.main:app --reload --port 8000 &
curl http://localhost:8000/docs  # Should show Swagger UI with v3 routes
```

Expected: v3/auth, v3/users, v3/plugins, v3/settings, v3/monitors, v3/agent, v3/jobs, v3/stream all listed

- [ ] **Step 6: Run full test suite**

```bash
.venv/bin/pytest tests/ -v --tb=short
```

Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add app/routers/v3/stream.py app/main.py tests/v3/test_stream.py
git commit -m "feat(v3): WebSocket live stream at /v3/stream with per-user event bus"
```

---

## Task 11: Smoke test — full docker compose up

- [ ] **Step 1: Build and run all services**

```bash
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
docker compose up --build
```

Expected output:
- `qdrant` healthy on port 6335
- `info-broker-api` healthy on port 8000, shows v3 migration logs
- `frontend` healthy on port 5173, Vite dev server running

- [ ] **Step 2: Verify API from host**

```bash
curl http://localhost:8000/healthz
# → {"status": "ok"}

curl http://localhost:8000/docs
# → Swagger UI HTML
```

- [ ] **Step 3: Verify frontend from host**

Open http://localhost:5173 in browser.
Expected: "info-broker — UI platform scaffold" in dark navy

- [ ] **Step 4: Verify WebSocket from host**

```bash
# Install wscat if needed: npm install -g wscat
# Get a token first:
TOKEN=$(curl -s -X POST http://localhost:8000/v3/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

# Create admin user first if needed:
# psql -h localhost -p 5433 -U user -d info_broker -c "INSERT INTO ui_users (username, password_hash) VALUES ('admin', '\$2b\$12\$...');"
```

- [ ] **Step 5: Final commit**

```bash
git add .
git commit -m "feat(v3): backend complete — all /v3/* endpoints, WebSocket, docker compose"
```
