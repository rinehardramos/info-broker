# Knowledge Graph + MCP Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent, event-sourced knowledge graph (Neo4j + PG) and complete MCP tool call observability with live process tracking in the admin UI.

**Architecture:** Immutable entity/relationship observations stored in PostgreSQL (source of truth). Neo4j materializes the current graph as a read projection via an async background worker. All MCP tool calls are logged at the execution gateway with session correlation and streamed via WebSocket to a new Live Processes admin panel.

**Tech Stack:** PostgreSQL (event store), Neo4j 5 Community (graph projection), Qdrant (entity embeddings), FastAPI (API), React/TypeScript (frontend), `neo4j` Python driver, `httpx`, `psycopg2`

---

## File Structure

### New Files (Backend)

| File | Responsibility |
|------|---------------|
| `app/knowledge/__init__.py` | Package init |
| `app/knowledge/models.py` | Pydantic models for entities, observations, relationships |
| `app/knowledge/writer.py` | `KnowledgeGraphWriter` — writes observations to PG event store |
| `app/knowledge/materializer.py` | Graph Materializer — reads PG events, resolves entities, upserts Neo4j |
| `app/knowledge/neo4j_client.py` | Neo4j driver wrapper (connect, query, upsert) |
| `app/knowledge/entity_resolution.py` | Entity resolution logic (exact, alias, embedding) |
| `app/routers/v3/knowledge_api.py` | Knowledge graph REST endpoints |
| `app/routers/v3/admin_api.py` | MCP observability REST endpoints (sessions, dashboard) |
| `app/observability/__init__.py` | Package init |
| `app/observability/tracker.py` | MCP tool call logger + session manager |

### New Files (Tests)

| File | Tests |
|------|-------|
| `tests/knowledge/__init__.py` | Package init |
| `tests/knowledge/test_writer.py` | KnowledgeGraphWriter unit tests |
| `tests/knowledge/test_materializer.py` | Graph Materializer unit tests |
| `tests/knowledge/test_entity_resolution.py` | Entity resolution unit tests |
| `tests/knowledge/test_models.py` | Pydantic model validation tests |
| `tests/observability/__init__.py` | Package init |
| `tests/observability/test_tracker.py` | MCP tracker unit tests |
| `tests/v3/test_knowledge_api.py` | Knowledge API integration tests |
| `tests/v3/test_admin_api.py` | Admin/observability API integration tests |

### New Files (Frontend)

| File | Responsibility |
|------|---------------|
| `frontend/src/pages/KnowledgeGraphPage.tsx` | Knowledge graph explorer page |
| `frontend/src/pages/LiveProcessesPage.tsx` | MCP live processes admin page |
| `frontend/src/components/knowledge/EntityList.tsx` | Entity search + list table |
| `frontend/src/components/knowledge/EntityDetail.tsx` | Entity detail + observation timeline |
| `frontend/src/components/knowledge/GraphViewer.tsx` | Subgraph visualization (force-directed) |
| `frontend/src/components/admin/SessionList.tsx` | Live session table |
| `frontend/src/components/admin/SessionDetail.tsx` | Session drill-down with call tree |
| `frontend/src/components/admin/Dashboard.tsx` | Metrics dashboard |

### Modified Files

| File | Change |
|------|--------|
| `app/routers/v3/db.py` | Add 8 new tables to `_MIGRATION` string + seed entity/relationship types |
| `app/routers/v3/nodes_api.py` | Add observability middleware to `execute_node()` |
| `app/main.py` | Register new routers, start materializer background task |
| `mcp_server/client.py` | Add `X-Caller-Identity` and `X-Session-Id` headers |
| `docker-compose.yml` | Add neo4j service + volume + env vars |
| `frontend/src/App.tsx` | Add routes for knowledge graph + live processes pages |
| `frontend/src/api/v3.ts` | Add API methods for knowledge + admin endpoints |
| `frontend/src/components/layout/IconRail.tsx` | Add nav icons for new pages |

---

## Task 1: Database Schema — Event Store + Observability Tables

**Files:**
- Modify: `app/routers/v3/db.py`
- Test: `tests/knowledge/test_models.py`

- [ ] **Step 1: Write test for Pydantic models**

Create `tests/knowledge/__init__.py` (empty) and `tests/knowledge/test_models.py`:

```python
"""Tests for knowledge graph Pydantic models."""
from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_entity_observation_requires_fields():
    from app.knowledge.models import EntityObservationIn
    with pytest.raises(ValidationError):
        EntityObservationIn()  # type: ignore[call-arg]

    obs = EntityObservationIn(
        entity_ref="person::john-doe",
        entity_type="person",
        attribute="name",
        value="John Doe",
        confidence=80,
        source_tool="ddg_search",
    )
    assert obs.entity_ref == "person::john-doe"
    assert obs.confidence == 80


def test_entity_observation_confidence_bounds():
    from app.knowledge.models import EntityObservationIn
    with pytest.raises(ValidationError):
        EntityObservationIn(
            entity_ref="person::x", entity_type="person",
            attribute="name", value="X", confidence=101, source_tool="test",
        )
    with pytest.raises(ValidationError):
        EntityObservationIn(
            entity_ref="person::x", entity_type="person",
            attribute="name", value="X", confidence=-1, source_tool="test",
        )


def test_relationship_observation_requires_fields():
    from app.knowledge.models import RelationshipObservationIn
    with pytest.raises(ValidationError):
        RelationshipObservationIn()  # type: ignore[call-arg]

    rel = RelationshipObservationIn(
        from_entity_ref="person::john-doe",
        to_entity_ref="organization::acme-corp",
        relationship_type="works_at",
        confidence=75,
        evidence="Found in LinkedIn profile",
        source_tool="linkedin_navigator",
    )
    assert rel.relationship_type == "works_at"


def test_mcp_tool_call_log_requires_fields():
    from app.knowledge.models import McpToolCallIn
    call = McpToolCallIn(
        tool_name="run_ddg_search",
        node_type="ddg_search",
        call_id="abc-123",
        caller_identity="is-brain",
    )
    assert call.tool_name == "run_ddg_search"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/knowledge/test_models.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.knowledge'`

- [ ] **Step 3: Create Pydantic models**

Create `app/knowledge/__init__.py` (empty file).

Create `app/knowledge/models.py`:

```python
"""Pydantic models for the knowledge graph event store."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class EntityObservationIn(BaseModel):
    entity_ref: str = Field(..., max_length=512)
    entity_type: str = Field(..., max_length=64)
    attribute: str = Field(..., max_length=128)
    value: str
    confidence: int = Field(..., ge=0, le=100)
    source_run_id: Optional[str] = None
    source_tool: str = Field(..., max_length=128)
    source_url: Optional[str] = None
    observed_at: Optional[datetime] = None


class RelationshipObservationIn(BaseModel):
    from_entity_ref: str = Field(..., max_length=512)
    to_entity_ref: str = Field(..., max_length=512)
    relationship_type: str = Field(..., max_length=64)
    confidence: int = Field(..., ge=0, le=100)
    evidence: Optional[str] = None
    source_run_id: Optional[str] = None
    source_tool: str = Field(..., max_length=128)
    observed_at: Optional[datetime] = None


class McpToolCallIn(BaseModel):
    tool_name: str = Field(..., max_length=128)
    node_type: Optional[str] = Field(None, max_length=64)
    call_id: str
    parent_call_id: Optional[str] = None
    caller_identity: str = Field(..., max_length=256)
    session_id: Optional[str] = None
    input_params: Optional[dict] = None


class EntityOut(BaseModel):
    ref: str
    entity_type: str
    name: str
    aliases: list[str] = []
    confidence: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    attributes: dict = {}
    observation_count: int = 0


class RelationshipOut(BaseModel):
    from_ref: str
    to_ref: str
    relationship_type: str
    confidence: int = 0
    evidence: Optional[str] = None
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    observation_count: int = 0


class McpSessionOut(BaseModel):
    id: str
    caller_identity: str
    session_type: str
    status: str
    tool_call_count: int = 0
    context: dict = {}
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/knowledge/test_models.py -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Add database tables to migration**

Add the following to the end of the `_MIGRATION` string in `app/routers/v3/db.py` (before the closing `"""`):

```sql
-- Knowledge graph: dynamic ontology registry
CREATE TABLE IF NOT EXISTS entity_types (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(64) UNIQUE NOT NULL,
    display_name    VARCHAR(128) NOT NULL,
    icon            VARCHAR(32),
    default_attributes JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS relationship_types (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(64) UNIQUE NOT NULL,
    display_name    VARCHAR(128) NOT NULL,
    from_types      TEXT[] DEFAULT '{}',
    to_types        TEXT[] DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Knowledge graph: immutable observation event store
CREATE TABLE IF NOT EXISTS entity_observations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_ref      VARCHAR(512) NOT NULL,
    entity_type     VARCHAR(64) NOT NULL,
    attribute       VARCHAR(128) NOT NULL,
    value           TEXT NOT NULL,
    confidence      INT NOT NULL DEFAULT 50,
    source_run_id   UUID,
    source_tool     VARCHAR(128),
    source_url      TEXT,
    observed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_entity_obs_ref ON entity_observations (entity_ref);
CREATE INDEX IF NOT EXISTS idx_entity_obs_type ON entity_observations (entity_type);
CREATE INDEX IF NOT EXISTS idx_entity_obs_created ON entity_observations (created_at);

CREATE TABLE IF NOT EXISTS relationship_observations (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_entity_ref   VARCHAR(512) NOT NULL,
    to_entity_ref     VARCHAR(512) NOT NULL,
    relationship_type VARCHAR(64) NOT NULL,
    confidence        INT NOT NULL DEFAULT 50,
    evidence          TEXT,
    source_run_id     UUID,
    source_tool       VARCHAR(128),
    observed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rel_obs_from ON relationship_observations (from_entity_ref);
CREATE INDEX IF NOT EXISTS idx_rel_obs_to ON relationship_observations (to_entity_ref);
CREATE INDEX IF NOT EXISTS idx_rel_obs_created ON relationship_observations (created_at);

CREATE TABLE IF NOT EXISTS entity_aliases (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_ref   VARCHAR(512) NOT NULL,
    alias           VARCHAR(512) NOT NULL,
    alias_type      VARCHAR(32) DEFAULT 'name',
    created_by      VARCHAR(64) DEFAULT 'system',
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (canonical_ref, alias)
);
CREATE INDEX IF NOT EXISTS idx_alias_lookup ON entity_aliases (alias);

CREATE TABLE IF NOT EXISTS graph_materializer_state (
    id                      INT PRIMARY KEY DEFAULT 1,
    last_entity_obs_at      TIMESTAMPTZ,
    last_rel_obs_at         TIMESTAMPTZ,
    last_run_at             TIMESTAMPTZ,
    entities_processed      INT DEFAULT 0,
    relationships_processed INT DEFAULT 0
);

-- MCP Observability: session + tool call tracking
CREATE TABLE IF NOT EXISTS mcp_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    caller_identity VARCHAR(256) NOT NULL,
    user_id         UUID,
    session_type    VARCHAR(32) NOT NULL,
    context         JSONB DEFAULT '{}',
    status          VARCHAR(20) DEFAULT 'active',
    tool_call_count INT DEFAULT 0,
    started_at      TIMESTAMPTZ DEFAULT now(),
    finished_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_mcp_sessions_status ON mcp_sessions (status);
CREATE INDEX IF NOT EXISTS idx_mcp_sessions_started ON mcp_sessions (started_at DESC);

CREATE TABLE IF NOT EXISTS mcp_tool_calls (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID REFERENCES mcp_sessions(id),
    caller_identity VARCHAR(256),
    user_id         UUID,
    tool_name       VARCHAR(128) NOT NULL,
    node_type       VARCHAR(64),
    call_id         UUID NOT NULL,
    parent_call_id  UUID,
    status          VARCHAR(20) DEFAULT 'pending',
    input_params    JSONB,
    result_preview  TEXT,
    result_count    INT,
    error_message   TEXT,
    duration_ms     INT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mcp_calls_session ON mcp_tool_calls (session_id);
CREATE INDEX IF NOT EXISTS idx_mcp_calls_status ON mcp_tool_calls (status);
CREATE INDEX IF NOT EXISTS idx_mcp_calls_created ON mcp_tool_calls (created_at DESC);
```

- [ ] **Step 6: Add entity type + relationship type seed data**

Add the following to the `_SEED` string in `app/routers/v3/db.py` (before the closing `"""`):

```sql
-- Seed entity types
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES
    ('person', 'Person', 'user', '{"name": "", "roles": [], "nationalities": []}'),
    ('organization', 'Organization', 'building', '{"name": "", "industry": "", "jurisdiction": ""}'),
    ('location', 'Location', 'map-pin', '{"name": "", "coords": "", "type": ""}'),
    ('document', 'Document', 'file-text', '{"title": "", "url": "", "classification": ""}'),
    ('technology', 'Technology', 'cpu', '{"name": "", "vendor": "", "category": ""}'),
    ('service', 'Service', 'briefcase', '{"name": "", "provider": "", "category": ""}'),
    ('event', 'Event', 'calendar', '{"name": "", "date": "", "type": ""}'),
    ('asset', 'Asset', 'box', '{"identifier": "", "type": "", "owner": ""}'),
    ('financial_entity', 'Financial Entity', 'dollar-sign', '{"identifier": "", "type": "", "jurisdiction": ""}'),
    ('transaction', 'Transaction', 'arrow-right-left', '{"amount": "", "currency": "", "date": ""}'),
    ('contract', 'Contract', 'file-signature', '{"value": "", "parties": [], "start_date": ""}'),
    ('market_signal', 'Market Signal', 'trending-up', '{"signal_type": "", "magnitude": "", "date": ""}'),
    ('threat_actor', 'Threat Actor', 'shield-alert', '{"name": "", "aliases": [], "attribution_confidence": 0}'),
    ('vulnerability', 'Vulnerability', 'bug', '{"cve_id": "", "severity": "", "affected_products": []}'),
    ('campaign', 'Campaign', 'target', '{"name": "", "timeframe": "", "objectives": ""}'),
    ('indicator', 'Indicator (IOC)', 'fingerprint', '{"type": "", "value": "", "first_seen": ""}'),
    ('malware', 'Malware', 'virus', '{"family": "", "variant": "", "capabilities": []}'),
    ('political_entity', 'Political Entity', 'landmark', '{"name": "", "type": "", "jurisdiction": ""}'),
    ('policy', 'Policy', 'scroll', '{"name": "", "issuer": "", "effective_date": ""}'),
    ('geopolitical_event', 'Geopolitical Event', 'globe', '{"type": "", "date": "", "actors": []}'),
    ('sanction', 'Sanction', 'ban', '{"target": "", "authority": "", "date": ""}'),
    ('infrastructure', 'Infrastructure', 'server', '{"identifier": "", "type": "", "registrar": ""}'),
    ('social_account', 'Social Account', 'at-sign', '{"platform": "", "handle": "", "url": ""}'),
    ('credential', 'Credential', 'key', '{"type": "", "source_breach": "", "exposure_date": ""}'),
    ('communication', 'Communication', 'message-square', '{"medium": "", "date": "", "participants": []}')
