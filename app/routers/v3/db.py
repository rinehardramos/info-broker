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
