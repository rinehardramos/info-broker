from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

_MIGRATION = """
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

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
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID REFERENCES ui_users(id) ON DELETE CASCADE,
    name                  VARCHAR(128) NOT NULL,
    type                  VARCHAR(32) NOT NULL,
    target                TEXT NOT NULL,
    poll_interval_minutes INT DEFAULT 60,
    last_polled_at        TIMESTAMPTZ,
    last_item_count       INT DEFAULT 0,
    is_active             BOOLEAN DEFAULT true,
    created_at            TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core_settings (
    key        VARCHAR(128) PRIMARY KEY,
    value      TEXT NOT NULL,
    is_secret  BOOLEAN DEFAULT false,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS v3_jobs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID REFERENCES ui_users(id) ON DELETE CASCADE,
    query        TEXT NOT NULL,
    status       VARCHAR(20) DEFAULT 'pending',
    created_at   TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);

ALTER TABLE v3_jobs ADD COLUMN IF NOT EXISTS result_count INT DEFAULT 0;

CREATE TABLE IF NOT EXISTS v3_job_results (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id       UUID REFERENCES v3_jobs(id) ON DELETE CASCADE,
    source       VARCHAR(32) DEFAULT 'ddg',
    title        TEXT NOT NULL,
    url          TEXT,
    snippet      TEXT,
    created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_v3_job_results_job_id ON v3_job_results(job_id);

CREATE TABLE IF NOT EXISTS v3_result_grades (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    result_id  UUID REFERENCES v3_job_results(id) ON DELETE CASCADE,
    user_id    UUID REFERENCES ui_users(id) ON DELETE CASCADE,
    grade      VARCHAR(16) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (result_id, user_id)
);

CREATE TABLE IF NOT EXISTS apify_run_configs (
    user_id      UUID PRIMARY KEY REFERENCES ui_users(id) ON DELETE CASCADE,
    job_titles   JSONB DEFAULT '[]',
    locations    JSONB DEFAULT '[]',
    max_items    INT DEFAULT 300,
    scraper_mode VARCHAR(64) DEFAULT 'Full + email search',
    updated_at   TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE apify_run_configs
    ADD COLUMN IF NOT EXISTS auto_query_segmentation             BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS auto_query_segmentation_levels      JSONB   DEFAULT '["country","industry","seniority_level"]',
    ADD COLUMN IF NOT EXISTS auto_query_segmentation_countries   JSONB   DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS recently_changed_jobs               BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS recently_posted_on_linkedin         BOOLEAN DEFAULT false;

CREATE TABLE IF NOT EXISTS apify_runs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID REFERENCES ui_users(id) ON DELETE CASCADE,
    apify_run_id TEXT,
    status       VARCHAR(20) DEFAULT 'queued',
    item_count   INT DEFAULT 0,
    started_at   TIMESTAMPTZ DEFAULT now(),
    finished_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS linkedin_profile_grades (
    profile_id  VARCHAR(128) NOT NULL,
    user_id     UUID NOT NULL REFERENCES ui_users(id) ON DELETE CASCADE,
    grade       VARCHAR(16) NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (profile_id, user_id)
);

CREATE TABLE IF NOT EXISTS pipelines (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES ui_users(id) ON DELETE CASCADE,
    name        VARCHAR(255) NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pipeline_nodes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
    node_type   VARCHAR(64) NOT NULL,
    label       VARCHAR(255) NOT NULL,
    config      JSONB NOT NULL DEFAULT '{}',
    position_x  INT NOT NULL DEFAULT 0,
    position_y  INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pipeline_edges (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id    UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
    source_node_id UUID NOT NULL REFERENCES pipeline_nodes(id) ON DELETE CASCADE,
    target_node_id UUID NOT NULL REFERENCES pipeline_nodes(id) ON DELETE CASCADE,
    edge_type      VARCHAR(16) NOT NULL DEFAULT 'results'
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id          UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
    user_id              UUID NOT NULL REFERENCES ui_users(id) ON DELETE CASCADE,
    temporal_workflow_id TEXT,
    status               VARCHAR(20) NOT NULL DEFAULT 'queued',
    trigger_type         VARCHAR(16) NOT NULL DEFAULT 'manual',
    error_message        TEXT,
    started_at           TIMESTAMPTZ DEFAULT now(),
    finished_at          TIMESTAMPTZ
);
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS query TEXT;
ALTER TABLE research_trails ADD COLUMN IF NOT EXISTS analysis JSONB;
ALTER TABLE research_trails ADD COLUMN IF NOT EXISTS plan JSONB;
ALTER TABLE research_trails ADD COLUMN IF NOT EXISTS clarification JSONB DEFAULT '[]';
ALTER TABLE research_trails ADD COLUMN IF NOT EXISTS verification_status VARCHAR(32);

CREATE TABLE IF NOT EXISTS pipeline_step_runs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id        UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    node_id       UUID NOT NULL REFERENCES pipeline_nodes(id) ON DELETE CASCADE,
    status        VARCHAR(20) NOT NULL DEFAULT 'pending',
    item_count    INT NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ
);

ALTER TABLE pipelines ALTER COLUMN user_id DROP NOT NULL;

ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS is_system BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE pipelines DROP CONSTRAINT IF EXISTS ck_pipeline_owner;

ALTER TABLE pipelines ADD CONSTRAINT ck_pipeline_owner CHECK ((user_id IS NOT NULL) OR (is_system = true));

ALTER TABLE ui_preferences ADD COLUMN IF NOT EXISTS agent_pipeline_id UUID REFERENCES pipelines(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS plugin_requests (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID REFERENCES ui_users(id) ON DELETE CASCADE,
    spec          JSONB NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at    TIMESTAMPTZ DEFAULT now(),
    reviewed_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS research_trails (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES ui_users(id) ON DELETE CASCADE,
    run_id        UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    node_id       UUID REFERENCES pipeline_nodes(id) ON DELETE SET NULL,
    query         TEXT NOT NULL,
    entity_type   VARCHAR(64),
    trail         JSONB NOT NULL DEFAULT '[]',
    findings      JSONB NOT NULL DEFAULT '[]',
    tool_calls    INT NOT NULL DEFAULT 0,
    suggested_pipeline JSONB,
    created_at    TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE research_trails ADD COLUMN IF NOT EXISTS scorecard JSONB;

CREATE TABLE IF NOT EXISTS finding_feedback (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID REFERENCES ui_users(id),
    run_id        UUID NOT NULL,
    finding_index INTEGER NOT NULL,
    finding_title TEXT,
    user_score    INTEGER CHECK (user_score BETWEEN -1 AND 1),
    reason        TEXT,
    created_at    TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, run_id, finding_index)
);

CREATE TABLE IF NOT EXISTS entity_types (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name              VARCHAR(64) UNIQUE NOT NULL,
    display_name      VARCHAR(128) NOT NULL,
    icon              VARCHAR(32),
    default_attributes JSONB DEFAULT '{}',
    created_at        TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS relationship_types (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(64) UNIQUE NOT NULL,
    display_name VARCHAR(128) NOT NULL,
    from_types   TEXT[] DEFAULT '{}',
    to_types     TEXT[] DEFAULT '{}',
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS entity_observations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_ref   VARCHAR(512) NOT NULL,
    entity_type  VARCHAR(64) NOT NULL,
    attribute    VARCHAR(128) NOT NULL,
    value        TEXT NOT NULL,
    confidence   INT NOT NULL DEFAULT 50,
    source_run_id UUID,
    source_tool  VARCHAR(128),
    source_url   TEXT,
    observed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_entity_observations_entity_ref ON entity_observations(entity_ref);
CREATE INDEX IF NOT EXISTS idx_entity_observations_entity_type ON entity_observations(entity_type);
CREATE INDEX IF NOT EXISTS idx_entity_observations_created_at ON entity_observations(created_at);

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
CREATE INDEX IF NOT EXISTS idx_relationship_obs_from_entity ON relationship_observations(from_entity_ref);
CREATE INDEX IF NOT EXISTS idx_relationship_obs_to_entity ON relationship_observations(to_entity_ref);
CREATE INDEX IF NOT EXISTS idx_relationship_obs_created_at ON relationship_observations(created_at);

ALTER TABLE entity_observations ADD COLUMN IF NOT EXISTS tier VARCHAR(8) DEFAULT 'hot';
ALTER TABLE entity_observations ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_entity_obs_tier ON entity_observations(tier);
ALTER TABLE relationship_observations ADD COLUMN IF NOT EXISTS tier VARCHAR(8) DEFAULT 'hot';
ALTER TABLE relationship_observations ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS entity_aliases (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_ref VARCHAR(512) NOT NULL,
    alias         VARCHAR(512) NOT NULL,
    alias_type    VARCHAR(32) DEFAULT 'name',
    created_by    VARCHAR(64) DEFAULT 'system',
    created_at    TIMESTAMPTZ DEFAULT now(),
    UNIQUE(canonical_ref, alias)
);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_alias ON entity_aliases(alias);

CREATE TABLE IF NOT EXISTS graph_materializer_state (
    id                      INT PRIMARY KEY DEFAULT 1,
    last_entity_obs_at      TIMESTAMPTZ,
    last_rel_obs_at         TIMESTAMPTZ,
    last_run_at             TIMESTAMPTZ,
    entities_processed      INT DEFAULT 0,
    relationships_processed INT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS kg_contradictions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_ref        VARCHAR(512) NOT NULL,
    attribute         VARCHAR(128) NOT NULL,
    value_a           TEXT NOT NULL,
    value_b           TEXT NOT NULL,
    confidence_a      INT DEFAULT 50,
    confidence_b      INT DEFAULT 50,
    observed_at_a     TIMESTAMPTZ,
    observed_at_b     TIMESTAMPTZ,
    source_run_a      UUID,
    source_run_b      UUID,
    observation_id_a  UUID,
    observation_id_b  UUID,
    winner            TEXT,
    status            VARCHAR(32) NOT NULL DEFAULT 'auto_resolved',
    resolved_by       VARCHAR(64) DEFAULT 'system',
    resolved_at       TIMESTAMPTZ DEFAULT now(),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_contradictions_entity ON kg_contradictions(entity_ref);
CREATE INDEX IF NOT EXISTS idx_contradictions_status ON kg_contradictions(status);
CREATE INDEX IF NOT EXISTS idx_contradictions_created ON kg_contradictions(created_at DESC);

CREATE TABLE IF NOT EXISTS kg_stale_flags (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_ref     VARCHAR(512) NOT NULL,
    attribute      VARCHAR(128) NOT NULL,
    current_value  TEXT,
    observation_id UUID,
    observed_at    TIMESTAMPTZ,
    ttl_days       INT NOT NULL,
    status         VARCHAR(32) NOT NULL DEFAULT 'stale',
    flagged_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    dismissed_by   VARCHAR(64),
    dismissed_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_stale_entity ON kg_stale_flags(entity_ref);
CREATE INDEX IF NOT EXISTS idx_stale_status ON kg_stale_flags(status);

CREATE TABLE IF NOT EXISTS kg_curation_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_ref VARCHAR(512),
    suggestion_type VARCHAR(32),
    suggestion TEXT NOT NULL,
    priority VARCHAR(16) DEFAULT 'medium',
    status VARCHAR(32) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_curation_suggestions_status ON kg_curation_suggestions(status);

CREATE TABLE IF NOT EXISTS research_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES ui_users(id) ON DELETE CASCADE,
    run_id          UUID,
    filename        TEXT NOT NULL,
    file_type       VARCHAR(16) NOT NULL,
    file_size_bytes INT,
    token_count     INT,
    findings_count  INT DEFAULT 0,
    s3_key          TEXT,
    manifest        JSONB,
    status          VARCHAR(32) NOT NULL DEFAULT 'processing',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_research_sources_user ON research_sources(user_id);
CREATE INDEX IF NOT EXISTS idx_research_sources_status ON research_sources(status);

CREATE TABLE IF NOT EXISTS mcp_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    caller_identity VARCHAR(256) NOT NULL,
    user_id         UUID,
    session_type    VARCHAR(32) NOT NULL,
    context         JSONB DEFAULT '{}',
    status          VARCHAR(20) DEFAULT 'active',
    tool_call_count INT DEFAULT 0,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_mcp_sessions_status ON mcp_sessions(status);
CREATE INDEX IF NOT EXISTS idx_mcp_sessions_started_at ON mcp_sessions(started_at DESC);

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
CREATE INDEX IF NOT EXISTS idx_mcp_tool_calls_session_id ON mcp_tool_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_mcp_tool_calls_status ON mcp_tool_calls(status);
CREATE INDEX IF NOT EXISTS idx_mcp_tool_calls_created_at ON mcp_tool_calls(created_at DESC);

CREATE TABLE IF NOT EXISTS research_skills (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id            UUID REFERENCES pipeline_runs(id),
    query             TEXT NOT NULL,
    entity_type       VARCHAR(64),
    keywords          TEXT[] DEFAULT '{}',
    tool_sequence     TEXT[] NOT NULL DEFAULT '{}',
    pipeline          JSONB,
    branch_pattern    JSONB DEFAULT '{}',
    findings_count    INT DEFAULT 0,
    quality_score     FLOAT DEFAULT 0.0,
    error_rate        FLOAT DEFAULT 0.0,
    entities_found    INT DEFAULT 0,
    tool_calls        INT DEFAULT 0,
    duration_seconds  INT DEFAULT 0,
    estimated_cost_usd FLOAT DEFAULT 0.0,
    efficiency        FLOAT DEFAULT 0.0,
    times_suggested   INT DEFAULT 0,
    times_adopted     INT DEFAULT 0,
    last_suggested_at TIMESTAMPTZ,
    disabled          BOOLEAN DEFAULT false,
    created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_skills_quality ON research_skills (quality_score DESC);
CREATE INDEX IF NOT EXISTS idx_skills_entity ON research_skills (entity_type);

CREATE TABLE IF NOT EXISTS investigation_strategy_overlays (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     VARCHAR(50) NOT NULL,
    selector_type   VARCHAR(50) NOT NULL,
    pivot_pattern   VARCHAR(200) NOT NULL,
    overlay_type    VARCHAR(20) NOT NULL,
    content         TEXT,
    technique_ref   VARCHAR(100),
    yield_rate      FLOAT DEFAULT 0.0,
    intel_value     FLOAT DEFAULT 0.5,
    category        VARCHAR(20) DEFAULT 'situational',
    confidence      FLOAT DEFAULT 0.0,
    run_count       INT DEFAULT 0,
    pinned          BOOLEAN DEFAULT FALSE,
    last_validated  TIMESTAMPTZ DEFAULT now(),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_overlays_entity_type ON investigation_strategy_overlays (entity_type, overlay_type);
CREATE INDEX IF NOT EXISTS idx_overlays_selector ON investigation_strategy_overlays (entity_type, selector_type);

CREATE TABLE IF NOT EXISTS agent_sessions (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL,
    genesis_query        TEXT NOT NULL,
    status               VARCHAR DEFAULT 'active',
    created_at           TIMESTAMPTZ DEFAULT now(),
    archived_at          TIMESTAMPTZ,
    run_count            INT DEFAULT 0,
    turn_count           INT DEFAULT 0,
    conversation_thread  JSONB DEFAULT '[]',
    accumulated_summary  TEXT DEFAULT '',
    key_findings         JSONB DEFAULT '[]',
    entity_type          VARCHAR DEFAULT 'unknown'
);
CREATE INDEX IF NOT EXISTS agent_sessions_user_status_idx
    ON agent_sessions (user_id, status, created_at DESC);

ALTER TABLE pipeline_runs
    ADD COLUMN IF NOT EXISTS session_id UUID REFERENCES agent_sessions(id);

-- Budget Phase 1: wallet + ledger tables
CREATE TABLE IF NOT EXISTS user_budget_wallets (
    user_id              UUID PRIMARY KEY REFERENCES ui_users(id) ON DELETE CASCADE,
    org_id               UUID,
    balance_units        NUMERIC(18, 4) NOT NULL DEFAULT 10000.0,
    reserved_units       NUMERIC(18, 4) NOT NULL DEFAULT 0.0,
    spent_units_lifetime NUMERIC(18, 4) NOT NULL DEFAULT 0.0,
    plan_name            VARCHAR(64) DEFAULT 'free',
    updated_at           TIMESTAMPTZ DEFAULT now(),
    created_at           TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS budget_ledger_entries (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES ui_users(id) ON DELETE CASCADE,
    run_id       UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    kind         VARCHAR(32) NOT NULL,  -- reserve | debit | credit | release
    units        NUMERIC(18, 4) NOT NULL,
    note         TEXT,
    created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS budget_ledger_user_idx ON budget_ledger_entries (user_id, created_at DESC);

-- Budget Phase 2: run-level budget tracking
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS run_budget       JSONB;
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS budget_plan      JSONB;
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS budget_status    VARCHAR(32);
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS budget_exhausted_at TIMESTAMPTZ;
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS budget_stop_reason  TEXT;

-- RBAC: admin flag + org role on ui_users
ALTER TABLE ui_users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT false;
UPDATE ui_users SET is_admin = true WHERE username = 'admin';

-- Org membership role: admin | analyst | viewer
ALTER TABLE ui_users ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'analyst';
UPDATE ui_users SET role = 'admin' WHERE is_admin = true OR username = 'admin';

-- SSO: Google/GitHub OAuth identity columns. SSO-only users have a NULL
-- password_hash so the password_hash NOT NULL constraint is relaxed.
ALTER TABLE ui_users ALTER COLUMN password_hash DROP NOT NULL;
ALTER TABLE ui_users ADD COLUMN IF NOT EXISTS oauth_provider VARCHAR(32);
ALTER TABLE ui_users ADD COLUMN IF NOT EXISTS oauth_sub      VARCHAR(255);
ALTER TABLE ui_users ADD COLUMN IF NOT EXISTS avatar_url     TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS ix_ui_users_oauth_identity
    ON ui_users(oauth_provider, oauth_sub) WHERE oauth_sub IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ix_ui_users_email_unique
    ON ui_users(LOWER(email)) WHERE email IS NOT NULL;

-- Email verification (Resend-backed):
ALTER TABLE ui_users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    user_id    UUID NOT NULL REFERENCES ui_users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, token_hash)
);
CREATE INDEX IF NOT EXISTS ix_evt_expires ON email_verification_tokens(expires_at);

-- User personalization fields:
ALTER TABLE ui_users ADD COLUMN IF NOT EXISTS display_name TEXT;
ALTER TABLE ui_users ADD COLUMN IF NOT EXISTS timezone TEXT;
ALTER TABLE ui_users ADD COLUMN IF NOT EXISTS locale TEXT;

-- Entity profile cache (physical-evidence enrichment per candidate name + run context):
CREATE TABLE IF NOT EXISTS entity_profiles (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL,
    context_hash TEXT NOT NULL,
    entity_type  VARCHAR(16),
    payload      JSONB NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (name, context_hash)
);
CREATE INDEX IF NOT EXISTS ix_entity_profiles_name ON entity_profiles(name);

-- Session-scoped file uploads: research_sources now optionally tracks the
-- agent_session it was uploaded into. NULL session_id = library item
-- (re-attachable to any new session via /v3/sources/attach).
ALTER TABLE research_sources ADD COLUMN IF NOT EXISTS session_id UUID;
CREATE INDEX IF NOT EXISTS ix_research_sources_session
    ON research_sources(session_id) WHERE session_id IS NOT NULL;


-- Session multi-turn hypothesis memory
ALTER TABLE agent_sessions ADD COLUMN IF NOT EXISTS investigated_hypotheses JSONB DEFAULT '[]'::jsonb;

-- Signed callback delivery support
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS callback_url TEXT;

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id       UUID        REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    attempt      INT         NOT NULL,
    url          TEXT        NOT NULL,
    status_code  INT,
    error        TEXT,
    delivered_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_run ON webhook_deliveries(run_id, attempt);
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


_SEED = """
INSERT INTO ui_users (username, password_hash)
VALUES (
    'admin',
    '$2b$12$3cjgCjbJ/MLj.H7vGH9xHOKDUtgo492x98IdWILFNnadN4NbLgmym'
)
ON CONFLICT (username) DO NOTHING;

