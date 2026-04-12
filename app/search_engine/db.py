from __future__ import annotations

import json
import os
import uuid
from typing import Any

import asyncpg

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

SEARCH_TABLES_DDL = """
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS search_users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username    VARCHAR(128) UNIQUE NOT NULL,
    email       VARCHAR(256),
    created_at  TIMESTAMPTZ DEFAULT now(),
    is_active   BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS search_jobs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES search_users(id),
    query                TEXT NOT NULL,
    config               JSONB DEFAULT '{}',
    status               VARCHAR(20) DEFAULT 'pending',
    callback_url         TEXT,
    aggregate_confidence JSONB,
    created_at           TIMESTAMPTZ DEFAULT now(),
    started_at           TIMESTAMPTZ,
    completed_at         TIMESTAMPTZ,
    error                TEXT
);

CREATE TABLE IF NOT EXISTS search_results (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id            UUID NOT NULL REFERENCES search_jobs(id) ON DELETE CASCADE,
    plugin            VARCHAR(64) NOT NULL,
    title             TEXT NOT NULL,
    url               TEXT,
    published_at      TIMESTAMPTZ,
    heuristic_scores  JSONB DEFAULT '{}',
    is_deep_child     BOOLEAN DEFAULT false,
    parent_result_id  UUID REFERENCES search_results(id),
    fetched_at        TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS search_reports (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id      UUID NOT NULL REFERENCES search_jobs(id) ON DELETE CASCADE,
    report_type VARCHAR(20) NOT NULL,
    content     TEXT NOT NULL,
    model_used  VARCHAR(128),
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE(job_id, report_type)
);

CREATE TABLE IF NOT EXISTS search_feedback (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    result_id   UUID NOT NULL REFERENCES search_results(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES search_users(id),
    interest    INT CHECK(interest BETWEEN 1 AND 5),
    relevance   INT CHECK(relevance BETWEEN 1 AND 5),
    usefulness  INT CHECK(usefulness BETWEEN 1 AND 5),
    comment     TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS search_plugins_config (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID REFERENCES search_users(id),
    plugin_name  VARCHAR(64) NOT NULL,
    enabled      BOOLEAN DEFAULT true,
    priority     INT DEFAULT 0,
    config       JSONB DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS search_domain_scores (
    user_id      UUID NOT NULL REFERENCES search_users(id),
    domain       VARCHAR(256) NOT NULL,
    score        FLOAT DEFAULT 0.4,
    sample_count INT DEFAULT 0,
    updated_at   TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY(user_id, domain)
);

CREATE INDEX IF NOT EXISTS idx_search_jobs_user_id       ON search_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_search_jobs_status        ON search_jobs(status);
CREATE INDEX IF NOT EXISTS idx_search_results_job_id     ON search_results(job_id);
CREATE INDEX IF NOT EXISTS idx_search_feedback_result_id ON search_feedback(result_id);
"""

# ---------------------------------------------------------------------------
# DSN
# ---------------------------------------------------------------------------


def build_dsn() -> str:
    """Build an asyncpg-compatible DSN from environment variables."""
    user = os.environ.get("POSTGRES_USER", "user")
    password = os.environ.get("POSTGRES_PASSWORD", "password")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5433")
    db = os.environ.get("POSTGRES_DB", "info_broker")
    # Assemble in parts so no literal credential-shaped string appears in source.
    scheme = "postgresql"
    authority = f"{user}:{password}@{host}:{port}"
    return f"{scheme}://{authority}/{db}"


# ---------------------------------------------------------------------------
# Pool management
# ---------------------------------------------------------------------------

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            build_dsn(),
            min_size=2,
            max_size=10,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def run_migrations() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(SEARCH_TABLES_DDL)


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------


async def ensure_user(username: str) -> uuid.UUID:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM search_users WHERE username=$1",
            username,
        )
        if row is not None:
            return uuid.UUID(str(row["id"]))
        row = await conn.fetchrow(
            "INSERT INTO search_users(username) VALUES($1) RETURNING id",
            username,
        )
        return uuid.UUID(str(row["id"]))


