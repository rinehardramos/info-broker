# Knowledge Graph + MCP Observability Design

## Overview

Upgrade info-broker from ephemeral search results to a persistent, event-sourced knowledge graph with full-spectrum entity tracking across business intelligence, threat/risk, geopolitical, and OSINT domains. Simultaneously add complete observability for all MCP tool calls so any process using info-broker-mcp appears as a live process in the admin UI.

**Architecture:** Event-sourced from day one. Every entity observation is an immutable event in PostgreSQL (source of truth). Neo4j materializes the current graph state as a read projection. Qdrant provides semantic search over entities. All MCP tool calls are logged with session correlation and streamed via WebSocket.

**Tech Stack Additions:** Neo4j 5 Community (graph database), new PG tables (event store + tool call log)

---

## 1. Dynamic Ontology — Entity & Relationship Types

### Entity Types

The ontology is dynamic — new types can be added via the `entity_types` registry table without code changes. The following types are bootstrapped at setup.

#### Core Entities

| Type | Examples | Key Attributes |
|------|----------|---------------|
| `person` | Executives, contacts, operatives, analysts | name, aliases, roles, nationalities |
| `organization` | Companies, agencies, NGOs, APT groups | name, aliases, industry, jurisdiction, size |
| `location` | Cities, countries, facilities, coordinates | name, coords, type (city/country/facility), sensitivity |
| `document` | Reports, filings, leaks, advisories | title, url, classification, published_at |
| `technology` | Software, platforms, frameworks | name, vendor, version, category |
| `service` | IT outsourcing, SaaS, consulting | name, provider, category |
| `event` | Meetings, incidents, operations | name, date, type, participants |
| `asset` | Vehicles, facilities, equipment | identifier, type, owner, location |

#### Business Intelligence Entities

| Type | Examples | Key Attributes |
|------|----------|---------------|
| `financial_entity` | Bank accounts, funds, shell companies | identifier, type, jurisdiction |
| `transaction` | Wire transfers, funding rounds, M&A deals | amount, currency, date, parties |
| `contract` | Government contracts, vendor agreements | value, parties, start/end dates |
| `market_signal` | Revenue changes, layoffs, expansions | signal_type, magnitude, date |

#### Threat/Risk Intelligence Entities

| Type | Examples | Key Attributes |
|------|----------|---------------|
| `threat_actor` | APT groups, cybercrime syndicates | name, aliases, attribution_confidence, TTPs |
| `vulnerability` | CVEs, zero-days, misconfigurations | cve_id, severity, affected_products |
| `campaign` | Phishing ops, influence ops, cyber attacks | name, timeframe, targets, objectives |
| `indicator` | IPs, domains, hashes, emails (IOCs) | type, value, first_seen, last_seen |
| `malware` | Ransomware, RATs, exploits | family, variant, capabilities |

#### Geopolitical Intelligence Entities

| Type | Examples | Key Attributes |
|------|----------|---------------|
| `political_entity` | Governments, parties, alliances | name, type, jurisdiction |
| `policy` | Regulations, sanctions, trade agreements | name, issuer, effective_date, targets |
| `geopolitical_event` | Elections, coups, sanctions, treaties | type, date, actors, impact |
| `sanction` | OFAC, EU, UN sanctions | target, authority, date, type |

#### OSINT / Infrastructure Entities

| Type | Examples | Key Attributes |
|------|----------|---------------|
| `infrastructure` | Domains, IPs, ASNs, servers, C2 | identifier, type (domain/ip/asn), registrar |
| `social_account` | Twitter, LinkedIn, FB profiles | platform, handle, url, verified |
| `credential` | Leaked emails, breached accounts | type, source_breach, exposure_date |

#### Operational Intelligence Entities

| Type | Examples | Key Attributes |
|------|----------|---------------|
| `communication` | Intercepted comms, public statements | medium, date, participants, content_ref |

### Relationship Types

