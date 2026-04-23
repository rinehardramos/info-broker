"""info-broker FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.lib.rate_limit import limiter
from app.routers import media, profiles, research, search

_SCHEMA_MIGRATION = """
CREATE TABLE IF NOT EXISTS linkedin_profiles (
    id        VARCHAR(128) PRIMARY KEY,
    first_name VARCHAR(256),
    last_name  VARCHAR(256),
    headline   TEXT,
    about      TEXT,
    raw_data   JSONB
);

ALTER TABLE linkedin_profiles
    ADD COLUMN IF NOT EXISTS research_status        VARCHAR DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS is_smb                 BOOLEAN,
    ADD COLUMN IF NOT EXISTS needs_outsourcing_prob DECIMAL,
    ADD COLUMN IF NOT EXISTS needs_cheap_labor_prob DECIMAL,
    ADD COLUMN IF NOT EXISTS searching_vendors_prob DECIMAL,
    ADD COLUMN IF NOT EXISTS research_summary       TEXT,
    ADD COLUMN IF NOT EXISTS system_confidence_score INT,
    ADD COLUMN IF NOT EXISTS confidence_rationale   TEXT,
    ADD COLUMN IF NOT EXISTS search_queries_used    TEXT,
    ADD COLUMN IF NOT EXISTS user_grade             INT,
    ADD COLUMN IF NOT EXISTS user_feedback          TEXT;
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging
    import os
    import psycopg2

    _log = logging.getLogger(__name__)

    # Build connection kwargs — prefer DATABASE_URL, fall back to individual vars.
    database_url = os.getenv("DATABASE_URL")
    try:
        if database_url:
            conn = psycopg2.connect(database_url)
        else:
            conn = psycopg2.connect(
                dbname=os.getenv("POSTGRES_DB", "info_broker"),
                user=os.getenv("POSTGRES_USER", "user"),
                password=os.getenv("POSTGRES_PASSWORD", "password"),
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=os.getenv("POSTGRES_PORT", "5432"),
            )
        try:
            cur = conn.cursor()
            cur.execute(_SCHEMA_MIGRATION)
            conn.commit()
            cur.close()
        finally:
            conn.close()
    except Exception as exc:
        _log.warning("Postgres unavailable at startup (profiles/research disabled): %s", exc)

    from app.search_engine.db import run_migrations as se_migrate, close_pool as se_close
    from app.search_engine.qdrant import ensure_collection as se_ensure_qdrant
    try:
        await se_migrate()
    except Exception as exc:
        _log.warning("Search-engine DB migration skipped: %s", exc)
    try:
        se_ensure_qdrant()
    except Exception as exc:
        _log.warning("Qdrant search_results setup: %s", exc)
    yield
    await se_close()


app = FastAPI(
    lifespan=lifespan,
    title="info-broker",
    version="0.4.0",
    description=(
        "Information-gathering and OSINT research service. Hosts both the OSINT "
        "/profiles surface and the /v1/* media surface (weather, news, songs, "
        "jokes, social mentions) consumed by the playgen-dj microservice."
    ),
)

# slowapi rate limiter — applies the per-key bucket defined in app/lib/rate_limit.py.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.get("/healthz", tags=["health"])
def healthz() -> dict:
    return {"status": "ok"}


app.include_router(profiles.router)
app.include_router(research.router)
app.include_router(search.router)
app.include_router(media.router)

from app.search_engine.router import router as search_engine_router  # noqa: E402
app.include_router(search_engine_router)