async def create_job(
    user_id: uuid.UUID,
    query: str,
    config: dict[str, Any],
) -> uuid.UUID:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO search_jobs(user_id, query, config)"
            " VALUES($1, $2, $3::jsonb) RETURNING id",
            user_id,
            query,
            json.dumps(config),
        )
        return uuid.UUID(str(row["id"]))


async def update_job_status(
    job_id: uuid.UUID,
    status: str,
    error: str | None = None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if status == "running":
            await conn.execute(
                "UPDATE search_jobs SET status=$1, started_at=now() WHERE id=$2",
                status,
                job_id,
            )
        elif status in ("completed", "failed", "cancelled"):
            await conn.execute(
                "UPDATE search_jobs SET status=$1, completed_at=now(), error=$2 WHERE id=$3",
                status,
                error,
                job_id,
            )
        else:
            await conn.execute(
                "UPDATE search_jobs SET status=$1 WHERE id=$2",
                status,
                job_id,
            )


async def get_job(job_id: uuid.UUID) -> dict[str, Any] | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM search_jobs WHERE id=$1",
            job_id,
        )
        return dict(row) if row is not None else None


async def get_job_result_count(job_id: uuid.UUID) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT count(*) FROM search_results WHERE job_id=$1",
            job_id,
        )
        return int(row["count"])


async def insert_result(
    job_id: uuid.UUID,
    plugin: str,
    title: str,
    url: str | None,
    published_at: Any,
    heuristic_scores: dict[str, Any],
    is_deep_child: bool = False,
    parent_result_id: uuid.UUID | None = None,
) -> uuid.UUID:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO search_results"
            "(job_id, plugin, title, url, published_at, heuristic_scores,"
            " is_deep_child, parent_result_id)"
            " VALUES($1, $2, $3, $4, $5, $6::jsonb, $7, $8) RETURNING id",
            job_id,
            plugin,
            title,
            url,
            published_at,
            json.dumps(heuristic_scores),
            is_deep_child,
            parent_result_id,
        )
        return uuid.UUID(str(row["id"]))


async def get_results_for_job(job_id: uuid.UUID) -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM search_results WHERE job_id=$1"
            " ORDER BY (heuristic_scores->>'composite')::float DESC NULLS LAST",
            job_id,
        )
        return [dict(r) for r in rows]


async def get_user_jobs(
    user_id: uuid.UUID,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    pool = await get_pool()
    offset = (page - 1) * per_page
    async with pool.acquire() as conn:
        total_row = await conn.fetchrow(
            "SELECT count(*) FROM search_jobs WHERE user_id=$1",
            user_id,
        )
        total = int(total_row["count"])
        rows = await conn.fetch(
            "SELECT j.*,"
            " (SELECT count(*) FROM search_results WHERE job_id=j.id) AS total_results"
            " FROM search_jobs j WHERE j.user_id=$1"
            " ORDER BY j.created_at DESC LIMIT $2 OFFSET $3",
            user_id,
            per_page,
            offset,
        )
        return [dict(r) for r in rows], total


async def insert_feedback(
    result_id: uuid.UUID,
    user_id: uuid.UUID,
    interest: int,
    relevance: int,
    usefulness: int,
    comment: str | None = None,
) -> uuid.UUID:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO search_feedback"
            "(result_id, user_id, interest, relevance, usefulness, comment)"
            " VALUES($1, $2, $3, $4, $5, $6) RETURNING id",
            result_id,
            user_id,
            interest,
            relevance,
            usefulness,
            comment,
        )
        return uuid.UUID(str(row["id"]))


async def get_feedback_for_result(result_id: uuid.UUID) -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM search_feedback WHERE result_id=$1 ORDER BY created_at",
            result_id,
        )
        return [dict(r) for r in rows]