| Type | From → To | Domain |
|------|-----------|--------|
| `works_at` | person → organization | Core |
| `founded` | person → organization | Core |
| `subsidiary_of` | organization → organization | Business |
| `competes_with` | organization → organization | Business |
| `partners_with` | organization → organization | Business |
| `supplies_to` | organization → organization | Business |
| `client_of` | organization → organization | Business |
| `invested_in` | org/person → organization | Business |
| `acquired` | organization → organization | Business |
| `transacted_with` | org/person → org/person | Business |
| `funds` | financial_entity → org/campaign | Business/Threat |
| `located_in` | any → location | Core |
| `uses_technology` | organization → technology | OSINT |
| `provides_service` | organization → service | Business |
| `owns_domain` | organization → infrastructure | OSINT |
| `operates_infrastructure` | threat_actor → infrastructure | Threat |
| `attributed_to` | campaign → threat_actor | Threat |
| `exploits` | campaign → vulnerability | Threat |
| `targets` | campaign/threat_actor → org/person | Threat |
| `sanctioned_by` | org/person → political_entity | Geopolitical |
| `governed_by` | policy → political_entity | Geopolitical |
| `linked_to_breach` | credential → organization | OSINT |
| `controls` | person → social_account | OSINT |
| `mentioned_in` | any → document | Core |
| `participated_in` | person/org → event | Core |

---

## 2. Event-Sourced Knowledge Graph

### Architecture

```
Research Run (IS Brain / Analyzer / Manual Input)
  |
  +-> Entity Extractor (LLM-powered)
  |     Decomposes findings into entity + relationship observations
  |     Each observation = immutable event in PostgreSQL
  |
  +-> entity_observations (PG, INSERT only)
  +-> relationship_observations (PG, INSERT only)
  |
  +-> Graph Materializer (async background worker)
        Reads new observations since last checkpoint
        Resolves entity identity (exact -> alias -> embedding similarity)
        Upserts Neo4j nodes and relationships
        Updates materialization checkpoint
```

### PostgreSQL Schema (Event Store — Source of Truth)

```sql
-- Dynamic ontology registry
CREATE TABLE entity_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(64) UNIQUE NOT NULL,       -- e.g., "person", "organization"
    display_name VARCHAR(128) NOT NULL,
    icon VARCHAR(32),                        -- icon identifier for UI
    default_attributes JSONB DEFAULT '{}',   -- schema hint for this type
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE relationship_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(64) UNIQUE NOT NULL,        -- e.g., "works_at", "subsidiary_of"
    display_name VARCHAR(128) NOT NULL,
    from_types TEXT[] DEFAULT '{}',           -- allowed source entity types
    to_types TEXT[] DEFAULT '{}',             -- allowed target entity types
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Immutable entity observation log
CREATE TABLE entity_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_ref VARCHAR(512) NOT NULL,        -- canonical ref: "person::john-doe-ceo-acme"
    entity_type VARCHAR(64) NOT NULL,
    attribute VARCHAR(128) NOT NULL,          -- "name", "role", "industry", etc.
    value TEXT NOT NULL,
    confidence INT NOT NULL DEFAULT 50,      -- 0-100
    source_run_id UUID,                      -- FK to pipeline_runs or research_trails
    source_tool VARCHAR(128),                -- "ddg_search", "apollo_zoominfo", etc.
    source_url TEXT,                          -- provenance URL
    observed_at TIMESTAMPTZ NOT NULL,        -- when the fact was observed
    created_at TIMESTAMPTZ DEFAULT now()     -- when we stored it
);

CREATE INDEX idx_entity_obs_ref ON entity_observations (entity_ref);
CREATE INDEX idx_entity_obs_type ON entity_observations (entity_type);
CREATE INDEX idx_entity_obs_created ON entity_observations (created_at);

-- Immutable relationship observation log
CREATE TABLE relationship_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_entity_ref VARCHAR(512) NOT NULL,
    to_entity_ref VARCHAR(512) NOT NULL,
    relationship_type VARCHAR(64) NOT NULL,
    confidence INT NOT NULL DEFAULT 50,
    evidence TEXT,                            -- brief explanation
    source_run_id UUID,
    source_tool VARCHAR(128),
    observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_rel_obs_from ON relationship_observations (from_entity_ref);
CREATE INDEX idx_rel_obs_to ON relationship_observations (to_entity_ref);
CREATE INDEX idx_rel_obs_created ON relationship_observations (created_at);

-- Entity alias mapping (for resolution)
CREATE TABLE entity_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_ref VARCHAR(512) NOT NULL,     -- the resolved entity ref
    alias VARCHAR(512) NOT NULL,             -- variant name/ref
    alias_type VARCHAR(32) DEFAULT 'name',   -- "name", "abbreviation", "misspelling"
    created_by VARCHAR(64) DEFAULT 'system', -- "system", "materializer", "admin"
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (canonical_ref, alias)
);

CREATE INDEX idx_alias_lookup ON entity_aliases (alias);

-- Materialization checkpoint
CREATE TABLE graph_materializer_state (
    id INT PRIMARY KEY DEFAULT 1,
    last_entity_obs_at TIMESTAMPTZ,
    last_rel_obs_at TIMESTAMPTZ,
    last_run_at TIMESTAMPTZ,
    entities_processed INT DEFAULT 0,
    relationships_processed INT DEFAULT 0
);
```