INSERT INTO pipelines (id, user_id, name, description, is_system)
VALUES (
    '00000000-0000-4000-8000-000000000001',
    NULL,
    'Agent Default',
    'Default pipeline for Agent chat: agent_input → multi_search → manual_scoring',
    true
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO pipeline_nodes (id, pipeline_id, node_type, label, config, position_x, position_y)
VALUES
    ('00000000-0000-4000-8000-000000000011', '00000000-0000-4000-8000-000000000001', 'agent_input',    'Agent CLI',      '{}', 0, 0),
    ('00000000-0000-4000-8000-000000000012', '00000000-0000-4000-8000-000000000001', 'multi_search',   'Multi-Engine Search', '{"engines":["ddg","serper","brave"]}', 0, 1),
    ('00000000-0000-4000-8000-000000000013', '00000000-0000-4000-8000-000000000001', 'manual_scoring', 'Manual Scoring', '{}', 0, 2)
ON CONFLICT (id) DO NOTHING;

INSERT INTO pipeline_edges (id, pipeline_id, source_node_id, target_node_id, edge_type)
VALUES
    ('00000000-0000-4000-8000-000000000021', '00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000011', '00000000-0000-4000-8000-000000000012', 'results'),
    ('00000000-0000-4000-8000-000000000022', '00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000012', '00000000-0000-4000-8000-000000000013', 'results')
ON CONFLICT (id) DO NOTHING;

INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('person', 'Person', 'user', '{"full_name": "", "date_of_birth": "", "nationality": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('organization', 'Organization', 'building-2', '{"legal_name": "", "industry": "", "founded_year": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('location', 'Location', 'map-pin', '{"address": "", "country": "", "coordinates": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('document', 'Document', 'file-text', '{"title": "", "author": "", "published_at": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('technology', 'Technology', 'cpu', '{"vendor": "", "version": "", "category": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('service', 'Service', 'server', '{"provider": "", "endpoint": "", "protocol": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('event', 'Event', 'calendar', '{"start_date": "", "end_date": "", "location": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('asset', 'Asset', 'package', '{"asset_type": "", "value": "", "owner": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('financial_entity', 'Financial Entity', 'landmark', '{"institution_type": "", "country": "", "regulatory_id": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('transaction', 'Transaction', 'arrow-left-right', '{"amount": "", "currency": "", "timestamp": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('contract', 'Contract', 'scroll-text', '{"parties": "", "effective_date": "", "value": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('market_signal', 'Market Signal', 'trending-up', '{"signal_type": "", "asset": "", "timestamp": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('threat_actor', 'Threat Actor', 'skull', '{"aliases": "", "motivation": "", "origin_country": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('vulnerability', 'Vulnerability', 'shield-alert', '{"cve_id": "", "cvss_score": "", "affected_product": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('campaign', 'Campaign', 'crosshair', '{"campaign_name": "", "start_date": "", "objectives": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('indicator', 'Indicator', 'radar', '{"indicator_type": "", "value": "", "tlp": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('malware', 'Malware', 'bug', '{"malware_family": "", "capabilities": "", "first_seen": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('political_entity', 'Political Entity', 'flag', '{"entity_type": "", "country": "", "affiliation": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('policy', 'Policy', 'file-check', '{"jurisdiction": "", "effective_date": "", "status": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('geopolitical_event', 'Geopolitical Event', 'globe', '{"region": "", "event_type": "", "date": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('sanction', 'Sanction', 'ban', '{"issuing_body": "", "target": "", "effective_date": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('infrastructure', 'Infrastructure', 'network', '{"infra_type": "", "provider": "", "region": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('social_account', 'Social Account', 'at-sign', '{"platform": "", "handle": "", "follower_count": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('credential', 'Credential', 'key', '{"credential_type": "", "scope": "", "expiry": ""}') ON CONFLICT (name) DO NOTHING;
INSERT INTO entity_types (name, display_name, icon, default_attributes) VALUES ('communication', 'Communication', 'message-square', '{"channel": "", "timestamp": "", "participants": ""}') ON CONFLICT (name) DO NOTHING;

INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('works_at', 'Works At', ARRAY['person'], ARRAY['organization']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('founded', 'Founded', ARRAY['person'], ARRAY['organization']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('subsidiary_of', 'Subsidiary Of', ARRAY['organization'], ARRAY['organization']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('competes_with', 'Competes With', ARRAY['organization'], ARRAY['organization']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('partners_with', 'Partners With', ARRAY['organization', 'person'], ARRAY['organization', 'person']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('supplies_to', 'Supplies To', ARRAY['organization'], ARRAY['organization']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('client_of', 'Client Of', ARRAY['organization', 'person'], ARRAY['organization']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('invested_in', 'Invested In', ARRAY['organization', 'person'], ARRAY['organization', 'asset']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('acquired', 'Acquired', ARRAY['organization'], ARRAY['organization', 'asset']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('transacted_with', 'Transacted With', ARRAY['organization', 'person'], ARRAY['organization', 'person']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('funds', 'Funds', ARRAY['organization', 'person'], ARRAY['organization', 'campaign']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('located_in', 'Located In', ARRAY['organization', 'person', 'infrastructure'], ARRAY['location']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('uses_technology', 'Uses Technology', ARRAY['organization', 'person', 'threat_actor'], ARRAY['technology']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('provides_service', 'Provides Service', ARRAY['organization'], ARRAY['service']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('owns_domain', 'Owns Domain', ARRAY['organization', 'person'], ARRAY['infrastructure']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('operates_infrastructure', 'Operates Infrastructure', ARRAY['organization', 'threat_actor'], ARRAY['infrastructure']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('attributed_to', 'Attributed To', ARRAY['campaign', 'malware', 'indicator'], ARRAY['threat_actor']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('exploits', 'Exploits', ARRAY['threat_actor', 'malware', 'campaign'], ARRAY['vulnerability']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('targets', 'Targets', ARRAY['threat_actor', 'campaign'], ARRAY['organization', 'person', 'infrastructure']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('sanctioned_by', 'Sanctioned By', ARRAY['organization', 'person'], ARRAY['political_entity']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('governed_by', 'Governed By', ARRAY['organization', 'infrastructure'], ARRAY['policy', 'political_entity']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('linked_to_breach', 'Linked To Breach', ARRAY['organization', 'person', 'credential'], ARRAY['event', 'campaign']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('controls', 'Controls', ARRAY['organization', 'person', 'threat_actor'], ARRAY['organization', 'infrastructure', 'asset']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('mentioned_in', 'Mentioned In', ARRAY['person', 'organization', 'event'], ARRAY['document', 'communication']) ON CONFLICT (name) DO NOTHING;
INSERT INTO relationship_types (name, display_name, from_types, to_types) VALUES ('participated_in', 'Participated In', ARRAY['person', 'organization'], ARRAY['event', 'campaign', 'geopolitical_event']) ON CONFLICT (name) DO NOTHING;

INSERT INTO graph_materializer_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- LLM model tier defaults
INSERT INTO core_settings (key, value, is_secret) VALUES ('llm.reasoning_model', 'claude-opus-4-7', false) ON CONFLICT (key) DO NOTHING;
INSERT INTO core_settings (key, value, is_secret) VALUES ('llm.general_model', 'claude-sonnet-4-6', false) ON CONFLICT (key) DO NOTHING;
"""
# Default credentials: admin / admin
# Change the password via the DB after first login.

# ---------------------------------------------------------------------------
# Migration: Wallet v2 (MVP-M1)
# Renames Phase-1 columns to RU-denominated names, adds concurrency/auto-topup
# fields, CHECK constraints, and the wallet_operations audit table.
# Safe to re-run: all ALTER TABLE use IF EXISTS / IF NOT EXISTS guards;
# CREATE TABLE uses IF NOT EXISTS; CHECK constraints use DO $$ BLOCK.
# ---------------------------------------------------------------------------
_MIGRATION_WALLET_V2 = """
-- Step 1: rename Phase-1 columns (idempotent via anonymous DO block)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_budget_wallets' AND column_name = 'balance_units'
    ) THEN
        ALTER TABLE user_budget_wallets RENAME COLUMN balance_units TO balance_ru;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_budget_wallets' AND column_name = 'reserved_units'
    ) THEN
        ALTER TABLE user_budget_wallets RENAME COLUMN reserved_units TO held_ru;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_budget_wallets' AND column_name = 'spent_units_lifetime'
    ) THEN
        ALTER TABLE user_budget_wallets RENAME COLUMN spent_units_lifetime TO spent_ru_lifetime;
    END IF;
END;
$$;

-- Step 2: add new columns (all IF NOT EXISTS)
ALTER TABLE user_budget_wallets
    ADD COLUMN IF NOT EXISTS floor_ru               INT          NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS version                INT          NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS auto_topup_enabled     BOOL         NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS auto_topup_trigger_ru  INT,
    ADD COLUMN IF NOT EXISTS auto_topup_amount_ru   INT,
    ADD COLUMN IF NOT EXISTS auto_topup_payment_id  TEXT,
    ADD COLUMN IF NOT EXISTS auto_topup_monthly_cap INT,
    ADD COLUMN IF NOT EXISTS auto_topup_consumed_mtd INT         NOT NULL DEFAULT 0;

-- Step 3: CHECK constraints (idempotent via DO block)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_wallet_held_ru_nonneg'
          AND conrelid = 'user_budget_wallets'::regclass
    ) THEN
        ALTER TABLE user_budget_wallets
            ADD CONSTRAINT ck_wallet_held_ru_nonneg CHECK (held_ru >= 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_wallet_balance_ge_held'
          AND conrelid = 'user_budget_wallets'::regclass
    ) THEN
        ALTER TABLE user_budget_wallets
            ADD CONSTRAINT ck_wallet_balance_ge_held CHECK (balance_ru >= held_ru);
    END IF;
END;
$$;

-- Step 4: wallet_operations audit table
CREATE TABLE IF NOT EXISTS wallet_operations (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        NOT NULL REFERENCES ui_users(id) ON DELETE CASCADE,
    run_id          UUID,
    idempotency_key TEXT        NOT NULL,
    op              VARCHAR(32) NOT NULL,
    delta_ru        INT         NOT NULL,
    balance_after   INT         NOT NULL,
    held_after      INT         NOT NULL,
    reason          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_wallet_ops_user_run
    ON wallet_operations (user_id, run_id, created_at DESC)
"""


_MIGRATION_FINDINGS_GRADES = """
CREATE TABLE IF NOT EXISTS findings_grades (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  finding_id  text NOT NULL,
  run_id      uuid NOT NULL,
  user_id     uuid NOT NULL,
  grade       char(1) NOT NULL CHECK (grade IN ('A','B','C','D')),
  note        text,
  graded_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, finding_id)
);
CREATE INDEX IF NOT EXISTS findings_grades_run_idx ON findings_grades(run_id);
CREATE INDEX IF NOT EXISTS findings_grades_finding_idx ON findings_grades(finding_id)
"""


_MIGRATION_SHARE_LINKS = """
CREATE TABLE IF NOT EXISTS run_share_links (
    token       TEXT        PRIMARY KEY,
    run_id      UUID        NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    created_by  UUID        NOT NULL REFERENCES ui_users(id) ON DELETE CASCADE,
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_share_links_run_id     ON run_share_links (run_id);
CREATE INDEX IF NOT EXISTS idx_share_links_expires_at ON run_share_links (expires_at)
"""


_MIGRATION_SAVED_TEMPLATES = """
CREATE TABLE IF NOT EXISTS saved_templates (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES ui_users(id) ON DELETE CASCADE,
    name        text NOT NULL,
    query       text NOT NULL,
    envelope    jsonb NOT NULL,
    strategy_id text NOT NULL,
    last_used   timestamptz,
    use_count   int NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, name)
);
CREATE INDEX IF NOT EXISTS saved_templates_user_idx ON saved_templates(user_id, last_used DESC);

CREATE TABLE IF NOT EXISTS user_defaults (
    user_id     uuid PRIMARY KEY REFERENCES ui_users(id) ON DELETE CASCADE,
    envelope    jsonb NOT NULL DEFAULT '{}',
    updated_at  timestamptz NOT NULL DEFAULT now()
)
"""

# Per-turn snapshot of the orchestrated IS-brain loop (Path B). One row per
# brain turn; the latest row for a run is the authoritative working memory.
_MIGRATION_WORKING_MEMORY = """
CREATE TABLE IF NOT EXISTS working_memory_snapshots (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          uuid NOT NULL,
    turn            int  NOT NULL,
    phase           varchar(32) NOT NULL,
    working_memory  jsonb NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, turn)
);
CREATE INDEX IF NOT EXISTS idx_wm_snapshots_run ON working_memory_snapshots(run_id, turn);

-- Hypothesis comments — analyst-grade collaboration on a specific hypothesis
-- within a loop run. hypothesis_id is the brain-assigned UUID stored in the
-- working memory; one row per (run, hypothesis, user, comment).
CREATE TABLE IF NOT EXISTS hypothesis_comments (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id         uuid NOT NULL,
    hypothesis_id  text NOT NULL,
    user_id        uuid NOT NULL,
    body           text NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_hyp_comments_run_hyp
  ON hypothesis_comments(run_id, hypothesis_id, created_at);

-- Per-finding analyst annotations. Persisted notes that also feed cross-run
-- priors (annotated findings get a confidence boost in fused_retrieve via the
-- existing user_score=+1 mechanism if grade='A' is set alongside).
CREATE TABLE IF NOT EXISTS finding_annotations (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      uuid NOT NULL,
    finding_id  text NOT NULL,
    user_id     uuid NOT NULL,
    body        text NOT NULL,
    color       varchar(16) DEFAULT 'yellow',
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, finding_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_finding_annotations_run
  ON finding_annotations(run_id, finding_id);
"""


def _split_sql_statements(sql: str) -> list[str]:
    """Split SQL on ';' but respect string literals and dollar-quoted blocks.

    psycopg2's execute() runs only the first statement of a multi-statement
    string. A naive split-on-';' breaks two cases:
      1. DO $$ BEGIN ... END; $$;  — ';' inside the dollar-quoted body
      2. '...$2b$12$.../...' — bcrypt hashes inside string literals contain '$'
         which can look like dollar-quote markers
    """
    statements: list[str] = []
    buf: list[str] = []
    i = 0
    in_dollar = False
    dollar_tag = ""
    in_single = False
    in_line_comment = False
    in_block_comment = False
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        # Block comment /* ... */
        if in_block_comment:
            buf.append(ch)
            if ch == "*" and nxt == "/":
                buf.append(nxt)
                i += 2
                in_block_comment = False
                continue
            i += 1
            continue
        # Line comment -- ... \n
        if in_line_comment:
            buf.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        # Inside single-quoted string
        if in_single:
            buf.append(ch)
            if ch == "'":
                # Check for escaped '' (two adjacent single quotes)
                if nxt == "'":
                    buf.append(nxt)
                    i += 2
                    continue
                in_single = False
            i += 1
            continue
        # Inside dollar-quoted block
        if in_dollar:
            if ch == "$" and sql.startswith(dollar_tag, i):
                buf.append(dollar_tag)
                i += len(dollar_tag)
                in_dollar = False
                dollar_tag = ""
                continue
            buf.append(ch)
            i += 1
            continue
        # Not in any quote — check for openers
        if ch == "-" and nxt == "-":
            in_line_comment = True
            buf.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            buf.append(ch)
            i += 1
            continue
        if ch == "'":
            in_single = True
            buf.append(ch)
            i += 1
            continue
        if ch == "$":
            # Match $$ or $<identifier>$ where identifier starts with letter/underscore
            end = sql.find("$", i + 1)
            if end != -1:
                tag_body = sql[i + 1 : end]
                if tag_body == "" or (tag_body[0].isalpha() or tag_body[0] == "_") and all(
                    c.isalnum() or c == "_" for c in tag_body
                ):
                    dollar_tag = sql[i : end + 1]
                    in_dollar = True
                    buf.append(dollar_tag)
                    i = end + 1
                    continue
        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    trailing = "".join(buf).strip()
    if trailing:
        statements.append(trailing)
    return statements


def run_migrations() -> None:
    # Ensure each migration block ends with ';' so concatenation doesn't merge
    # the last statement of one block with the first of the next.
    parts = [_MIGRATION, _SEED, _MIGRATION_WALLET_V2, _MIGRATION_FINDINGS_GRADES, _MIGRATION_SHARE_LINKS, _MIGRATION_SAVED_TEMPLATES, _MIGRATION_WORKING_MEMORY]
    all_sql = "\n".join(p.rstrip().rstrip(";") + ";\n" for p in parts)
    statements = _split_sql_statements(all_sql)
    with get_conn() as conn:
        with conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)


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