ON CONFLICT (name) DO NOTHING;

-- Seed relationship types
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES
    ('works_at', 'Works At', '{person}', '{organization}'),
    ('founded', 'Founded', '{person}', '{organization}'),
    ('subsidiary_of', 'Subsidiary Of', '{organization}', '{organization}'),
    ('competes_with', 'Competes With', '{organization}', '{organization}'),
    ('partners_with', 'Partners With', '{organization}', '{organization}'),
    ('supplies_to', 'Supplies To', '{organization}', '{organization}'),
    ('client_of', 'Client Of', '{organization}', '{organization}'),
    ('invested_in', 'Invested In', '{organization,person}', '{organization}'),
    ('acquired', 'Acquired', '{organization}', '{organization}'),
    ('transacted_with', 'Transacted With', '{organization,person}', '{organization,person}'),
    ('funds', 'Funds', '{financial_entity}', '{organization,campaign}'),
    ('located_in', 'Located In', '{person,organization,asset}', '{location}'),
    ('uses_technology', 'Uses Technology', '{organization}', '{technology}'),
    ('provides_service', 'Provides Service', '{organization}', '{service}'),
    ('owns_domain', 'Owns Domain', '{organization}', '{infrastructure}'),
    ('operates_infrastructure', 'Operates Infrastructure', '{threat_actor}', '{infrastructure}'),
    ('attributed_to', 'Attributed To', '{campaign}', '{threat_actor}'),
    ('exploits', 'Exploits', '{campaign}', '{vulnerability}'),
    ('targets', 'Targets', '{campaign,threat_actor}', '{organization,person}'),
    ('sanctioned_by', 'Sanctioned By', '{organization,person}', '{political_entity}'),
    ('governed_by', 'Governed By', '{policy}', '{political_entity}'),
    ('linked_to_breach', 'Linked To Breach', '{credential}', '{organization}'),
    ('controls', 'Controls', '{person}', '{social_account}'),
    ('mentioned_in', 'Mentioned In', '{person,organization,technology}', '{document}'),
    ('participated_in', 'Participated In', '{person,organization}', '{event}')
ON CONFLICT (name) DO NOTHING;

