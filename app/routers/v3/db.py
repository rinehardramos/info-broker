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
    started_at           TIMESTAMPTZ DEFAULT now(),
    finished_at          TIMESTAMPTZ
);

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
    'Default pipeline for Agent chat: agent_input → ddg_search → manual_scoring',
    true
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO pipeline_nodes (id, pipeline_id, node_type, label, config, position_x, position_y)
VALUES
    ('00000000-0000-4000-8000-000000000011', '00000000-0000-4000-8000-000000000001', 'agent_input',    'Agent CLI',      '{}', 0, 0),
    ('00000000-0000-4000-8000-000000000012', '00000000-0000-4000-8000-000000000001', 'ddg_search',     'DDG Search',     '{}', 0, 1),
    ('00000000-0000-4000-8000-000000000013', '00000000-0000-4000-8000-000000000001', 'manual_scoring', 'Manual Scoring', '{}', 0, 2)
ON CONFLICT (id) DO NOTHING;

INSERT INTO pipeline_edges (id, pipeline_id, source_node_id, target_node_id, edge_type)
VALUES
    ('00000000-0000-4000-8000-000000000021', '00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000011', '00000000-0000-4000-8000-000000000012', 'results'),
    ('00000000-0000-4000-8000-000000000022', '00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000012', '00000000-0000-4000-8000-000000000013', 'results')
ON CONFLICT (id) DO NOTHING;
"""
# Default credentials: admin / admin
# Change the password via the DB after first login.


def run_migrations() -> None:
    # psycopg2 execute() only runs the first statement in a multi-statement
    # string. Split on ";" and run each non-empty statement individually.
    statements = [s.strip() for s in (_MIGRATION + _SEED).split(";") if s.strip()]
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