### Neo4j Schema (Materialized Graph — Read Projection)

```cypher
// One label per entity type, all share common properties
// (:Person), (:Organization), (:Location), (:ThreatActor), etc.

// Common node properties:
// - ref: canonical entity_ref (unique identifier)
// - name: display name (highest-confidence "name" observation)
// - aliases: list of known aliases
// - confidence: overall confidence (max across observations)
// - first_seen: earliest observed_at
// - last_seen: latest observed_at
// - attributes: map of attribute -> value (latest highest-confidence)
// - observation_count: number of observations feeding this entity

// Relationships carry:
// - confidence: highest confidence from observations
// - evidence: explanation text
// - first_seen: earliest observed_at
// - last_seen: latest observed_at
// - observation_count: number of observations supporting this link

// Indexes
CREATE CONSTRAINT entity_ref_unique FOR (n:Entity) REQUIRE n.ref IS UNIQUE;
CREATE INDEX entity_name_idx FOR (n:Entity) ON (n.name);
```

### Entity Resolution Strategy

Resolution happens in the materializer when processing new observations:

1. **Exact ref match:** If `entity_ref` matches an existing Neo4j node's `ref`, update in place.
2. **Alias lookup:** Query `entity_aliases` table. If the observation's name matches a known alias, map to canonical ref.
3. **Embedding similarity:** Embed the entity name + type via Qdrant. Search existing entities of the same type. If cosine similarity >= 0.92, treat as same entity. Create alias mapping.
4. **New entity:** If no match found, create new Neo4j node.
5. **Conflict resolution:** When multiple observations provide different values for the same attribute, highest confidence wins. Ties broken by most recent `observed_at`.
6. **Manual override:** Admin can merge entities (creates `merge_event`), split entities, or correct attributes. Manual observations get confidence = 100.

### Temporal Queries

The event store enables point-in-time queries:

```sql
-- What did we know about an entity as of a specific date?
SELECT DISTINCT ON (attribute)
    attribute, value, confidence, source_tool, observed_at
FROM entity_observations
WHERE entity_ref = 'organization::acme-corp'
  AND observed_at <= '2026-03-01'
ORDER BY attribute, confidence DESC, observed_at DESC;

-- When did we first learn about a relationship?
SELECT MIN(observed_at) AS first_seen, relationship_type, evidence
FROM relationship_observations
WHERE from_entity_ref = 'person::john-doe'
  AND to_entity_ref = 'organization::acme-corp'
GROUP BY relationship_type, evidence;
```

---

## 3. MCP Observability — Live Process Tracking

### Problem

When external tools use info-broker-mcp (e.g., worker-mcp dispatches a task), those tool calls don't appear in the admin UI. The user has no visibility into what's happening.

### Solution

Log every MCP tool call at the execution gateway with session correlation, and stream events to the admin UI via WebSocket.

### PostgreSQL Schema

```sql
-- Session tracking (groups tool calls into logical units)
CREATE TABLE mcp_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    caller_identity VARCHAR(256) NOT NULL,   -- "is-brain", "worker-mcp:eos-report", "pipeline:abc123"
    user_id UUID,                            -- who triggered it (nullable for system calls)
    session_type VARCHAR(32) NOT NULL,       -- "is_research", "pipeline_run", "worker_task", "manual"
    context JSONB DEFAULT '{}',              -- {query, pipeline_id, task_id, etc.}
    status VARCHAR(20) DEFAULT 'active',     -- active -> completed/failed
    tool_call_count INT DEFAULT 0,
    started_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX idx_mcp_sessions_status ON mcp_sessions (status);
CREATE INDEX idx_mcp_sessions_started ON mcp_sessions (started_at DESC);

-- Tool call log (append-heavy)
CREATE TABLE mcp_tool_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES mcp_sessions(id),
    caller_identity VARCHAR(256),
    user_id UUID,
    tool_name VARCHAR(128) NOT NULL,         -- "run_ddg_search", "run_apollo_lookup"
    node_type VARCHAR(64),                   -- underlying pipeline node type
    call_id UUID NOT NULL,                   -- unique call identifier
    parent_call_id UUID,                     -- tree linkage for nested calls
    status VARCHAR(20) DEFAULT 'pending',    -- pending -> executing -> succeeded/failed
    input_params JSONB,                      -- tool input (secrets scrubbed)
    result_preview TEXT,                     -- first 500 chars of result
    result_count INT,
    error_message TEXT,
    duration_ms INT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_mcp_calls_session ON mcp_tool_calls (session_id);
CREATE INDEX idx_mcp_calls_status ON mcp_tool_calls (status);
CREATE INDEX idx_mcp_calls_created ON mcp_tool_calls (created_at DESC);
```