-- Initialize materializer state
INSERT INTO graph_materializer_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
```

- [ ] **Step 7: Verify migration runs**

```bash
cd /Users/rinehardramos/Projects/info-broker && POSTGRES_HOST=localhost POSTGRES_PORT=5433 uv run python -c "from app.routers.v3.db import run_migrations; run_migrations(); print('OK')"
```

Expected: `OK` with no errors. If Postgres is in Docker, use port 5433 (mapped in docker-compose.yml).

- [ ] **Step 8: Verify tables exist**

```bash
cd /Users/rinehardramos/Projects/info-broker && POSTGRES_HOST=localhost POSTGRES_PORT=5433 uv run python -c "
from app.routers.v3.db import fetch_one, fetch_all
tables = ['entity_types', 'relationship_types', 'entity_observations', 'relationship_observations', 'entity_aliases', 'graph_materializer_state', 'mcp_sessions', 'mcp_tool_calls']
for t in tables:
    row = fetch_one(f\"SELECT count(*) as cnt FROM {t}\")
    print(f'{t}: {row}')
# Check seed data
types = fetch_all('SELECT name FROM entity_types ORDER BY name')
print(f'Entity types seeded: {len(types)}')
rels = fetch_all('SELECT name FROM relationship_types ORDER BY name')
print(f'Relationship types seeded: {len(rels)}')
"
```

Expected: All 8 tables exist. 25 entity types seeded. 25 relationship types seeded.

- [ ] **Step 9: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add app/knowledge/__init__.py app/knowledge/models.py app/routers/v3/db.py tests/knowledge/__init__.py tests/knowledge/test_models.py && git commit -m "feat(kg): add event store schema, ontology seed data, and Pydantic models"
```

---

## Task 2: MCP Observability — Tool Call Tracker

**Files:**
- Create: `app/observability/__init__.py`
- Create: `app/observability/tracker.py`
- Test: `tests/observability/test_tracker.py`

- [ ] **Step 1: Write failing tests for the tracker**

Create `tests/observability/__init__.py` (empty) and `tests/observability/test_tracker.py`:

```python
"""Tests for MCP tool call tracker."""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import patch, MagicMock

import pytest


def _arun(coro):
    return asyncio.run(coro)


def test_start_session_returns_id():
    from app.observability.tracker import McpTracker

    tracker = McpTracker()
    with patch("app.observability.tracker.execute") as mock_exec:
        sid = _arun(tracker.start_session(
            caller_identity="is-brain",
            session_type="is_research",
            context={"query": "test"},
        ))
    assert isinstance(sid, str)
    assert len(sid) == 36  # UUID format
    mock_exec.assert_called_once()


def test_log_tool_call_start():
    from app.observability.tracker import McpTracker

    tracker = McpTracker()
    call_id = str(uuid.uuid4())
    with patch("app.observability.tracker.execute") as mock_exec:
        _arun(tracker.log_call_start(
            session_id=str(uuid.uuid4()),
            tool_name="run_ddg_search",
            node_type="ddg_search",
            call_id=call_id,
            caller_identity="is-brain",
            input_params={"query": "test"},
        ))
    mock_exec.assert_called_once()
    sql = mock_exec.call_args[0][0]
    assert "mcp_tool_calls" in sql
    assert "INSERT" in sql.upper()


def test_log_tool_call_complete():
    from app.observability.tracker import McpTracker

    tracker = McpTracker()
    call_id = str(uuid.uuid4())
    with patch("app.observability.tracker.execute") as mock_exec:
        _arun(tracker.log_call_complete(
            call_id=call_id,
            status="succeeded",
            result_preview="Some results...",
            result_count=5,
            duration_ms=1234,
        ))
    mock_exec.assert_called_once()
    sql = mock_exec.call_args[0][0]
    assert "UPDATE" in sql.upper()
    assert "mcp_tool_calls" in sql


def test_end_session():
    from app.observability.tracker import McpTracker

    tracker = McpTracker()
    sid = str(uuid.uuid4())
    with patch("app.observability.tracker.execute") as mock_exec:
        _arun(tracker.end_session(sid, status="completed"))
    mock_exec.assert_called_once()
    sql = mock_exec.call_args[0][0]
    assert "mcp_sessions" in sql
    assert "UPDATE" in sql.upper()


def test_scrub_secrets_from_params():
    from app.observability.tracker import _scrub_params

    params = {
        "query": "test",
        "api_key": "sk-secret-123",
        "token": "tok-secret",
        "password": "hunter2",
        "normal_field": "safe",
    }
    scrubbed = _scrub_params(params)
    assert scrubbed["query"] == "test"
    assert scrubbed["normal_field"] == "safe"
    assert scrubbed["api_key"] == "***"
    assert scrubbed["token"] == "***"
    assert scrubbed["password"] == "***"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/observability/test_tracker.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.observability'`

- [ ] **Step 3: Implement the tracker**

Create `app/observability/__init__.py` (empty).

Create `app/observability/tracker.py`:

```python
"""MCP tool call tracker — logs all MCP tool executions for observability."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from app.routers.v3.db import execute

log = logging.getLogger(__name__)

_SECRET_KEYS = {"api_key", "token", "password", "secret", "key", "auth", "credential"}


def _scrub_params(params: dict | None) -> dict:
    """Remove sensitive values from tool call parameters."""
    if not params:
        return {}
    scrubbed = {}
    for k, v in params.items():
        if any(s in k.lower() for s in _SECRET_KEYS):
            scrubbed[k] = "***"
        else:
            scrubbed[k] = v
    return scrubbed


class McpTracker:
    """Tracks MCP tool call sessions and individual calls."""

    async def start_session(
        self,
        caller_identity: str,
        session_type: str,
        context: dict | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        sid = session_id or str(uuid.uuid4())
        execute(
            """INSERT INTO mcp_sessions (id, caller_identity, user_id, session_type, context, status)
            VALUES (%s, %s, %s, %s, %s, 'active')
            ON CONFLICT (id) DO NOTHING""",
            (sid, caller_identity, user_id, session_type, json.dumps(context or {})),
        )
        return sid

    async def log_call_start(
        self,
        session_id: str | None,
        tool_name: str,
        node_type: str | None,
        call_id: str,
        caller_identity: str,
        input_params: dict | None = None,
        parent_call_id: str | None = None,
        user_id: str | None = None,
    ) -> str:
        row_id = str(uuid.uuid4())
        scrubbed = _scrub_params(input_params)
        execute(
            """INSERT INTO mcp_tool_calls
            (id, session_id, caller_identity, user_id, tool_name, node_type,
             call_id, parent_call_id, status, input_params)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'executing', %s)""",
            (row_id, session_id, caller_identity, user_id, tool_name,
             node_type, call_id, parent_call_id, json.dumps(scrubbed)),
        )
        # Increment session call count
        if session_id:
            execute(
                "UPDATE mcp_sessions SET tool_call_count = tool_call_count + 1 WHERE id = %s",
                (session_id,),
            )
        return row_id

    async def log_call_complete(
        self,
        call_id: str,
        status: str,
        result_preview: str | None = None,
        result_count: int | None = None,
        duration_ms: int | None = None,
        error_message: str | None = None,
    ) -> None:
        execute(
            """UPDATE mcp_tool_calls
            SET status = %s, result_preview = %s, result_count = %s,
                duration_ms = %s, error_message = %s, updated_at = now()
            WHERE call_id = %s""",
            (status, (result_preview or "")[:500], result_count,
             duration_ms, error_message, call_id),
        )

    async def end_session(self, session_id: str, status: str = "completed") -> None:
        execute(
            "UPDATE mcp_sessions SET status = %s, finished_at = now() WHERE id = %s",
            (status, session_id),
        )


# Singleton tracker instance
tracker = McpTracker()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/observability/test_tracker.py -v
```

Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add app/observability/__init__.py app/observability/tracker.py tests/observability/__init__.py tests/observability/test_tracker.py && git commit -m "feat(obs): add MCP tool call tracker with session management"
```

---

## Task 3: Instrument Node Execution Endpoint

**Files:**
- Modify: `app/routers/v3/nodes_api.py`
- Modify: `app/routers/v3/stream.py` (import only — push_event already exists)
- Test: `tests/observability/test_tracker.py` (extend)

- [ ] **Step 1: Write failing test for instrumented execution**

Add to `tests/observability/test_tracker.py`:

```python
def test_execute_node_logs_tool_call(monkeypatch):
    """The execute_node endpoint should log tool calls to mcp_tool_calls."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # Mock the DB calls to avoid needing real Postgres
    calls_logged = []

    def mock_execute(sql, params=()):
        calls_logged.append((sql, params))

    monkeypatch.setattr("app.observability.tracker.execute", mock_execute)
    monkeypatch.setattr("app.routers.v3.nodes_api._log_execute", mock_execute)

    resp = client.post(
        "/v3/nodes/ddg_search/execute",
        json={"query": "test", "max_results": 5},
        headers={
            "X-API-Key": "changeme",
            "X-Caller-Identity": "test-caller",
            "X-Session-Id": "test-session-123",
        },
    )
    # The endpoint may fail due to no actual DDG, but the logging should have fired
    # Check that at least one INSERT into mcp_tool_calls happened
    insert_calls = [c for c in calls_logged if "mcp_tool_calls" in c[0] and "INSERT" in c[0].upper()]
    assert len(insert_calls) >= 1, f"Expected tool call log INSERT, got: {[c[0][:80] for c in calls_logged]}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/observability/test_tracker.py::test_execute_node_logs_tool_call -v
```

Expected: FAIL (no logging instrumentation exists yet)

- [ ] **Step 3: Instrument the execute_node endpoint**

Modify `app/routers/v3/nodes_api.py` to wrap execution with observability:

```python
"""Node execution endpoint — allows MCP server (and other callers) to run individual pipeline nodes."""
from __future__ import annotations

import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from app.deps import require_api_key
from app.pipeline.nodes import NodeRegistry
from app.pipeline.nodes.base import RunContext

router = APIRouter(prefix="/v3/nodes", tags=["v3-nodes"])
log = logging.getLogger(__name__)


def _get_node(node_type: str):
    NodeRegistry.auto_discover()
    try:
        return NodeRegistry.get(node_type)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown node type: {node_type!r}")


@router.post("/{node_type}/execute")
async def execute_node(
    node_type: str,
    body: dict,
    request: Request,
    _key: str = Depends(require_api_key),
) -> dict:
    """Execute a pipeline node ad-hoc with observability logging."""
    node = _get_node(node_type)

    inputs: list[dict] = body.pop("inputs", [])
    if not inputs and "query" in body:
        inputs = [{"query": body["query"]}]

    # Extract observability headers
    caller_identity = request.headers.get("X-Caller-Identity", "unknown")
    session_id = request.headers.get("X-Session-Id")
    call_id = str(uuid.uuid4())

    # Log tool call start
    try:
        from app.observability.tracker import tracker
        await tracker.log_call_start(
            session_id=session_id,
            tool_name=f"run_{node_type}",
            node_type=node_type,
            call_id=call_id,
            caller_identity=caller_identity,
            input_params=body,
        )
    except Exception as exc:
        log.debug("Observability log_call_start failed (non-fatal): %s", exc)

    # Push WebSocket event
    try:
        from app.routers.v3.stream import push_event
        await push_event("__admin__", {
            "type": "mcp.tool_call.start",
            "session_id": session_id,
            "call_id": call_id,
            "caller": caller_identity,
            "tool": f"run_{node_type}",
            "params_preview": json.dumps(body)[:200],
        })
    except Exception:
        pass

    ctx = RunContext(
        user_id="mcp-system",
        run_id="mcp-adhoc",
        node_id="mcp-adhoc",
    )

    start_ms = time.monotonic_ns() // 1_000_000
    try:
        result = await node.execute(body, inputs, ctx)
    except Exception as exc:
        duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms
        # Log failure
        try:
            from app.observability.tracker import tracker
            await tracker.log_call_complete(
                call_id=call_id,
                status="failed",
                error_message=str(exc)[:500],
                duration_ms=duration_ms,
            )
            from app.routers.v3.stream import push_event
            await push_event("__admin__", {
                "type": "mcp.tool_call.complete",
                "call_id": call_id,
                "status": "failed",
                "duration_ms": duration_ms,
                "error": str(exc)[:200],
            })
        except Exception:
            pass
        log.exception("Node %s execution failed", node_type)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms
    preview = json.dumps(result[:1])[:500] if result else ""

    # Log success
    try:
        from app.observability.tracker import tracker
        await tracker.log_call_complete(
            call_id=call_id,
            status="succeeded",
            result_preview=preview,
            result_count=len(result),
            duration_ms=duration_ms,
        )
        from app.routers.v3.stream import push_event
        await push_event("__admin__", {
            "type": "mcp.tool_call.complete",
            "call_id": call_id,
            "status": "succeeded",
            "duration_ms": duration_ms,
            "result_count": len(result),
        })
    except Exception:
        pass

    return {"status": "success", "items": result, "count": len(result)}


@router.post("/{node_type}/tool-invoke")
async def tool_invoke_node(
    node_type: str,
    body: dict,
    _key: str = Depends(require_api_key),
) -> dict:
    """Invoke a ToolCallable node directly with LLM-provided params."""
    node = _get_node(node_type)

    if not hasattr(node, "tool_invoke"):
        raise HTTPException(
            status_code=400,
            detail=f"Node {node_type!r} does not support tool_invoke",
        )

    ctx = RunContext(
        user_id="mcp-system",
        run_id="mcp-adhoc",
        node_id="mcp-adhoc",
    )

    try:
        result = await node.tool_invoke(body, ctx)
    except Exception as exc:
        log.exception("Node %s tool_invoke failed", node_type)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"status": "success", "items": result, "count": len(result)}
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/observability/ -v
```

Expected: All tests pass (6 total)

- [ ] **Step 5: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add app/routers/v3/nodes_api.py tests/observability/test_tracker.py && git commit -m "feat(obs): instrument node execution endpoint with tool call logging"
```

---

## Task 4: MCP Client — Add Identity Headers

**Files:**
- Modify: `mcp_server/client.py`

- [ ] **Step 1: Update MCP client to pass identity headers**

Replace `mcp_server/client.py` with:

```python
"""Thin async HTTP client for the info-broker REST API."""
from __future__ import annotations

import os

import httpx

API_URL = os.getenv("INFO_BROKER_URL", "http://localhost:8000")
API_KEY = os.getenv("INFO_BROKER_API_KEY", "changeme")

# Observability: caller identity and session correlation
_CALLER_IDENTITY = os.getenv("MCP_CALLER_IDENTITY", "mcp-server")
_SESSION_ID: str | None = None


def set_session(session_id: str, caller_identity: str | None = None) -> None:
    """Set the current session ID and optional caller identity for observability."""
    global _SESSION_ID, _CALLER_IDENTITY
    _SESSION_ID = session_id
    if caller_identity:
        _CALLER_IDENTITY = caller_identity


async def api_call(method: str, path: str, **kwargs) -> dict:
    """Make an authenticated request to the info-broker API.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API path, e.g. "/v3/nodes/ddg_search/execute"
        **kwargs: Passed directly to httpx.AsyncClient.request (json=, params=, etc.)

    Returns:
        Parsed JSON response as a dict.

    Raises:
        httpx.HTTPStatusError: on 4xx/5xx responses.
    """
    async with httpx.AsyncClient(base_url=API_URL, timeout=60) as client:
        headers = {
            "X-API-Key": API_KEY,
            "X-Caller-Identity": _CALLER_IDENTITY,
        }
        if _SESSION_ID:
            headers["X-Session-Id"] = _SESSION_ID
        resp = await client.request(method, path, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 2: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add mcp_server/client.py && git commit -m "feat(obs): add identity headers to MCP client for observability"
```

---

## Task 5: Knowledge Graph Writer

**Files:**
- Create: `app/knowledge/writer.py`
- Test: `tests/knowledge/test_writer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/knowledge/test_writer.py`:

```python
"""Tests for the KnowledgeGraphWriter."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest


def _arun(coro):
    return asyncio.run(coro)


def test_write_entity_observations_from_analyzer_output():
    from app.knowledge.writer import KnowledgeGraphWriter

    analyzer_entities = [
        {
            "name": "John Doe",
            "type": "person",
            "attributes": {"role": "CEO", "company": "Acme Corp"},
            "evidence": [1, 3],
        },
        {
            "name": "Acme Corp",
            "type": "company",
            "attributes": {"industry": "IT", "location": "Manila"},
            "evidence": [1, 2],
        },
    ]

    inserts = []

    def mock_execute(sql, params=()):
        inserts.append((sql, params))

    writer = KnowledgeGraphWriter()
    with patch("app.knowledge.writer.execute", side_effect=mock_execute):
        _arun(writer.write_entities(
            entities=analyzer_entities,
            source_run_id="run-123",
            source_tool="analyzer",
        ))

    # Should have written observations for each entity + each attribute
    # John Doe: name + role + company = 3 observations
    # Acme Corp: name + industry + location = 3 observations
    entity_obs_inserts = [i for i in inserts if "entity_observations" in i[0]]
    assert len(entity_obs_inserts) == 6


def test_write_relationship_observations():
    from app.knowledge.writer import KnowledgeGraphWriter

    relationships = [
        {
            "from": "John Doe",
            "to": "Acme Corp",
            "type": "works_at",
            "evidence": "CEO of Acme Corp per LinkedIn",
        },
    ]

    inserts = []

    def mock_execute(sql, params=()):
        inserts.append((sql, params))

    writer = KnowledgeGraphWriter()
    with patch("app.knowledge.writer.execute", side_effect=mock_execute):
        _arun(writer.write_relationships(
            relationships=relationships,
            source_run_id="run-123",
            source_tool="analyzer",
        ))

    rel_inserts = [i for i in inserts if "relationship_observations" in i[0]]
    assert len(rel_inserts) == 1


def test_generate_entity_ref():
    from app.knowledge.writer import _generate_entity_ref

    ref = _generate_entity_ref("John Doe", "person")
    assert ref == "person::john-doe"

    ref2 = _generate_entity_ref("Acme Corp Inc.", "organization")
    assert ref2 == "organization::acme-corp-inc"

    # Company type maps to organization
    ref3 = _generate_entity_ref("Test LLC", "company")
    assert ref3 == "organization::test-llc"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/knowledge/test_writer.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the writer**

Create `app/knowledge/writer.py`:

```python
"""KnowledgeGraphWriter — bridges analyzer output to the observation event store."""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone

from app.routers.v3.db import execute

log = logging.getLogger(__name__)

# Map common LLM type names to our ontology
_TYPE_MAP = {
    "company": "organization",
    "org": "organization",
    "role/title": "person",
    "role": "person",
    "title": "person",
}


def _generate_entity_ref(name: str, entity_type: str) -> str:
    """Generate a canonical entity reference from name and type.

    Format: {normalized_type}::{slugified_name}
    """
    normalized_type = _TYPE_MAP.get(entity_type.lower(), entity_type.lower())
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{normalized_type}::{slug}"


class KnowledgeGraphWriter:
    """Writes entity and relationship observations to the PG event store."""

    async def write_entities(
        self,
        entities: list[dict],
        source_run_id: str | None = None,
        source_tool: str = "analyzer",
        default_confidence: int = 70,
    ) -> int:
        """Write entity observations from analyzer output.

        Each entity's name + attributes become individual observations.
        Returns the number of observations written.
        """
        count = 0
        now = datetime.now(timezone.utc)

        for entity in entities:
            name = entity.get("name", "")
            raw_type = entity.get("type", "unknown")
            entity_type = _TYPE_MAP.get(raw_type.lower(), raw_type.lower())
            ref = _generate_entity_ref(name, raw_type)
            confidence = entity.get("confidence", default_confidence)

            # Write the name observation
            execute(
                """INSERT INTO entity_observations
                (id, entity_ref, entity_type, attribute, value, confidence,
                 source_run_id, source_tool, observed_at)
                VALUES (%s, %s, %s, 'name', %s, %s, %s, %s, %s)""",
                (str(uuid.uuid4()), ref, entity_type, name,
                 confidence, source_run_id, source_tool, now),
            )
            count += 1

            # Write each attribute as a separate observation
            for attr_key, attr_val in entity.get("attributes", {}).items():
                if not attr_val:
                    continue
                val_str = str(attr_val) if not isinstance(attr_val, str) else attr_val
                execute(
                    """INSERT INTO entity_observations
                    (id, entity_ref, entity_type, attribute, value, confidence,
                     source_run_id, source_tool, observed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (str(uuid.uuid4()), ref, entity_type, attr_key, val_str,
                     confidence, source_run_id, source_tool, now),
                )
                count += 1

        log.info("KG Writer: wrote %d entity observations from %d entities", count, len(entities))
        return count

    async def write_relationships(
        self,
        relationships: list[dict],
        source_run_id: str | None = None,
        source_tool: str = "analyzer",
        default_confidence: int = 60,
    ) -> int:
        """Write relationship observations from analyzer output.

        Returns the number of observations written.
        """
        count = 0
        now = datetime.now(timezone.utc)

        for rel in relationships:
            from_name = rel.get("from", "")
            to_name = rel.get("to", "")
            rel_type = rel.get("type", "unknown")
            evidence = rel.get("evidence", "")
            confidence = rel.get("confidence", default_confidence)

            # Generate refs — we don't know entity types from relationship data alone,
            # so use a generic lookup or default
            from_ref = _generate_entity_ref(from_name, "unknown")
            to_ref = _generate_entity_ref(to_name, "unknown")

            execute(
                """INSERT INTO relationship_observations
                (id, from_entity_ref, to_entity_ref, relationship_type,
                 confidence, evidence, source_run_id, source_tool, observed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (str(uuid.uuid4()), from_ref, to_ref, rel_type,
                 confidence, evidence, source_run_id, source_tool, now),
            )
            count += 1

        log.info("KG Writer: wrote %d relationship observations", count)
        return count

    async def write_from_analyzer(
        self,
        analyzer_output: dict,
        source_run_id: str | None = None,
    ) -> dict:
        """Convenience: write both entities and relationships from analyzer output."""
        entities = analyzer_output.get("entities", [])
        relationships = analyzer_output.get("relationships", [])

        entity_count = await self.write_entities(
            entities, source_run_id=source_run_id, source_tool="analyzer",
        )
        rel_count = await self.write_relationships(
            relationships, source_run_id=source_run_id, source_tool="analyzer",
        )
        return {"entity_observations": entity_count, "relationship_observations": rel_count}


# Singleton
kg_writer = KnowledgeGraphWriter()
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/knowledge/test_writer.py -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add app/knowledge/writer.py tests/knowledge/test_writer.py && git commit -m "feat(kg): add KnowledgeGraphWriter for observation event store"
```

---

## Task 6: Neo4j Docker + Python Client

**Files:**
- Modify: `docker-compose.yml`
- Create: `app/knowledge/neo4j_client.py`
- Test: `tests/knowledge/test_neo4j_client.py`

- [ ] **Step 1: Add Neo4j to docker-compose.yml**

Add after the `temporal-ui` service block and before the `temporal-worker` block:

```yaml
  neo4j:
    image: neo4j:5-community
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-changeme}
      NEO4J_PLUGINS: '["apoc"]'
    volumes:
      - neo4j_data:/data
    healthcheck:
      test: ["CMD", "neo4j", "status"]
      interval: 10s
      timeout: 5s
      retries: 5
```

Add `neo4j_data:` to the `volumes:` section at the bottom.

Add to `info-broker-api` and `temporal-worker` environments:

```yaml
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: ${NEO4J_PASSWORD:-changeme}
```

Add to `info-broker-api` depends_on:

```yaml
      neo4j:
        condition: service_healthy
```

- [ ] **Step 2: Write failing test for Neo4j client**

Create `tests/knowledge/test_neo4j_client.py`:

```python
"""Tests for Neo4j client wrapper (unit tests with mocked driver)."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest


def _arun(coro):
    return asyncio.run(coro)


def test_upsert_entity_creates_merge_query():
    from app.knowledge.neo4j_client import Neo4jClient

    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)

    client = Neo4jClient.__new__(Neo4jClient)
    client._driver = mock_driver

    client.upsert_entity(
        ref="person::john-doe",
        entity_type="person",
        name="John Doe",
        attributes={"role": "CEO"},
        confidence=80,
        first_seen="2026-01-01T00:00:00Z",
        last_seen="2026-05-06T00:00:00Z",
        observation_count=5,
    )

    mock_session.run.assert_called_once()
    cypher = mock_session.run.call_args[0][0]
    assert "MERGE" in cypher
    assert "Person" in cypher
    assert "john-doe" in str(mock_session.run.call_args)


def test_upsert_relationship():
    from app.knowledge.neo4j_client import Neo4jClient

    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)

    client = Neo4jClient.__new__(Neo4jClient)
    client._driver = mock_driver

    client.upsert_relationship(
        from_ref="person::john-doe",
        to_ref="organization::acme-corp",
        rel_type="works_at",
        confidence=75,
        evidence="LinkedIn profile",
        first_seen="2026-01-01T00:00:00Z",
        last_seen="2026-05-06T00:00:00Z",
    )

    mock_session.run.assert_called_once()
    cypher = mock_session.run.call_args[0][0]
    assert "MATCH" in cypher
    assert "WORKS_AT" in cypher


def test_get_subgraph():
    from app.knowledge.neo4j_client import Neo4jClient

    mock_result = MagicMock()
    mock_result.data.return_value = [
        {"n": {"ref": "person::john-doe", "name": "John Doe"}, "r": None, "m": None},
    ]
    mock_session = MagicMock()
    mock_session.run.return_value = mock_result
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)

    client = Neo4jClient.__new__(Neo4jClient)
    client._driver = mock_driver

    result = client.get_subgraph("person::john-doe", hops=2)
    mock_session.run.assert_called_once()
    cypher = mock_session.run.call_args[0][0]
    assert "person::john-doe" in str(mock_session.run.call_args)
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/knowledge/test_neo4j_client.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Install neo4j driver**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv add neo4j
```

- [ ] **Step 5: Implement Neo4j client**

Create `app/knowledge/neo4j_client.py`:

```python
"""Neo4j driver wrapper for the knowledge graph."""
from __future__ import annotations

import logging
import os

from neo4j import GraphDatabase

log = logging.getLogger(__name__)

# Map entity_type to Neo4j label (PascalCase)
_LABEL_MAP = {
    "person": "Person",
    "organization": "Organization",
    "location": "Location",
    "document": "Document",
    "technology": "Technology",
    "service": "Service",
    "event": "Event",
    "asset": "Asset",
    "financial_entity": "FinancialEntity",
    "transaction": "Transaction",
    "contract": "Contract",
    "market_signal": "MarketSignal",
    "threat_actor": "ThreatActor",
    "vulnerability": "Vulnerability",
    "campaign": "Campaign",
    "indicator": "Indicator",
    "malware": "Malware",
    "political_entity": "PoliticalEntity",
    "policy": "Policy",
    "geopolitical_event": "GeopoliticalEvent",
    "sanction": "Sanction",
    "infrastructure": "Infrastructure",
    "social_account": "SocialAccount",
    "credential": "Credential",
    "communication": "Communication",
}

# Map relationship_type to Neo4j rel type (UPPER_SNAKE)
_REL_MAP = {
    "works_at": "WORKS_AT",
    "founded": "FOUNDED",
    "subsidiary_of": "SUBSIDIARY_OF",
    "competes_with": "COMPETES_WITH",
    "partners_with": "PARTNERS_WITH",
    "supplies_to": "SUPPLIES_TO",
    "client_of": "CLIENT_OF",
    "invested_in": "INVESTED_IN",
    "acquired": "ACQUIRED",
    "transacted_with": "TRANSACTED_WITH",
    "funds": "FUNDS",
    "located_in": "LOCATED_IN",
    "uses_technology": "USES_TECHNOLOGY",
    "provides_service": "PROVIDES_SERVICE",
    "owns_domain": "OWNS_DOMAIN",
    "operates_infrastructure": "OPERATES_INFRASTRUCTURE",
    "attributed_to": "ATTRIBUTED_TO",
    "exploits": "EXPLOITS",
    "targets": "TARGETS",
    "sanctioned_by": "SANCTIONED_BY",
    "governed_by": "GOVERNED_BY",
    "linked_to_breach": "LINKED_TO_BREACH",
    "controls": "CONTROLS",
    "mentioned_in": "MENTIONED_IN",
    "participated_in": "PARTICIPATED_IN",
}


class Neo4jClient:
    """Thin wrapper around the Neo4j Python driver."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        self._uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self._user = user or os.getenv("NEO4J_USER", "neo4j")
        self._password = password or os.getenv("NEO4J_PASSWORD", "changeme")
        self._driver = GraphDatabase.driver(self._uri, auth=(self._user, self._password))

    def close(self):
        self._driver.close()

    def ensure_constraints(self):
        """Create uniqueness constraints and indexes if they don't exist."""
        with self._driver.session() as session:
            for label in _LABEL_MAP.values():
                try:
                    session.run(
                        f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.ref IS UNIQUE"
                    )
                except Exception as exc:
                    log.debug("Constraint for %s: %s", label, exc)
            try:
                session.run(
                    "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.name)"
                )
            except Exception as exc:
                log.debug("Index creation: %s", exc)

    def upsert_entity(
        self,
        ref: str,
        entity_type: str,
        name: str,
        attributes: dict | None = None,
        confidence: int = 50,
        first_seen: str | None = None,
        last_seen: str | None = None,
        observation_count: int = 1,
        aliases: list[str] | None = None,
    ) -> None:
        """MERGE an entity node in Neo4j."""
        label = _LABEL_MAP.get(entity_type, "Entity")
        attrs = attributes or {}

        cypher = f"""
        MERGE (n:{label} {{ref: $ref}})
        ON CREATE SET
            n.name = $name,
            n.entity_type = $entity_type,
            n.confidence = $confidence,
            n.first_seen = $first_seen,
            n.last_seen = $last_seen,
            n.observation_count = $observation_count,
            n.aliases = $aliases,
            n.attributes = $attributes
        ON MATCH SET
            n.name = CASE WHEN $confidence >= n.confidence THEN $name ELSE n.name END,
            n.confidence = CASE WHEN $confidence > n.confidence THEN $confidence ELSE n.confidence END,
            n.first_seen = CASE WHEN n.first_seen IS NULL OR $first_seen < n.first_seen THEN $first_seen ELSE n.first_seen END,
            n.last_seen = CASE WHEN n.last_seen IS NULL OR $last_seen > n.last_seen THEN $last_seen ELSE n.last_seen END,
            n.observation_count = n.observation_count + $observation_count,
            n.aliases = CASE WHEN size($aliases) > size(coalesce(n.aliases, [])) THEN $aliases ELSE n.aliases END,
            n.attributes = apoc.map.merge(coalesce(n.attributes, {}), $attributes)
        """
        with self._driver.session() as session:
            session.run(cypher, {
                "ref": ref,
                "name": name,
                "entity_type": entity_type,
                "confidence": confidence,
                "first_seen": first_seen,
                "last_seen": last_seen,
                "observation_count": observation_count,
                "aliases": aliases or [],
                "attributes": str(attrs),
            })

    def upsert_relationship(
        self,
        from_ref: str,
        to_ref: str,
        rel_type: str,
        confidence: int = 50,
        evidence: str | None = None,
        first_seen: str | None = None,
        last_seen: str | None = None,
    ) -> None:
        """MERGE a relationship between two existing entity nodes."""
        neo4j_rel = _REL_MAP.get(rel_type, rel_type.upper())

        cypher = f"""
        MATCH (a {{ref: $from_ref}})
        MATCH (b {{ref: $to_ref}})
        MERGE (a)-[r:{neo4j_rel}]->(b)
        ON CREATE SET
            r.confidence = $confidence,
            r.evidence = $evidence,
            r.first_seen = $first_seen,
            r.last_seen = $last_seen,
            r.observation_count = 1
        ON MATCH SET
            r.confidence = CASE WHEN $confidence > r.confidence THEN $confidence ELSE r.confidence END,
            r.evidence = CASE WHEN $confidence >= r.confidence THEN $evidence ELSE r.evidence END,
            r.first_seen = CASE WHEN r.first_seen IS NULL OR $first_seen < r.first_seen THEN $first_seen ELSE r.first_seen END,
            r.last_seen = CASE WHEN r.last_seen IS NULL OR $last_seen > r.last_seen THEN $last_seen ELSE r.last_seen END,
            r.observation_count = r.observation_count + 1
        """
        with self._driver.session() as session:
            session.run(cypher, {
                "from_ref": from_ref,
                "to_ref": to_ref,
                "confidence": confidence,
                "evidence": evidence or "",
                "first_seen": first_seen,
                "last_seen": last_seen,
            })

    def get_subgraph(self, ref: str, hops: int = 2) -> list[dict]:
        """Get the subgraph around an entity, up to N hops."""
        hops = min(hops, 5)
        cypher = f"""
        MATCH path = (n {{ref: $ref}})-[*1..{hops}]-(m)
        RETURN n, relationships(path) AS rels, m
        LIMIT 200
        """
        with self._driver.session() as session:
            result = session.run(cypher, {"ref": ref})
            return result.data()

    def search_entities(
        self,
        query: str,
        entity_type: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Search entities by name (case-insensitive contains)."""
        if entity_type:
            label = _LABEL_MAP.get(entity_type, "Entity")
            cypher = f"""
            MATCH (n:{label})
            WHERE toLower(n.name) CONTAINS toLower($query)
            RETURN n.ref AS ref, n.name AS name, n.entity_type AS entity_type,
                   n.confidence AS confidence, n.observation_count AS observation_count
            ORDER BY n.confidence DESC
            LIMIT $limit
            """
        else:
            cypher = """
            MATCH (n)
            WHERE n.ref IS NOT NULL AND toLower(n.name) CONTAINS toLower($query)
            RETURN n.ref AS ref, n.name AS name, n.entity_type AS entity_type,
                   n.confidence AS confidence, n.observation_count AS observation_count
            ORDER BY n.confidence DESC
            LIMIT $limit
            """
        with self._driver.session() as session:
            result = session.run(cypher, {"query": query, "limit": limit})
            return result.data()

    def get_entity(self, ref: str) -> dict | None:
        """Get a single entity by ref."""
        cypher = """
        MATCH (n {ref: $ref})
        RETURN n.ref AS ref, n.name AS name, n.entity_type AS entity_type,
               n.confidence AS confidence, n.aliases AS aliases,
               n.attributes AS attributes, n.first_seen AS first_seen,
               n.last_seen AS last_seen, n.observation_count AS observation_count
        """
        with self._driver.session() as session:
            result = session.run(cypher, {"ref": ref})
            data = result.data()
            return data[0] if data else None

    def get_entity_relationships(self, ref: str) -> list[dict]:
        """Get all relationships for an entity."""
        cypher = """
        MATCH (n {ref: $ref})-[r]-(m)
        RETURN type(r) AS relationship_type, r.confidence AS confidence,
               r.evidence AS evidence, m.ref AS other_ref, m.name AS other_name,
               m.entity_type AS other_type,
               CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END AS direction
        ORDER BY r.confidence DESC
        """
        with self._driver.session() as session:
            result = session.run(cypher, {"ref": ref})
            return result.data()
```

- [ ] **Step 6: Run tests**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/knowledge/test_neo4j_client.py -v
```

Expected: 3 tests PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add docker-compose.yml app/knowledge/neo4j_client.py tests/knowledge/test_neo4j_client.py && git commit -m "feat(kg): add Neo4j container and Python client wrapper"
```

---

## Task 7: Graph Materializer

**Files:**
- Create: `app/knowledge/materializer.py`
- Create: `app/knowledge/entity_resolution.py`
- Test: `tests/knowledge/test_materializer.py`
- Test: `tests/knowledge/test_entity_resolution.py`

- [ ] **Step 1: Write failing tests for entity resolution**

Create `tests/knowledge/test_entity_resolution.py`:

```python
"""Tests for entity resolution logic."""
from __future__ import annotations

from unittest.mock import patch


def test_exact_ref_match():
    from app.knowledge.entity_resolution import resolve_entity_ref

    with patch("app.knowledge.entity_resolution.fetch_one") as mock_fetch:
        # No alias found, no embedding match — returns original ref
        mock_fetch.return_value = None
        ref = resolve_entity_ref("person::john-doe", "person", "John Doe")
    assert ref == "person::john-doe"


def test_alias_match():
    from app.knowledge.entity_resolution import resolve_entity_ref

    with patch("app.knowledge.entity_resolution.fetch_one") as mock_fetch:
        mock_fetch.return_value = {"canonical_ref": "person::john-doe-ceo"}
        ref = resolve_entity_ref("person::john-doe", "person", "John Doe")
    assert ref == "person::john-doe-ceo"


def test_normalize_type():
    from app.knowledge.entity_resolution import normalize_entity_type

    assert normalize_entity_type("company") == "organization"
    assert normalize_entity_type("org") == "organization"
    assert normalize_entity_type("person") == "person"
    assert normalize_entity_type("PERSON") == "person"
    assert normalize_entity_type("Unknown Type") == "unknown type"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/knowledge/test_entity_resolution.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement entity resolution**

Create `app/knowledge/entity_resolution.py`:

```python
"""Entity resolution — maps observations to canonical entity refs."""
from __future__ import annotations

import logging

from app.routers.v3.db import execute, fetch_one

log = logging.getLogger(__name__)

_TYPE_MAP = {
    "company": "organization",
    "org": "organization",
    "role/title": "person",
    "role": "person",
    "title": "person",
}


def normalize_entity_type(raw_type: str) -> str:
    """Normalize entity type to match ontology."""
    return _TYPE_MAP.get(raw_type.lower(), raw_type.lower())


def resolve_entity_ref(
    entity_ref: str,
    entity_type: str,
    entity_name: str,
) -> str:
    """Resolve an entity ref to its canonical form.

    Resolution order:
    1. Alias lookup in entity_aliases table
    2. Return original ref if no alias found

    Embedding-based similarity is handled by the materializer in a separate pass
    to avoid blocking the write path.
    """
    # Check alias table
    alias_row = fetch_one(
        "SELECT canonical_ref FROM entity_aliases WHERE alias = %s",
        (entity_ref,),
    )
    if alias_row:
        log.debug("Resolved alias %s -> %s", entity_ref, alias_row["canonical_ref"])
        return alias_row["canonical_ref"]

    # Also check by name (case-insensitive)
    name_row = fetch_one(
        "SELECT canonical_ref FROM entity_aliases WHERE LOWER(alias) = LOWER(%s)",
        (entity_name,),
    )
    if name_row:
        log.debug("Resolved name alias %s -> %s", entity_name, name_row["canonical_ref"])
        return name_row["canonical_ref"]

    return entity_ref


def create_alias(canonical_ref: str, alias: str, alias_type: str = "name", created_by: str = "materializer") -> None:
    """Create an alias mapping."""
    execute(
        """INSERT INTO entity_aliases (canonical_ref, alias, alias_type, created_by)
        VALUES (%s, %s, %s, %s) ON CONFLICT (canonical_ref, alias) DO NOTHING""",
        (canonical_ref, alias, alias_type, created_by),
    )
```

- [ ] **Step 4: Run entity resolution tests**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/knowledge/test_entity_resolution.py -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Write failing tests for materializer**

Create `tests/knowledge/test_materializer.py`:

```python
"""Tests for the Graph Materializer."""
from __future__ import annotations

import asyncio
from unittest.mock import patch, MagicMock


def _arun(coro):
    return asyncio.run(coro)


def test_materialize_entities_processes_new_observations():
    from app.knowledge.materializer import GraphMaterializer

    # Mock: 2 new entity observations for the same entity
    observations = [
        {
            "entity_ref": "person::john-doe",
            "entity_type": "person",
            "attribute": "name",
            "value": "John Doe",
            "confidence": 80,
            "observed_at": "2026-05-06T00:00:00+00:00",
        },
        {
            "entity_ref": "person::john-doe",
            "entity_type": "person",
            "attribute": "role",
            "value": "CEO",
            "confidence": 75,
            "observed_at": "2026-05-06T00:00:00+00:00",
        },
    ]

    mock_neo4j = MagicMock()

    with patch("app.knowledge.materializer.fetch_all", return_value=observations), \
         patch("app.knowledge.materializer.fetch_one", return_value={"last_entity_obs_at": None}), \
         patch("app.knowledge.materializer.execute"), \
         patch("app.knowledge.entity_resolution.fetch_one", return_value=None):

        mat = GraphMaterializer(neo4j_client=mock_neo4j)
        count = _arun(mat.materialize_entities())

    # Should have upserted 1 entity (grouped by ref)
    assert mock_neo4j.upsert_entity.call_count == 1
    call_kwargs = mock_neo4j.upsert_entity.call_args
    assert "john-doe" in str(call_kwargs)


def test_materialize_relationships():
    from app.knowledge.materializer import GraphMaterializer

    observations = [
        {
            "from_entity_ref": "person::john-doe",
            "to_entity_ref": "organization::acme-corp",
            "relationship_type": "works_at",
            "confidence": 75,
            "evidence": "LinkedIn profile",
            "observed_at": "2026-05-06T00:00:00+00:00",
        },
    ]

    mock_neo4j = MagicMock()

    with patch("app.knowledge.materializer.fetch_all", return_value=observations), \
         patch("app.knowledge.materializer.fetch_one", return_value={"last_rel_obs_at": None}), \
         patch("app.knowledge.materializer.execute"):

        mat = GraphMaterializer(neo4j_client=mock_neo4j)
        count = _arun(mat.materialize_relationships())

    assert mock_neo4j.upsert_relationship.call_count == 1
```

- [ ] **Step 6: Run test to verify it fails**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/knowledge/test_materializer.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 7: Implement the materializer**

Create `app/knowledge/materializer.py`:

```python
"""Graph Materializer — reads PG observation events and upserts Neo4j."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone

from app.knowledge.entity_resolution import resolve_entity_ref, create_alias
from app.routers.v3.db import execute, fetch_all, fetch_one

log = logging.getLogger(__name__)


class GraphMaterializer:
    """Reads new observations from PG and upserts Neo4j graph."""

    def __init__(self, neo4j_client=None):
        self._neo4j = neo4j_client

    async def materialize_entities(self) -> int:
        """Process new entity observations since last checkpoint."""
        state = fetch_one("SELECT last_entity_obs_at FROM graph_materializer_state WHERE id = 1")
        last_at = state.get("last_entity_obs_at") if state else None

        if last_at:
            observations = fetch_all(
                """SELECT entity_ref, entity_type, attribute, value, confidence, observed_at
                FROM entity_observations WHERE created_at > %s ORDER BY created_at""",
                (last_at,),
            )
        else:
            observations = fetch_all(
                """SELECT entity_ref, entity_type, attribute, value, confidence, observed_at
                FROM entity_observations ORDER BY created_at""",
            )

        if not observations:
            return 0

        # Group by entity_ref
        grouped: dict[str, list[dict]] = defaultdict(list)
        for obs in observations:
            resolved_ref = resolve_entity_ref(obs["entity_ref"], obs["entity_type"], obs.get("value", ""))
            if resolved_ref != obs["entity_ref"]:
                create_alias(resolved_ref, obs["entity_ref"])
            grouped[resolved_ref].append(obs)

        # Upsert each entity
        count = 0
        for ref, obs_list in grouped.items():
            entity_type = obs_list[0]["entity_type"]

            # Build attributes from observations (highest confidence wins per attribute)
            attrs: dict[str, str] = {}
            name = ref.split("::")[-1].replace("-", " ").title()
            max_confidence = 0
            first_seen = None
            last_seen = None

            for obs in sorted(obs_list, key=lambda x: x["confidence"], reverse=True):
                attr = obs["attribute"]
                if attr not in attrs:
                    attrs[attr] = obs["value"]
                if attr == "name":
                    name = obs["value"]
                max_confidence = max(max_confidence, obs["confidence"])
                obs_time = str(obs["observed_at"])
                if first_seen is None or obs_time < first_seen:
                    first_seen = obs_time
                if last_seen is None or obs_time > last_seen:
                    last_seen = obs_time

            self._neo4j.upsert_entity(
                ref=ref,
                entity_type=entity_type,
                name=name,
                attributes={k: v for k, v in attrs.items() if k != "name"},
                confidence=max_confidence,
                first_seen=first_seen,
                last_seen=last_seen,
                observation_count=len(obs_list),
            )
            count += 1

        # Update checkpoint
        latest = max(str(o["observed_at"]) for o in observations) if observations else None
        if latest:
            execute(
                """UPDATE graph_materializer_state
                SET last_entity_obs_at = %s, last_run_at = now(),
                    entities_processed = entities_processed + %s
                WHERE id = 1""",
                (latest, count),
            )

        log.info("Materializer: upserted %d entities from %d observations", count, len(observations))
        return count

    async def materialize_relationships(self) -> int:
        """Process new relationship observations since last checkpoint."""
        state = fetch_one("SELECT last_rel_obs_at FROM graph_materializer_state WHERE id = 1")
        last_at = state.get("last_rel_obs_at") if state else None

        if last_at:
            observations = fetch_all(
                """SELECT from_entity_ref, to_entity_ref, relationship_type,
                       confidence, evidence, observed_at
                FROM relationship_observations WHERE created_at > %s ORDER BY created_at""",
                (last_at,),
            )
        else:
            observations = fetch_all(
                """SELECT from_entity_ref, to_entity_ref, relationship_type,
                       confidence, evidence, observed_at
                FROM relationship_observations ORDER BY created_at""",
            )

        if not observations:
            return 0

        count = 0
        for obs in observations:
            self._neo4j.upsert_relationship(
                from_ref=obs["from_entity_ref"],
                to_ref=obs["to_entity_ref"],
                rel_type=obs["relationship_type"],
                confidence=obs["confidence"],
                evidence=obs.get("evidence", ""),
                first_seen=str(obs["observed_at"]),
                last_seen=str(obs["observed_at"]),
            )
            count += 1

        latest = max(str(o["observed_at"]) for o in observations) if observations else None
        if latest:
            execute(
                """UPDATE graph_materializer_state
                SET last_rel_obs_at = %s, last_run_at = now(),
                    relationships_processed = relationships_processed + %s
                WHERE id = 1""",
                (latest, count),
            )

        log.info("Materializer: upserted %d relationships", count)
        return count

    async def run_once(self) -> dict:
        """Run one materialization cycle."""
        entities = await self.materialize_entities()
        relationships = await self.materialize_relationships()
        return {"entities": entities, "relationships": relationships}


async def materializer_loop(interval_seconds: int = 5):
    """Background loop that materializes the graph periodically."""
    from app.knowledge.neo4j_client import Neo4jClient

    try:
        client = Neo4jClient()
        client.ensure_constraints()
    except Exception as exc:
        log.warning("Neo4j not available, materializer disabled: %s", exc)
        return

    mat = GraphMaterializer(neo4j_client=client)
    log.info("Graph materializer started (interval=%ds)", interval_seconds)

    while True:
        try:
            result = await mat.run_once()
            if result["entities"] or result["relationships"]:
                log.info("Materialized: %s", result)
        except Exception as exc:
            log.error("Materializer error: %s", exc)
        await asyncio.sleep(interval_seconds)
```

- [ ] **Step 8: Run materializer tests**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/knowledge/test_materializer.py tests/knowledge/test_entity_resolution.py -v
```

Expected: 5 tests PASS

- [ ] **Step 9: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add app/knowledge/entity_resolution.py app/knowledge/materializer.py tests/knowledge/test_entity_resolution.py tests/knowledge/test_materializer.py && git commit -m "feat(kg): add graph materializer and entity resolution"
```

---

## Task 8: Knowledge Graph API + Admin API

**Files:**
- Create: `app/routers/v3/knowledge_api.py`
- Create: `app/routers/v3/admin_api.py`
- Modify: `app/main.py`

- [ ] **Step 1: Create knowledge API router**

Create `app/routers/v3/knowledge_api.py`:

```python
"""Knowledge graph API — entity search, detail, subgraph, observations."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import fetch_all, fetch_one

router = APIRouter(prefix="/v3/knowledge", tags=["v3-knowledge"])
log = logging.getLogger(__name__)


@router.get("/entity-types")
def list_entity_types(user: dict = Depends(get_current_user)):
    return fetch_all("SELECT name, display_name, icon FROM entity_types ORDER BY name")


@router.get("/relationship-types")
def list_relationship_types(user: dict = Depends(get_current_user)):
    return fetch_all("SELECT name, display_name, from_types, to_types FROM relationship_types ORDER BY name")


@router.get("/entities")
def search_entities(
    q: str = "",
    entity_type: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    """Search entities in Neo4j by name."""
    try:
        from app.knowledge.neo4j_client import Neo4jClient
        client = Neo4jClient()
        results = client.search_entities(q, entity_type=entity_type, limit=limit)
        client.close()
        return results
    except Exception as exc:
        log.warning("Neo4j search failed, falling back to PG: %s", exc)
        # Fallback: search entity_observations
        if q:
            rows = fetch_all(
                """SELECT DISTINCT entity_ref AS ref, entity_type,
                    MAX(CASE WHEN attribute = 'name' THEN value END) AS name,
                    MAX(confidence) AS confidence,
                    COUNT(*) AS observation_count
                FROM entity_observations
                WHERE value ILIKE %s
                GROUP BY entity_ref, entity_type
                ORDER BY MAX(confidence) DESC LIMIT %s""",
                (f"%{q}%", limit),
            )
        else:
            rows = fetch_all(
                """SELECT DISTINCT entity_ref AS ref, entity_type,
                    MAX(CASE WHEN attribute = 'name' THEN value END) AS name,
                    MAX(confidence) AS confidence,
                    COUNT(*) AS observation_count
                FROM entity_observations
                GROUP BY entity_ref, entity_type
                ORDER BY MAX(confidence) DESC LIMIT %s""",
                (limit,),
            )
        return [dict(r) for r in rows]


@router.get("/entities/{ref:path}/observations")
def get_entity_observations(ref: str, user: dict = Depends(get_current_user)):
    """Get all observations for an entity, ordered by time."""
    rows = fetch_all(
        """SELECT attribute, value, confidence, source_tool, source_url, observed_at
        FROM entity_observations WHERE entity_ref = %s
        ORDER BY observed_at DESC""",
        (ref,),
    )
    return [dict(r) for r in rows]


@router.get("/entities/{ref:path}/graph")
def get_entity_graph(
    ref: str,
    hops: int = Query(2, ge=1, le=5),
    user: dict = Depends(get_current_user),
):
    """Get the subgraph around an entity."""
    try:
        from app.knowledge.neo4j_client import Neo4jClient
        client = Neo4jClient()
        result = client.get_subgraph(ref, hops=hops)
        client.close()
        return result
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Neo4j unavailable: {exc}")


@router.get("/entities/{ref:path}")
def get_entity_detail(ref: str, user: dict = Depends(get_current_user)):
    """Get entity detail with relationships."""
    try:
        from app.knowledge.neo4j_client import Neo4jClient
        client = Neo4jClient()
        entity = client.get_entity(ref)
        relationships = client.get_entity_relationships(ref) if entity else []
        client.close()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        return {"entity": entity, "relationships": relationships}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Neo4j unavailable: {exc}")


@router.get("/stats")
def get_knowledge_stats(user: dict = Depends(get_current_user)):
    """Get knowledge graph statistics."""
    entity_count = fetch_one("SELECT COUNT(DISTINCT entity_ref) AS cnt FROM entity_observations")
    rel_count = fetch_one("SELECT COUNT(*) AS cnt FROM relationship_observations")
    type_counts = fetch_all(
        """SELECT entity_type, COUNT(DISTINCT entity_ref) AS cnt
        FROM entity_observations GROUP BY entity_type ORDER BY cnt DESC"""
    )
    state = fetch_one("SELECT * FROM graph_materializer_state WHERE id = 1")
    return {
        "total_entities": entity_count["cnt"] if entity_count else 0,
        "total_relationships": rel_count["cnt"] if rel_count else 0,
        "entities_by_type": [dict(r) for r in type_counts],
        "materializer_state": dict(state) if state else None,
    }


@router.get("/timeline")
def get_timeline(
    start: str | None = None,
    end: str | None = None,
    entity_ref: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    user: dict = Depends(get_current_user),
):
    """Get observation timeline."""
    conditions = []
    params: list = []

    if start:
        conditions.append("observed_at >= %s")
        params.append(start)
    if end:
        conditions.append("observed_at <= %s")
        params.append(end)
    if entity_ref:
        conditions.append("entity_ref = %s")
        params.append(entity_ref)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    rows = fetch_all(
        f"""SELECT entity_ref, entity_type, attribute, value, confidence,
               source_tool, observed_at
        FROM entity_observations {where}
        ORDER BY observed_at DESC LIMIT %s""",
        tuple(params),
    )
    return [dict(r) for r in rows]
```

- [ ] **Step 2: Create admin API router**

Create `app/routers/v3/admin_api.py`:

```python
"""Admin API — MCP observability endpoints (sessions, dashboard, tool stats)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import fetch_all, fetch_one

router = APIRouter(prefix="/v3/admin", tags=["v3-admin"])
log = logging.getLogger(__name__)


@router.get("/sessions")
def list_sessions(
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    """List active + recent MCP sessions."""
    if status:
        rows = fetch_all(
            """SELECT id, caller_identity, session_type, status, tool_call_count,
                  context, started_at, finished_at
            FROM mcp_sessions WHERE status = %s
            ORDER BY started_at DESC LIMIT %s""",
            (status, limit),
        )
    else:
        rows = fetch_all(
            """SELECT id, caller_identity, session_type, status, tool_call_count,
                  context, started_at, finished_at
            FROM mcp_sessions
            ORDER BY started_at DESC LIMIT %s""",
            (limit,),
        )
    return [dict(r) for r in rows]


@router.get("/sessions/{session_id}")
def get_session(session_id: str, user: dict = Depends(get_current_user)):
    """Get session detail with call tree."""
    session = fetch_one(
        """SELECT id, caller_identity, session_type, status, tool_call_count,
              context, started_at, finished_at
        FROM mcp_sessions WHERE id = %s""",
        (session_id,),
    )
    if not session:
        return {"error": "Session not found"}

    calls = fetch_all(
        """SELECT id, tool_name, node_type, call_id, parent_call_id, status,
              input_params, result_preview, result_count, error_message,
              duration_ms, created_at
        FROM mcp_tool_calls WHERE session_id = %s
        ORDER BY created_at""",
        (session_id,),
    )
    return {"session": dict(session), "calls": [dict(c) for c in calls]}


@router.get("/dashboard")
def get_dashboard(user: dict = Depends(get_current_user)):
    """Aggregated metrics for the observability dashboard."""
    active = fetch_one("SELECT COUNT(*) AS cnt FROM mcp_sessions WHERE status = 'active'")
    total_calls = fetch_one("SELECT COUNT(*) AS cnt FROM mcp_tool_calls")
    error_rate = fetch_one(
        """SELECT
            COUNT(*) FILTER (WHERE status = 'failed') AS errors,
            COUNT(*) AS total
        FROM mcp_tool_calls
        WHERE created_at > now() - interval '1 hour'"""
    )
    avg_duration = fetch_one(
        """SELECT AVG(duration_ms) AS avg_ms
        FROM mcp_tool_calls
        WHERE status = 'succeeded' AND created_at > now() - interval '1 hour'"""
    )
    top_tools = fetch_all(
        """SELECT tool_name, COUNT(*) AS call_count, AVG(duration_ms) AS avg_ms
        FROM mcp_tool_calls
        WHERE created_at > now() - interval '24 hours'
        GROUP BY tool_name ORDER BY call_count DESC LIMIT 10"""
    )

    return {
        "active_sessions": active["cnt"] if active else 0,
        "total_tool_calls": total_calls["cnt"] if total_calls else 0,
        "error_rate_last_hour": {
            "errors": error_rate["errors"] if error_rate else 0,
            "total": error_rate["total"] if error_rate else 0,
        },
        "avg_duration_ms": round(avg_duration["avg_ms"] or 0, 1) if avg_duration else 0,
        "top_tools_24h": [dict(r) for r in top_tools],
    }


@router.get("/tools/stats")
def get_tool_stats(user: dict = Depends(get_current_user)):
    """Per-tool usage statistics."""
    rows = fetch_all(
        """SELECT tool_name,
            COUNT(*) AS total_calls,
            COUNT(*) FILTER (WHERE status = 'succeeded') AS succeeded,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed,
            AVG(duration_ms) FILTER (WHERE status = 'succeeded') AS avg_duration_ms,
            MAX(created_at) AS last_used
        FROM mcp_tool_calls
        GROUP BY tool_name ORDER BY total_calls DESC"""
    )
    return [dict(r) for r in rows]
```

- [ ] **Step 3: Register routers and start materializer in main.py**

Add to `app/main.py` after the existing router imports (around line 156):

```python
from app.routers.v3.knowledge_api import router as v3_knowledge_router  # noqa: E402
from app.routers.v3.admin_api import router as v3_admin_router  # noqa: E402
```

Add after the existing `app.include_router(v3_research_router)` line:

```python
app.include_router(v3_knowledge_router)
app.include_router(v3_admin_router)
```

Add to the `lifespan` function (after the `v3_migrate()` call, around line 109):

```python
    # Start graph materializer background task
    import asyncio
    try:
        from app.knowledge.materializer import materializer_loop
        asyncio.create_task(materializer_loop(interval_seconds=5))
    except Exception as exc:
        _log.warning("Graph materializer not started: %s", exc)
```

- [ ] **Step 4: Run all knowledge tests**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/knowledge/ tests/observability/ -v
```

Expected: All tests PASS (14+ total)

- [ ] **Step 5: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add app/routers/v3/knowledge_api.py app/routers/v3/admin_api.py app/main.py && git commit -m "feat(kg): add knowledge graph and admin observability API endpoints"
```

---

## Task 9: Wire Analyzer Output to Knowledge Graph

**Files:**
- Modify: `app/routers/v3/research_api.py`

- [ ] **Step 1: Wire KG writer into the analyze endpoint**

In `app/routers/v3/research_api.py`, modify the `analyze_findings` function to also write to the knowledge graph after analysis:

Add after `result = await node.execute(config, items, ctx)` (around line 179):

```python
    # Write analysis results to knowledge graph
    if result:
        try:
            from app.knowledge.writer import kg_writer
            analysis = result[0] if isinstance(result, list) else result
            kg_result = await kg_writer.write_from_analyzer(
                analysis, source_run_id="analyze-adhoc",
            )
            log.info("KG Writer: %s", kg_result)
        except Exception as exc:
            log.warning("KG write failed (non-fatal): %s", exc)
```

- [ ] **Step 2: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add app/routers/v3/research_api.py && git commit -m "feat(kg): wire analyzer output to knowledge graph writer"
```

---

## Task 10: Frontend — API Client Methods

**Files:**
- Modify: `frontend/src/api/v3.ts`

- [ ] **Step 1: Add knowledge graph and admin API methods**

Add to the end of `frontend/src/api/v3.ts`:

```typescript
// --- Knowledge Graph ---

export interface EntityOut {
  ref: string
  entity_type: string
  name: string
  confidence: number
  observation_count: number
  aliases?: string[]
  attributes?: Record<string, string>
  first_seen?: string
  last_seen?: string
}

export interface EntityObservation {
  attribute: string
  value: string
  confidence: number
  source_tool: string
  source_url: string | null
  observed_at: string
}

export interface KnowledgeStats {
  total_entities: number
  total_relationships: number
  entities_by_type: { entity_type: string; cnt: number }[]
  materializer_state: Record<string, unknown> | null
}

export const getEntityTypes = () =>
  api.get<{ name: string; display_name: string; icon: string }[]>('/v3/knowledge/entity-types').then(r => r.data)

export const searchEntities = (q: string, entityType?: string, limit = 50) =>
  api.get<EntityOut[]>('/v3/knowledge/entities', { params: { q, entity_type: entityType, limit } }).then(r => r.data)

export const getEntityDetail = (ref: string) =>
  api.get<{ entity: EntityOut; relationships: Record<string, unknown>[] }>(`/v3/knowledge/entities/${encodeURIComponent(ref)}`).then(r => r.data)

export const getEntityObservations = (ref: string) =>
  api.get<EntityObservation[]>(`/v3/knowledge/entities/${encodeURIComponent(ref)}/observations`).then(r => r.data)

export const getEntityGraph = (ref: string, hops = 2) =>
  api.get(`/v3/knowledge/entities/${encodeURIComponent(ref)}/graph`, { params: { hops } }).then(r => r.data)

export const getKnowledgeStats = () =>
  api.get<KnowledgeStats>('/v3/knowledge/stats').then(r => r.data)

export const getKnowledgeTimeline = (params?: { start?: string; end?: string; entity_ref?: string; limit?: number }) =>
  api.get<EntityObservation[]>('/v3/knowledge/timeline', { params }).then(r => r.data)

// --- Admin / Observability ---

export interface McpSession {
  id: string
  caller_identity: string
  session_type: string
  status: string
  tool_call_count: number
  context: Record<string, unknown>
  started_at: string
  finished_at: string | null
}

export interface McpToolCall {
  id: string
  tool_name: string
  node_type: string | null
  call_id: string
  parent_call_id: string | null
  status: string
  input_params: Record<string, unknown> | null
  result_preview: string | null
  result_count: number | null
  error_message: string | null
  duration_ms: number | null
  created_at: string
}

export interface DashboardMetrics {
  active_sessions: number
  total_tool_calls: number
  error_rate_last_hour: { errors: number; total: number }
  avg_duration_ms: number
  top_tools_24h: { tool_name: string; call_count: number; avg_ms: number }[]
}

export const listMcpSessions = (status?: string, limit = 50) =>
  api.get<McpSession[]>('/v3/admin/sessions', { params: { status, limit } }).then(r => r.data)

export const getMcpSession = (id: string) =>
  api.get<{ session: McpSession; calls: McpToolCall[] }>(`/v3/admin/sessions/${id}`).then(r => r.data)

export const getDashboardMetrics = () =>
  api.get<DashboardMetrics>('/v3/admin/dashboard').then(r => r.data)

export const getToolStats = () =>
  api.get<{ tool_name: string; total_calls: number; succeeded: number; failed: number; avg_duration_ms: number; last_used: string }[]>('/v3/admin/tools/stats').then(r => r.data)
```

- [ ] **Step 2: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add frontend/src/api/v3.ts && git commit -m "feat(fe): add knowledge graph and admin observability API methods"
```

---

## Task 11: Frontend — Live Processes Page

**Files:**
- Create: `frontend/src/pages/LiveProcessesPage.tsx`
- Create: `frontend/src/components/admin/SessionList.tsx`
- Create: `frontend/src/components/admin/Dashboard.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/IconRail.tsx`

- [ ] **Step 1: Create SessionList component**

Create `frontend/src/components/admin/SessionList.tsx`:

```tsx
import { useState, useEffect } from 'react'
import { listMcpSessions, getMcpSession, type McpSession, type McpToolCall } from '../../api/v3'
import { useWebSocket } from '../../hooks/useWebSocket'

export default function SessionList() {
  const [sessions, setSessions] = useState<McpSession[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [calls, setCalls] = useState<McpToolCall[]>([])
  const ws = useWebSocket()

  useEffect(() => {
    listMcpSessions(undefined, 50).then(setSessions).catch(() => {})
    const interval = setInterval(() => {
      listMcpSessions(undefined, 50).then(setSessions).catch(() => {})
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  // Listen for real-time MCP events
  useEffect(() => {
    if (!ws) return
    const handler = (ev: MessageEvent) => {
      try {
        const data = JSON.parse(ev.data)
        if (data.type === 'mcp.session.start' || data.type === 'mcp.session.complete') {
          listMcpSessions(undefined, 50).then(setSessions).catch(() => {})
        }
        if (data.type === 'mcp.tool_call.start' || data.type === 'mcp.tool_call.complete') {
          if (selected) {
            getMcpSession(selected).then(r => setCalls(r.calls)).catch(() => {})
          }
        }
      } catch {}
    }
    ws.addEventListener('message', handler)
    return () => ws.removeEventListener('message', handler)
  }, [ws, selected])

  const selectSession = async (id: string) => {
    setSelected(id)
    try {
      const detail = await getMcpSession(id)
      setCalls(detail.calls)
    } catch {}
  }

  return (
    <div className="flex gap-4 h-full">
      {/* Session List */}
      <div className="w-1/2 overflow-auto">
        <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--muted)' }}>Sessions</h3>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ color: 'var(--muted)' }}>
              <th className="text-left p-1">Status</th>
              <th className="text-left p-1">Caller</th>
              <th className="text-left p-1">Type</th>
              <th className="text-right p-1">Tools</th>
              <th className="text-right p-1">Started</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map(s => (
              <tr
                key={s.id}
                onClick={() => selectSession(s.id)}
                className="cursor-pointer hover:opacity-80"
                style={{
                  background: selected === s.id ? 'var(--surface)' : undefined,
                  color: s.status === 'active' ? 'var(--accent)' : 'var(--text)',
                }}
              >
                <td className="p-1">
                  <span className={`inline-block w-2 h-2 rounded-full mr-1 ${s.status === 'active' ? 'bg-green-400' : s.status === 'failed' ? 'bg-red-400' : 'bg-gray-400'}`} />
                  {s.status}
                </td>
                <td className="p-1 font-mono">{s.caller_identity}</td>
                <td className="p-1">{s.session_type}</td>
                <td className="p-1 text-right">{s.tool_call_count}</td>
                <td className="p-1 text-right">{new Date(s.started_at).toLocaleTimeString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Call Detail */}
      <div className="w-1/2 overflow-auto">
        <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--muted)' }}>
          {selected ? 'Tool Calls' : 'Select a session'}
        </h3>
        {calls.map(c => (
          <div
            key={c.id}
            className="p-2 mb-1 rounded text-xs"
            style={{ background: 'var(--surface)', border: c.status === 'failed' ? '1px solid var(--danger)' : '1px solid var(--border)' }}
          >
            <div className="flex justify-between">
              <span className="font-mono font-semibold">{c.tool_name}</span>
              <span style={{ color: c.status === 'succeeded' ? 'var(--accent)' : c.status === 'failed' ? 'var(--danger)' : 'var(--muted)' }}>
                {c.status} {c.duration_ms ? `(${c.duration_ms}ms)` : ''}
              </span>
            </div>
            {c.result_preview && (
              <div className="mt-1 opacity-70 truncate">{c.result_preview}</div>
            )}
            {c.error_message && (
              <div className="mt-1" style={{ color: 'var(--danger)' }}>{c.error_message}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create Dashboard component**

Create `frontend/src/components/admin/Dashboard.tsx`:

```tsx
import { useState, useEffect } from 'react'
import { getDashboardMetrics, getToolStats, type DashboardMetrics } from '../../api/v3'

export default function Dashboard() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null)
  const [tools, setTools] = useState<{ tool_name: string; total_calls: number; succeeded: number; failed: number; avg_duration_ms: number }[]>([])

  useEffect(() => {
    const load = () => {
      getDashboardMetrics().then(setMetrics).catch(() => {})
      getToolStats().then(setTools).catch(() => {})
    }
    load()
    const interval = setInterval(load, 10000)
    return () => clearInterval(interval)
  }, [])

  if (!metrics) return <div className="text-xs" style={{ color: 'var(--muted)' }}>Loading...</div>

  const errorPct = metrics.error_rate_last_hour.total > 0
    ? ((metrics.error_rate_last_hour.errors / metrics.error_rate_last_hour.total) * 100).toFixed(1)
    : '0.0'

  return (
    <div>
      {/* Metric Cards */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        {[
          { label: 'Active Sessions', value: metrics.active_sessions, color: 'var(--accent)' },
          { label: 'Total Tool Calls', value: metrics.total_tool_calls, color: 'var(--text)' },
          { label: 'Error Rate (1h)', value: `${errorPct}%`, color: parseFloat(errorPct) > 10 ? 'var(--danger)' : 'var(--accent)' },
          { label: 'Avg Duration', value: `${Math.round(metrics.avg_duration_ms)}ms`, color: 'var(--text)' },
        ].map(card => (
          <div key={card.label} className="p-3 rounded" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
            <div className="text-xs" style={{ color: 'var(--muted)' }}>{card.label}</div>
            <div className="text-xl font-bold mt-1" style={{ color: card.color }}>{card.value}</div>
          </div>
        ))}
      </div>

      {/* Tool Stats Table */}
      <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--muted)' }}>Tool Usage (24h)</h3>
      <table className="w-full text-xs">
        <thead>
          <tr style={{ color: 'var(--muted)' }}>
            <th className="text-left p-1">Tool</th>
            <th className="text-right p-1">Calls</th>
            <th className="text-right p-1">Success</th>
            <th className="text-right p-1">Failed</th>
            <th className="text-right p-1">Avg Duration</th>
          </tr>
        </thead>
        <tbody>
          {tools.map(t => (
            <tr key={t.tool_name}>
              <td className="p-1 font-mono">{t.tool_name}</td>
              <td className="p-1 text-right">{t.total_calls}</td>
              <td className="p-1 text-right" style={{ color: 'var(--accent)' }}>{t.succeeded}</td>
              <td className="p-1 text-right" style={{ color: t.failed > 0 ? 'var(--danger)' : 'var(--muted)' }}>{t.failed}</td>
              <td className="p-1 text-right">{Math.round(t.avg_duration_ms || 0)}ms</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 3: Create LiveProcessesPage**

Create `frontend/src/pages/LiveProcessesPage.tsx`:

```tsx
import IconRail from '../components/layout/IconRail'
import SessionList from '../components/admin/SessionList'
import Dashboard from '../components/admin/Dashboard'
import { useState } from 'react'

export default function LiveProcessesPage() {
  const [tab, setTab] = useState<'sessions' | 'dashboard'>('sessions')

  return (
    <div className="flex h-screen" style={{ background: 'var(--bg)', color: 'var(--text)' }}>
      <div className="flex-1 overflow-hidden flex flex-col p-4">
        <div className="flex items-center gap-4 mb-4">
          <h1 className="text-lg font-bold">Live Processes</h1>
          <div className="flex gap-1">
            {(['sessions', 'dashboard'] as const).map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className="px-3 py-1 rounded text-xs"
                style={{
                  background: tab === t ? 'var(--accent)' : 'var(--surface)',
                  color: tab === t ? '#fff' : 'var(--text)',
                }}
              >
                {t === 'sessions' ? 'Sessions' : 'Dashboard'}
              </button>
            ))}
          </div>
        </div>
        <div className="flex-1 overflow-auto">
          {tab === 'sessions' ? <SessionList /> : <Dashboard />}
        </div>
      </div>
      <IconRail />
    </div>
  )
}
```

- [ ] **Step 4: Add route to App.tsx**

Add lazy import at the top of `frontend/src/App.tsx`:

```typescript
const LiveProcessesPage = lazy(() => import('./pages/LiveProcessesPage'))
```

Add route inside `<Routes>` (after the settings route):

```tsx
<Route path="/admin/processes" element={<AuthGuard><LiveProcessesPage /></AuthGuard>} />
```

- [ ] **Step 5: Add nav icon to IconRail**

Add a "Live Processes" icon to `frontend/src/components/layout/IconRail.tsx`. Find the existing navigation items array and add:

```typescript
{ path: '/admin/processes', icon: 'Activity', label: 'Live Processes' },
```

(Use whatever icon component the IconRail already uses — match the existing pattern.)

- [ ] **Step 6: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add frontend/src/pages/LiveProcessesPage.tsx frontend/src/components/admin/SessionList.tsx frontend/src/components/admin/Dashboard.tsx frontend/src/App.tsx frontend/src/components/layout/IconRail.tsx && git commit -m "feat(fe): add Live Processes page with session list and dashboard"
```

---

## Task 12: Frontend — Knowledge Graph Explorer Page

**Files:**
- Create: `frontend/src/pages/KnowledgeGraphPage.tsx`
- Create: `frontend/src/components/knowledge/EntityList.tsx`
- Create: `frontend/src/components/knowledge/EntityDetail.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create EntityList component**

Create `frontend/src/components/knowledge/EntityList.tsx`:

```tsx
import { useState, useEffect } from 'react'
import { searchEntities, getEntityTypes, type EntityOut } from '../../api/v3'

interface Props {
  onSelect: (ref: string) => void
  selectedRef: string | null
}

export default function EntityList({ onSelect, selectedRef }: Props) {
  const [query, setQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState<string>('')
  const [entities, setEntities] = useState<EntityOut[]>([])
  const [types, setTypes] = useState<{ name: string; display_name: string }[]>([])

  useEffect(() => {
    getEntityTypes().then(setTypes).catch(() => {})
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => {
      searchEntities(query, typeFilter || undefined, 100).then(setEntities).catch(() => {})
    }, 300)
    return () => clearTimeout(timer)
  }, [query, typeFilter])

  return (
    <div className="flex flex-col h-full">
      <div className="flex gap-2 mb-2">
        <input
          className="flex-1 px-2 py-1 rounded text-xs"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)' }}
          placeholder="Search entities..."
          value={query}
          onChange={e => setQuery(e.target.value)}
        />
        <select
          className="px-2 py-1 rounded text-xs"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)' }}
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
        >
          <option value="">All Types</option>
          {types.map(t => (
            <option key={t.name} value={t.name}>{t.display_name}</option>
          ))}
        </select>
      </div>
      <div className="flex-1 overflow-auto">
        {entities.map(e => (
          <div
            key={e.ref}
            onClick={() => onSelect(e.ref)}
            className="p-2 mb-1 rounded cursor-pointer hover:opacity-80 text-xs"
            style={{
              background: selectedRef === e.ref ? 'var(--accent)' : 'var(--surface)',
              color: selectedRef === e.ref ? '#fff' : 'var(--text)',
              border: '1px solid var(--border)',
            }}
          >
            <div className="font-semibold">{e.name}</div>
            <div className="flex gap-2 mt-1 opacity-70">
              <span className="px-1 rounded" style={{ background: 'var(--bg)' }}>{e.entity_type}</span>
              <span>conf: {e.confidence}%</span>
              <span>{e.observation_count} obs</span>
            </div>
          </div>
        ))}
        {entities.length === 0 && (
          <div className="text-xs p-4 text-center" style={{ color: 'var(--muted)' }}>
            {query ? 'No entities found' : 'Search to find entities'}
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create EntityDetail component**

Create `frontend/src/components/knowledge/EntityDetail.tsx`:

```tsx
import { useState, useEffect } from 'react'
import { getEntityDetail, getEntityObservations, type EntityOut, type EntityObservation } from '../../api/v3'

interface Props {
  entityRef: string
}

export default function EntityDetail({ entityRef }: Props) {
  const [entity, setEntity] = useState<EntityOut | null>(null)
  const [relationships, setRelationships] = useState<Record<string, unknown>[]>([])
  const [observations, setObservations] = useState<EntityObservation[]>([])
  const [tab, setTab] = useState<'overview' | 'timeline'>('overview')

  useEffect(() => {
    getEntityDetail(entityRef)
      .then(r => { setEntity(r.entity); setRelationships(r.relationships) })
      .catch(() => {})
    getEntityObservations(entityRef).then(setObservations).catch(() => {})
  }, [entityRef])

  if (!entity) return <div className="text-xs p-4" style={{ color: 'var(--muted)' }}>Loading...</div>

  return (
    <div className="h-full overflow-auto">
      {/* Header */}
      <div className="mb-4">
        <h2 className="text-lg font-bold">{entity.name}</h2>
        <div className="flex gap-2 text-xs mt-1" style={{ color: 'var(--muted)' }}>
          <span className="px-2 py-0.5 rounded" style={{ background: 'var(--surface)' }}>{entity.entity_type}</span>
          <span>Confidence: {entity.confidence}%</span>
          <span>{entity.observation_count} observations</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-3">
        {(['overview', 'timeline'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className="px-3 py-1 rounded text-xs"
            style={{ background: tab === t ? 'var(--accent)' : 'var(--surface)', color: tab === t ? '#fff' : 'var(--text)' }}
          >
            {t === 'overview' ? 'Overview' : 'Timeline'}
          </button>
        ))}
      </div>

      {tab === 'overview' ? (
        <>
          {/* Relationships */}
          <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--muted)' }}>Relationships ({relationships.length})</h3>
          {relationships.map((r, i) => (
            <div key={i} className="p-2 mb-1 rounded text-xs" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
              <span className="font-mono">{String(r.relationship_type)}</span>
              <span className="mx-2">{String(r.direction) === 'outgoing' ? '→' : '←'}</span>
              <span className="font-semibold">{String(r.other_name)}</span>
              <span className="ml-2 opacity-60">({String(r.other_type)})</span>
              {r.confidence && <span className="ml-2 opacity-60">conf: {String(r.confidence)}%</span>}
            </div>
          ))}
        </>
      ) : (
        <>
          {/* Observation Timeline */}
          <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--muted)' }}>Observations ({observations.length})</h3>
          {observations.map((o, i) => (
            <div key={i} className="p-2 mb-1 rounded text-xs flex justify-between" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
              <div>
                <span className="font-mono font-semibold">{o.attribute}</span>
                <span className="mx-1">=</span>
                <span>{o.value}</span>
              </div>
              <div className="flex gap-2 opacity-60">
                <span>{o.source_tool}</span>
                <span>conf: {o.confidence}%</span>
                <span>{new Date(o.observed_at).toLocaleDateString()}</span>
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Create KnowledgeGraphPage**

Create `frontend/src/pages/KnowledgeGraphPage.tsx`:

```tsx
import { useState } from 'react'
import IconRail from '../components/layout/IconRail'
import EntityList from '../components/knowledge/EntityList'
import EntityDetail from '../components/knowledge/EntityDetail'

export default function KnowledgeGraphPage() {
  const [selectedRef, setSelectedRef] = useState<string | null>(null)

  return (
    <div className="flex h-screen" style={{ background: 'var(--bg)', color: 'var(--text)' }}>
      <div className="flex-1 overflow-hidden flex flex-col p-4">
        <h1 className="text-lg font-bold mb-4">Knowledge Graph</h1>
        <div className="flex-1 flex gap-4 overflow-hidden">
          <div className="w-1/3">
            <EntityList onSelect={setSelectedRef} selectedRef={selectedRef} />
          </div>
          <div className="w-2/3">
            {selectedRef ? (
              <EntityDetail entityRef={selectedRef} />
            ) : (
              <div className="flex items-center justify-center h-full text-xs" style={{ color: 'var(--muted)' }}>
                Select an entity to view details
              </div>
            )}
          </div>
        </div>
      </div>
      <IconRail />
    </div>
  )
}
```

- [ ] **Step 4: Add route to App.tsx**

Add lazy import:

```typescript
const KnowledgeGraphPage = lazy(() => import('./pages/KnowledgeGraphPage'))
```

Add route:

```tsx
<Route path="/knowledge" element={<AuthGuard><KnowledgeGraphPage /></AuthGuard>} />
```

Add nav icon to IconRail:

```typescript
{ path: '/knowledge', icon: 'Network', label: 'Knowledge Graph' },
```

- [ ] **Step 5: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add frontend/src/pages/KnowledgeGraphPage.tsx frontend/src/components/knowledge/EntityList.tsx frontend/src/components/knowledge/EntityDetail.tsx frontend/src/App.tsx frontend/src/components/layout/IconRail.tsx && git commit -m "feat(fe): add Knowledge Graph explorer page with entity search and detail"
```

---

## Task 13: Docker Build + Integration Test

**Files:**
- None (verification only)

- [ ] **Step 1: Run all unit tests**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/knowledge/ tests/observability/ tests/pipeline/nodes/test_analyzer.py -v
```

Expected: All tests PASS

- [ ] **Step 2: Build Docker containers**

```bash
cd /Users/rinehardramos/Projects/info-broker && export PATH="/opt/homebrew/bin:$PATH" && docker compose build --no-cache info-broker-api
```

Expected: Build succeeds

- [ ] **Step 3: Start all services including Neo4j**

```bash
cd /Users/rinehardramos/Projects/info-broker && export PATH="/opt/homebrew/bin:$PATH" && docker compose up -d
```

Expected: All services start, including neo4j

- [ ] **Step 4: Verify schema migration**

```bash
cd /Users/rinehardramos/Projects/info-broker && export PATH="/opt/homebrew/bin:$PATH" && docker compose exec info-broker-api python -c "
from app.routers.v3.db import fetch_all
types = fetch_all('SELECT name FROM entity_types ORDER BY name')
print(f'Entity types: {len(types)}')
rels = fetch_all('SELECT name FROM relationship_types ORDER BY name')
print(f'Relationship types: {len(rels)}')
"
```

Expected: 25 entity types, 25 relationship types

- [ ] **Step 5: Verify API endpoints**

```bash
# Knowledge endpoints
curl -s http://localhost:8000/v3/knowledge/entity-types -H "Authorization: Bearer $(curl -s http://localhost:8000/v3/auth/login -d '{"username":"admin","password":"admin"}' -H 'Content-Type: application/json' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')" | python3 -m json.tool | head -20

# Admin endpoints
curl -s http://localhost:8000/v3/admin/dashboard -H "Authorization: Bearer $(curl -s http://localhost:8000/v3/auth/login -d '{"username":"admin","password":"admin"}' -H 'Content-Type: application/json' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')" | python3 -m json.tool
```

Expected: JSON responses with entity types and dashboard metrics

- [ ] **Step 6: Verify observability by making a tool call**

```bash
# Make a tool call via MCP endpoint
curl -s -X POST http://localhost:8000/v3/nodes/ddg_search/execute \
  -H "X-API-Key: changeme" \
  -H "X-Caller-Identity: test-caller" \
  -H "X-Session-Id: test-session-$(date +%s)" \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "max_results": 3}' | python3 -m json.tool | head -5

# Check it was logged
curl -s http://localhost:8000/v3/admin/sessions -H "Authorization: Bearer $(curl -s http://localhost:8000/v3/auth/login -d '{"username":"admin","password":"admin"}' -H 'Content-Type: application/json' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')" | python3 -m json.tool | head -20
```

Expected: Tool call logged in mcp_tool_calls, visible via admin API

- [ ] **Step 7: Commit any fixes**

If any fixes were needed during integration testing, commit them.

```bash
cd /Users/rinehardramos/Projects/info-broker && git add -A && git status
# Only commit if there are changes
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Section 1 (Ontology): Task 1 seeds all 25 entity types + 25 relationship types
- [x] Section 2 (Event Store): Tasks 1, 5, 7 implement PG tables, writer, materializer
- [x] Section 3 (Observability): Tasks 2, 3, 4 implement tracker, instrumentation, headers
- [x] Section 4 (API): Task 8 implements all knowledge + admin endpoints
- [x] Section 5 (Integration): Task 9 wires analyzer to KG writer
- [x] Section 6 (Phases): All 5 phases covered across 13 tasks
- [x] Section 7 (Verification): Task 13 verifies end-to-end

**Placeholder scan:** No TBDs, TODOs, or "implement later" found.

**Type consistency:**
- `EntityObservationIn` fields match PG schema columns
- `McpToolCallIn` fields match `mcp_tool_calls` table
- `tracker.log_call_start()` params match `McpToolCallIn`
- `KnowledgeGraphWriter.write_entities()` output matches `entity_observations` schema
- Frontend `EntityOut` matches backend `get_entity()` response
- Frontend `McpSession` matches backend `list_sessions()` response
