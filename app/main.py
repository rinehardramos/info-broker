"""info-broker FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

# Configure root logger at INFO so background task log.info() calls reach
# uvicorn's stdout. Without this, Python's default WARNING level silently
# swallows every INFO/DEBUG record emitted by background tasks.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

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

CREATE TABLE IF NOT EXISTS social_tokens (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    platform   TEXT        NOT NULL CHECK (platform IN ('twitter','facebook')),
    owner_ref  TEXT        NOT NULL,
    ciphertext BYTEA       NOT NULL,
    nonce      BYTEA       NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS social_tokens_owner_idx ON social_tokens (owner_ref, platform);
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging
    import os
    import psycopg2

    # Load secrets from OpenBao before any os.getenv() calls.
    # No-op if OPENBAO_ADDR is not set (falls back to .env).
    from app.secrets import load_secrets
    load_secrets("info-broker")

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
    try:
        from app.memory.collection import ensure_research_memory_collection
        ensure_research_memory_collection()
    except Exception as exc:
        _log.warning("research_memory collection setup: %s", exc)

    from app.routers.v3.db import run_migrations as v3_migrate
    try:
        v3_migrate()
    except Exception as exc:
        _log.warning("v3 DB migration skipped: %s", exc)

    os.makedirs("/tmp/exports", exist_ok=True)

    # Start graph materializer background task
    import asyncio as _aio
    try:
        from app.knowledge.materializer import materializer_loop
        _aio.create_task(materializer_loop(interval_seconds=5))
    except Exception as exc:
        _log.warning("Graph materializer not started: %s", exc)

    # Start KG curator background task
    try:
        from app.knowledge.curator import KGCurator
        _curator = KGCurator()
        _aio.create_task(_curator.run_curator_loop(600))
    except Exception as exc:
        _log.warning("KG curator not started: %s", exc)

    # Start memory lifecycle sweep
    try:
        from app.memory.lifecycle import run_lifecycle_sweep
        _aio.create_task(run_lifecycle_sweep(1800))
    except Exception as exc:
        _log.warning("Memory lifecycle sweep not started: %s", exc)

    # Start daily LLM curation (contradiction resolution + entity dedup)
    async def _llm_curation_loop(interval_seconds: int = 86400) -> None:
        import asyncio as _a
        while True:
            await _a.sleep(interval_seconds)
            try:
                from app.knowledge.llm_curator import resolve_contradictions_batch, generate_curation_suggestions
                result = await resolve_contradictions_batch(limit=20)
                _log.info("LLM curation: resolved %d contradictions", result.get("resolved", 0))
                sug = await generate_curation_suggestions(limit=20)
                _log.info("LLM curation: generated %d suggestions", sug.get("created", 0))
            except Exception as exc:
                _log.warning("LLM curation sweep failed: %s", exc)
    try:
        _aio.create_task(_llm_curation_loop(86400))
    except Exception as exc:
        _log.warning("LLM curator loop not started: %s", exc)

    # Reload any confirm_pending runs from DB into memory (survives restarts)
    try:
        from app.routers.v3.db import fetch_all as _fetch_all
        from app.routers.v3.agent import _CONFIRM_PENDING
        import json as _json
        rows = _fetch_all(
            "SELECT id, confirmation_data FROM pipeline_runs WHERE status = 'confirm_pending'", ()
        )
        for row in rows:
            data = row.get("confirmation_data")
            if data and isinstance(data, dict) and data.get("uid"):
                _CONFIRM_PENDING[str(row["id"])] = data
        if rows:
            _log.info("Restored %d confirm_pending runs from DB", len(rows))
    except Exception as exc:
        _log.warning("confirm_pending restore failed (non-fatal): %s", exc)

    # Mark any IS brain runs that were in-flight when the server restarted as failed.
    # Their Claude Code subprocesses are dead — they will never complete or push results.
    try:
        from app.routers.v3.db import execute as _exec, fetch_all as _fetch_all2
        killed = _fetch_all2(
            """SELECT id FROM pipeline_runs
               WHERE status = 'running' AND trigger_type = 'agent_is'""",
            (),
        )
        if killed:
            _exec(
                """UPDATE pipeline_runs
                   SET status = 'failed',
                       finished_at = now(),
                       error_message = 'Server restarted — subprocess was killed'
                   WHERE status = 'running' AND trigger_type = 'agent_is'""",
                (),
            )
            _log.info("Marked %d orphaned running IS brain runs as failed on startup", len(killed))
            # Notify any already-connected browsers after WS is up (slight delay)
            async def _notify_killed() -> None:
                import asyncio as _a2
                await _a2.sleep(2)
                try:
                    from app.routers.v3.stream import push_event as _push
                    from app.routers.v3.db import fetch_all as _fa
                    rows = _fa(
                        "SELECT id, user_id FROM pipeline_runs WHERE id = ANY(%s)",
                        ([str(r["id"]) for r in killed],),
                    )
                    for row in rows:
                        await _push(str(row["user_id"]), {
                            "type": "job.failed",
                            "job_id": str(row["id"]),
                            "run_id": str(row["id"]),
                            "status": "failed",
                            "message": "Research stopped — server was restarted",
                        })
                except Exception:
                    pass
            _aio.create_task(_notify_killed())
    except Exception as exc:
        _log.warning("Orphaned run cleanup failed (non-fatal): %s", exc)

    # Mark manual (Temporal) pipeline runs that were in-flight at restart as failed.
    try:
        from app.pipeline.reconcile import reconcile_orphaned_runs as _reconcile
        _reconcile()
    except Exception as exc:
        _log.warning("Manual pipeline run reconciliation failed (non-fatal): %s", exc)

    # Periodic sweep — catch any runs that slipped through (> 20 min with no completion)
    async def _stale_run_sweep(interval_seconds: int = 300) -> None:
        import asyncio as _a
        while True:
            await _a.sleep(interval_seconds)
            try:
                from app.routers.v3.db import execute as _e
                _e(
                    """UPDATE pipeline_runs
                       SET status = 'failed',
                           finished_at = now(),
                           error_message = 'Run exceeded maximum duration — killed by sweep'
                       WHERE status = 'running'
                         AND trigger_type = 'agent_is'
                         AND started_at < NOW() - INTERVAL '20 minutes'""",
                    (),
                )
            except Exception as exc:
                _log.warning("Stale run sweep error (non-fatal): %s", exc)
            try:
                from app.pipeline.reconcile import sweep_stale_runs as _sweep
                _sweep(max_age_minutes=60)
            except Exception as exc:
                _log.warning("Manual pipeline stale sweep error (non-fatal): %s", exc)

    try:
        _aio.create_task(_stale_run_sweep(300))
    except Exception as exc:
        _log.warning("Stale run sweep not started: %s", exc)

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

from starlette.middleware.cors import CORSMiddleware  # noqa: E402
import os as _cors_os  # noqa: E402

_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
]
# Allow additional origins from env (comma-separated)
_extra = _cors_os.getenv("CORS_ALLOWED_ORIGINS", "")
if _extra:
    _CORS_ORIGINS.extend(o.strip() for o in _extra.split(",") if o.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_origin_regex=r"https://.*\.ngrok-free\.(app|dev)",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Session-Id",
                   "X-MCP-Signature", "X-MCP-Timestamp", "X-Caller-Identity"],
)


@app.get("/healthz", tags=["health"])
def healthz() -> dict:
    return {"status": "ok"}


app.include_router(profiles.router)
app.include_router(research.router)
app.include_router(search.router)
app.include_router(media.router)

from app.search_engine.router import router as search_engine_router  # noqa: E402
app.include_router(search_engine_router)

from app.routers.v3.auth import router as v3_auth_router  # noqa: E402
from app.routers.v3.users import router as v3_users_router  # noqa: E402
from app.routers.v3.plugins import router as v3_plugins_router  # noqa: E402
from app.routers.v3.settings import router as v3_settings_router  # noqa: E402
from app.routers.v3.monitors import router as v3_monitors_router  # noqa: E402
from app.routers.v3.agent import router as v3_agent_router  # noqa: E402
from app.routers.v3.jobs import router as v3_jobs_router  # noqa: E402
from app.routers.v3.stream import router as v3_stream_router  # noqa: E402
from app.routers.v3.apify import router as v3_apify_router  # noqa: E402
from app.routers.v3.pipelines import router as v3_pipelines_router  # noqa: E402
from app.routers.v3.nodes_api import router as v3_nodes_router  # noqa: E402
from app.routers.v3.research_api import router as v3_research_router  # noqa: E402
from app.routers.v3.knowledge_api import router as v3_knowledge_router  # noqa: E402
from app.routers.v3.admin_api import router as v3_admin_router  # noqa: E402
from app.routers.v3.exports import router as v3_exports_router  # noqa: E402
from app.routers.v3.curation_api import router as v3_curation_router  # noqa: E402
from app.routers.v3.brain_questions import router as v3_brain_questions_router  # noqa: E402
from app.routers.v3.sources_api import router as v3_sources_router  # noqa: E402
from app.routers.v3.sessions_api import router as v3_sessions_router  # noqa: E402
from app.routers.v3.metrics import router as v3_metrics_router  # noqa: E402
app.include_router(v3_auth_router)
app.include_router(v3_users_router)
app.include_router(v3_plugins_router)
app.include_router(v3_settings_router)
app.include_router(v3_monitors_router)
app.include_router(v3_agent_router)
app.include_router(v3_jobs_router)
app.include_router(v3_stream_router)
app.include_router(v3_apify_router)
app.include_router(v3_pipelines_router)
app.include_router(v3_nodes_router)
app.include_router(v3_research_router)
app.include_router(v3_knowledge_router)
app.include_router(v3_admin_router)
app.include_router(v3_exports_router)
app.include_router(v3_curation_router)
app.include_router(v3_brain_questions_router)
app.include_router(v3_sources_router)
app.include_router(v3_sessions_router)
app.include_router(v3_metrics_router, prefix="/api/v3")