### Instrumentation

The logging happens at the MCP tool execution gateway (`POST /v3/nodes/{node_type}/execute`):

1. Extract caller identity from `X-Caller-Identity` header (new)
2. Extract session ID from `X-Session-Id` header (new)
3. Before execution: INSERT `mcp_tool_calls` with status='executing', push WS event `mcp.tool_call.start`
4. After execution: UPDATE status, duration, result_preview, push WS event `mcp.tool_call.complete`
5. On error: UPDATE status='failed', error_message, push WS event `mcp.tool_call.complete` with error

### Caller Identity Headers

The MCP client (`mcp_server/client.py`) must pass identity headers on every request:

```python
headers = {
    "X-API-Key": api_key,
    "X-Caller-Identity": caller_identity,  # e.g., "is-brain", "worker-mcp:task-name"
    "X-Session-Id": session_id,            # correlates calls into a session
}
```

For IS brain: caller_identity = "is-brain", session_id = run_id
For worker-mcp: caller_identity = f"worker-mcp:{specialization}", session_id = task_id
For pipeline runs: caller_identity = f"pipeline:{pipeline_id}", session_id = run_id

### WebSocket Events

```json
// Session started
{
    "type": "mcp.session.start",
    "session_id": "uuid",
    "caller": "worker-mcp:eos-report",
    "session_type": "worker_task",
    "context": {"task_description": "Generate end of shift report"}
}

// Tool call started
{
    "type": "mcp.tool_call.start",
    "session_id": "uuid",
    "call_id": "uuid",
    "caller": "worker-mcp:eos-report",
    "tool": "run_ddg_search",
    "params_preview": "query=Philippine IT outsourcing companies"
}

// Tool call completed
{
    "type": "mcp.tool_call.complete",
    "call_id": "uuid",
    "status": "succeeded",
    "duration_ms": 1234,
    "result_count": 8,
    "result_preview": "Top 10 IT outsourcing companies in the Philippines..."
}

// Session completed
{
    "type": "mcp.session.complete",
    "session_id": "uuid",
    "status": "completed",
    "tool_call_count": 15,
    "duration_ms": 45000
}
```

### Admin UI: Live Processes Panel

**Live Process List** — real-time table showing all active and recent sessions:

| Status | Caller | Type | Tools | Duration | Started |
|--------|--------|------|-------|----------|---------|
| `active` | is-brain | is_research | 12/? | 45s | 45s ago |
| `active` | worker-mcp:eos-report | worker_task | 3/? | 12s | 12s ago |
| `completed` | pipeline:abc123 | pipeline_run | 8 | 2m 15s | 5m ago |

**Session Drill-Down** — click a session to see:
- Call tree visualization (parent -> child relationships)
- Timeline of all calls (Gantt-style)
- Per-call details: input params, result preview, duration, errors
- Total metrics: call count, success rate, total duration

**Dashboard Panel** — aggregated metrics:
- Active sessions count (real-time)
- Tool calls per minute (rolling 5-min window)
- Error rate by tool (last hour)
- Average duration by tool (last hour)
- Top 10 tools by usage (last 24h)
- Session throughput (sessions/hour)

All metrics computed via SQL aggregation on `mcp_tool_calls` and `mcp_sessions` tables. No additional infrastructure.

---

## 4. API Endpoints

### Knowledge Graph Endpoints

