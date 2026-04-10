"""info-broker FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.deps import get_db_conn
from app.lib.rate_limit import limiter
from app.routers import media, profiles, research, search

_SCHEMA_MIGRATION = """
ALTER TABLE linkedin_profiles
    ADD COLUMN IF NOT EXISTS research_status       VARCHAR DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS is_smb                BOOLEAN,
    ADD COLUMN IF NOT EXISTS needs_outsourcing_prob DECIMAL,
    ADD COLUMN IF NOT EXISTS needs_cheap_labor_prob DECIMAL,
    ADD COLUMN IF NOT EXISTS searching_vendors_prob DECIMAL,
    ADD COLUMN IF NOT EXISTS research_summary      TEXT,
    ADD COLUMN IF NOT EXISTS system_confidence_score INT,
    ADD COLUMN IF NOT EXISTS confidence_rationale  TEXT,
    ADD COLUMN IF NOT EXISTS search_queries_used   TEXT,
    ADD COLUMN IF NOT EXISTS user_grade            INT,
    ADD COLUMN IF NOT EXISTS user_feedback         TEXT;
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = next(get_db_conn())
    try:
        cur = conn.cursor()
        cur.execute(_SCHEMA_MIGRATION)
        conn.commit()
        cur.close()
    finally:
        conn.close()
    yield


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