```
GET  /v3/knowledge/entity-types          — list registered entity types
POST /v3/knowledge/entity-types          — register new entity type
GET  /v3/knowledge/relationship-types    — list registered relationship types
POST /v3/knowledge/relationship-types    — register new relationship type

GET  /v3/knowledge/entities              — search/list entities (paginated, filterable)
GET  /v3/knowledge/entities/:ref         — entity detail with observation timeline
GET  /v3/knowledge/entities/:ref/graph   — subgraph around entity (configurable hops, max 5)
GET  /v3/knowledge/entities/:ref/observations — raw observations for this entity

GET  /v3/knowledge/relationships         — search relationships (by type, entity, etc.)

POST /v3/knowledge/entities/merge        — manually merge two entities (admin)
POST /v3/knowledge/entities/:ref/split   — split a wrongly merged entity (admin)
POST /v3/knowledge/observations          — manually add an observation (admin)

GET  /v3/knowledge/timeline              — temporal view of all observations (date range filter)
POST /v3/knowledge/query                 — Cypher query proxy (admin only, read-only)

GET  /v3/knowledge/stats                 — entity count by type, relationship count, observation rate
```

### Observability Endpoints

```
GET  /v3/admin/sessions                  — list active + recent MCP sessions (paginated)
GET  /v3/admin/sessions/:id              — session detail with call tree
GET  /v3/admin/sessions/:id/calls        — paginated call list for a session
GET  /v3/admin/dashboard                 — aggregated metrics (active sessions, rates, errors)
GET  /v3/admin/tools/stats               — per-tool usage statistics
```

---

## 5. Integration Points

### Entity Extraction from Research Runs

When the IS brain or analyzer completes a run:

1. The AnalyzerNode already extracts entities and relationships
2. A new `KnowledgeGraphWriter` takes analyzer output and writes observations:
   - Each entity -> `entity_observations` rows (one per attribute)
   - Each relationship -> `relationship_observations` row
3. The Graph Materializer processes new observations and upserts Neo4j

For IS brain runs that skip the analyzer, a lightweight entity extractor runs on raw findings to create basic observations (entity name, type, source URL).

### Observability Instrumentation

The node execution endpoint (`POST /v3/nodes/{node_type}/execute`) gets middleware that:

1. Reads `X-Caller-Identity` and `X-Session-Id` headers
2. Creates or finds the MCP session
3. Logs the tool call (before + after execution)
4. Pushes WebSocket events for real-time UI

The MCP client in `mcp_server/client.py` must pass these headers. IS brain and worker-mcp both set their identity when making tool calls.

### Docker Compose Changes

```yaml
neo4j:
  image: neo4j:5-community
  ports:
    - "7474:7474"   # Browser UI
    - "7687:7687"   # Bolt protocol
  environment:
    NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-changeme}
    NEO4J_PLUGINS: '["apoc"]'   # Graph algorithms
  volumes:
    - neo4j_data:/data
  healthcheck:
    test: ["CMD", "neo4j", "status"]
    interval: 10s
    timeout: 5s
    retries: 5
```

---

## 6. Implementation Phases

| Phase | Scope | Can Parallelize? |
|-------|-------|-----------------|
| **P1: Event Store + Schema** | PG tables (entity_types, entity_observations, relationship_observations, entity_aliases, graph_materializer_state), entity type seeding, observation write API | Start first |
| **P2: Neo4j + Materializer** | Neo4j container, Python driver integration, Graph Materializer background worker, entity resolution logic, Cypher query proxy | After P1 |
| **P3: MCP Observability** | PG tables (mcp_sessions, mcp_tool_calls), execution gateway middleware, WS events, MCP client header passing, Live Processes admin UI | Parallel with P1/P2 |
| **P4: Knowledge Graph UI** | Entity search/list page, entity detail with timeline, graph visualization (subgraph explorer), dashboard metrics | After P1+P2 |
| **P5: Entity Extraction Pipeline** | KnowledgeGraphWriter (bridges analyzer output to observations), lightweight extractor for raw findings, materializer integration | After P1+P2 |

---

## 7. Verification Criteria

1. **Event store works:** Insert entity observations, query by ref, query by date range
2. **Neo4j materializes:** Observations flow through materializer and appear in Neo4j within 5 seconds
3. **Entity resolution:** Same person from two different sources resolves to one Neo4j node
4. **Temporal queries:** Can query "what did we know about X as of date Y"
5. **MCP observability:** Any tool call (from IS brain, worker-mcp, or direct API) appears in Live Processes within 1 second
6. **Session correlation:** Related tool calls group into sessions with drill-down
7. **Dashboard metrics:** Active sessions, tool call rate, error rate, avg duration all display correctly
8. **Knowledge graph UI:** Search entities, view detail + timeline, visualize subgraph with N hops
9. **End-to-end:** Run IS brain query -> findings extracted to observations -> materialized in Neo4j -> visible in graph UI -> tool calls visible in Live Processes
