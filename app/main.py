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

import os as _mon_os

_MONITORING_ENABLED = _mon_os.getenv("MONITORING_ENABLED", "true").lower() not in ("0", "false", "no")

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

    # -----------------------------------------------------------------------
    # platform-monitoring: register adapters + bootstrap ClickHouse schema.
    # Fail-soft: any error here logs a warning and continues — monitoring
    # must never prevent the host app from starting.
    # -----------------------------------------------------------------------
    _monitoring_aclose: list = []
    if _MONITORING_ENABLED:
        try:
            from platform_monitoring.adapters.redis_hot_store import RedisHotStore
            from platform_monitoring.adapters.clickhouse_sink import ClickHouseSink
            from platform_monitoring.ports.hot_store import register_hot_store
            from platform_monitoring.ports.event_sink import register_event_sink
            from platform_monitoring.settings import MonitoringSettings

            _mon_settings = MonitoringSettings()  # type: ignore[call-arg]
            _hot = RedisHotStore(_mon_settings.monitoring_redis_url, stream_maxlen=_mon_settings.stream_maxlen)
            await _hot.ensure_group()
            register_hot_store(_hot)
            _monitoring_aclose.append(_hot)

            _sink = ClickHouseSink(
                _mon_settings.clickhouse_url,
                database=_mon_settings.clickhouse_database,
                raw_retention_days=_mon_settings.raw_retention_days,
            )
            await _sink.bootstrap_schema()
            register_event_sink(_sink)
            _monitoring_aclose.append(_sink)
            _log.info("platform-monitoring adapters registered")
        except Exception as _mon_exc:
            _log.warning(
                "platform-monitoring startup failed (monitoring disabled this session): %s", _mon_exc
            )

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

    # Strategy gate audit — fail loud if any registered strategy declares a
    # gate check kind the strategist runtime doesn't implement. Without this,
    # the runtime fail-OPENed on unknown kinds and runs reported success with
    # 0 work done (issue: skeleton strategies "succeeding" in 0.1s).
    try:
        from pathlib import Path as _Path
        from app.pipeline.catalogs.loader import load_catalog as _load_catalog
        from app.pipeline.strategist import audit_strategy_gates as _audit_gates
        _strat_dir = _Path(__file__).resolve().parent / "pipeline" / "catalogs" / "registries" / "strategies"
        _strategies = _load_catalog("strategy", _strat_dir)
        _violations = _audit_gates(_strategies)
        if _violations:
            for v in _violations:
                _log.error(
                    "GATE_AUDIT_VIOLATION strategy=%s phase=%s unknown_kind=%s — "
                    "this gate would fail-CLOSED at runtime (was fail-open before "
                    "the audit landed). Either implement the check kind in "
                    "strategist._GATE_CHECKS or remove it from the strategy catalog.",
                    v.strategy_id, v.phase_id, v.unknown_kind,
                )
            _log.error(
                "GATE_AUDIT: %d unknown gate-check kind(s) detected across %d strategies. "
                "Runs touching these strategies WILL fail their gates until fixed. "
                "Set STRATEGY_GATE_AUDIT_STRICT=true to refuse startup on violations.",
                len(_violations),
                len({v.strategy_id for v in _violations}),
            )
            if os.getenv("STRATEGY_GATE_AUDIT_STRICT", "").lower() in ("1", "true", "yes"):
                raise RuntimeError(
                    f"strict gate audit: {len(_violations)} violations — "
                    f"refusing to start. See ERROR logs above."
                )
        else:
            _log.info("GATE_AUDIT: all %d strategies' gate-check kinds resolved.", len(_strategies))
    except RuntimeError:
        raise  # strict mode — let it propagate
    except Exception as exc:
        _log.warning("GATE_AUDIT skipped: %s", exc)

    # ---------------------------------------------------------------------------
    # Strategy / tactic alignment audit (spec 2026-05-23)
    # Fail-CLOSED unconditionally — there is no env-var escape hatch because
    # misalignment yields silently-broken user-facing runs (per PR #116).
    # ---------------------------------------------------------------------------
    try:
        from app.pipeline.catalogs.loader import load_catalog as _load_catalog2
        from app.pipeline.catalogs.audit import run_audit_or_fail as _run_tactic_audit
        from pathlib import Path as _Path2
        _strat_dir2 = _Path2(__file__).resolve().parent / "pipeline" / "catalogs" / "registries" / "strategies"
        _tactics_dir = _Path2(__file__).resolve().parent / "pipeline" / "catalogs" / "registries" / "tactics"
        _strategies2 = _load_catalog2("strategy", _strat_dir2)
        _tactics_catalog = _load_catalog2("tactic", _tactics_dir)
        _run_tactic_audit(_strategies2, _tactics_catalog)
        _log.info("Strategy/tactic catalog audit passed.")
    except Exception as _audit_exc:
        _log.error("Strategy/tactic catalog audit FAILED: %s", _audit_exc)
        raise   # fail-CLOSED — API does not start

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

    # Temporal-aware orphan watchdog (queries actual workflow state, doesn't
    # rely on age alone). Authoritative reconciliation path; the simple
    # `_stale_run_sweep` above stays as a belt-and-suspenders safety net.
    try:
        from app.pipeline.orphan_watchdog import start_orphan_watchdog
        await start_orphan_watchdog()
    except Exception as exc:
        _log.warning("Orphan watchdog not started: %s", exc)

    yield

    for _mon_closeable in _monitoring_aclose:
        try:
            await _mon_closeable.aclose()
        except Exception:
            pass

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
    "https://infobroker.tech",
    "https://www.infobroker.tech",
]
# Allow additional origins from env (comma-separated)
_extra = _cors_os.getenv("CORS_ALLOWED_ORIGINS", "")
if _extra:
    _CORS_ORIGINS.extend(o.strip() for o in _extra.split(",") if o.strip())

_CORS_ORIGIN_REGEX = r"https://.*\.ngrok-free\.(app|dev)"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    # ngrok-free for legacy demos.
    allow_origin_regex=_CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Session-Id",
                   "X-MCP-Signature", "X-MCP-Timestamp", "X-Caller-Identity"],
)

# MonitoringMiddleware — registered LAST so it is the OUTERMOST ASGI layer.
# Captures every request before CORS, before SlowAPI, before any route handler.
# Fail-soft: if MONITORING_ENABLED=false or adapters failed, this block is skipped.
if _MONITORING_ENABLED:
    try:
        from platform_monitoring.middleware import MonitoringMiddleware
        from platform_monitoring.adapters.geolite2_geo import GeoLite2Geo
        from jose import jwt as _jwt_mon
        import os as _mw_os

        _jwt_secret_mon = _mw_os.getenv("JWT_SECRET", "change-me-in-production")

        def _decode_jwt_for_monitoring(token: str) -> dict:
            try:
                return _jwt_mon.decode(token, _jwt_secret_mon, algorithms=["HS256"], options={"verify_exp": False})
            except Exception:
                return {}

        _geo_path = _mw_os.getenv("GEOLITE2_DB_PATH", "").strip()
        _geo_resolver = GeoLite2Geo(db_path=_geo_path) if _geo_path else None
        _trusted = {c.strip() for c in _mw_os.getenv("MON_TRUSTED_PROXIES", "").split(",") if c.strip()}

        app.add_middleware(
            MonitoringMiddleware,
            geolite2_resolver=_geo_resolver,
            jwt_decoder=_decode_jwt_for_monitoring,
            trusted_proxies=_trusted,
        )
    except Exception as _mw_exc:
        logging.getLogger("app.main").warning("MonitoringMiddleware not registered: %s", _mw_exc)


# ---------------------------------------------------------------------------
# Uncaught-exception handler with CORS-header echo (#97)
# ---------------------------------------------------------------------------
#
# FastAPI's default 500 path returns before CORSMiddleware can add headers, so
# browsers report uncaught exceptions as "CORS blocked" instead of HTTP 500 —
# hiding the real failure (#96 spent ~36h masked this way). This handler
# echoes the matching CORS header back on 500s so DevTools shows the real
# status code, while keeping the body generic (no traceback / path leaks).

import re as _re_cors  # noqa: E402
from fastapi import Request as _Request  # noqa: E402
from fastapi.responses import JSONResponse as _JSONResponse  # noqa: E402

_CORS_ORIGIN_REGEX_COMPILED = _re_cors.compile(_CORS_ORIGIN_REGEX)


def _is_origin_allowed(origin: str | None) -> bool:
    """True iff origin is in the explicit allowlist OR matches the regex."""
    if not origin:
        return False
    if origin in _CORS_ORIGINS:
        return True
    return bool(_CORS_ORIGIN_REGEX_COMPILED.fullmatch(origin))


async def cors_safe_500_handler(request: _Request, exc: Exception) -> _JSONResponse:
    """Uncaught-exception handler — returns 500 with CORS headers echoed back
    when the request's Origin is allowlisted.

    Body stays generic ("Internal Server Error") so file paths and tracebacks
    don't leak to clients. The real exception is logged at ERROR with the
    traceback, so admins still see the cause.
    """
    # Log with traceback for admins. exc_info=True attaches the full
    # traceback to the log record.
    logging.getLogger("app.main.cors_safe_500").error(
        "uncaught exception on %s %s: %s",
        request.method, request.url.path, exc, exc_info=True,
    )

    origin = request.headers.get("origin")
    headers: dict[str, str] = {}
    if _is_origin_allowed(origin):
        headers["Access-Control-Allow-Origin"] = origin  # type: ignore[assignment]
        headers["Access-Control-Allow-Credentials"] = "true"
        # Vary: Origin so caches don't reuse a no-CORS response for a CORS one.
        headers["Vary"] = "Origin"

    return _JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
        headers=headers,
    )


# Register against the broadest exception type. FastAPI's HTTPException path
# already routes through middleware (so 4xx CORS works); this targets the
# uncaught-exception path that bypasses middleware.
app.add_exception_handler(Exception, cors_safe_500_handler)


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
from app.routers.v3.oauth import router as v3_oauth_router  # noqa: E402
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
from app.routers.v3.brain import router as v3_brain_router, runs_router as v3_runs_router  # noqa: E402
from app.routers.v3.preflight import router as v3_preflight_router  # noqa: E402
from app.routers.v3.findings_grades import router as v3_findings_grades_router  # noqa: E402
from app.routers.v3.wallet import router as v3_wallet_router, runs_cost_router as v3_runs_cost_router  # noqa: E402
from app.routers.v3.share import router as v3_share_router  # noqa: E402
from app.routers.v3.templates import router as v3_templates_router  # noqa: E402
from app.routers.v3.replay import router as v3_replay_router  # noqa: E402
from app.routers.v3.evidence import router as v3_evidence_router  # noqa: E402
from app.routers.v3.health import router as v3_health_router  # noqa: E402
from app.routers.v3.working_memory import router as v3_working_memory_router  # noqa: E402
from app.routers.v3.investigation_templates import router as v3_investigation_templates_router  # noqa: E402
from app.routers.v3.absorption import router as v3_absorption_router  # noqa: E402
from app.routers.v3.modes import router as v3_modes_router  # noqa: E402
from app.routers.v3.visibility import router as v3_visibility_router  # noqa: E402
from app.routers.v3.benchmarks import router as v3_benchmarks_router  # noqa: E402
app.include_router(v3_auth_router)
app.include_router(v3_benchmarks_router)
app.include_router(v3_oauth_router)
app.include_router(v3_users_router)
app.include_router(v3_plugins_router)
app.include_router(v3_settings_router)
app.include_router(v3_visibility_router)
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

if _MONITORING_ENABLED:
    try:
        from fastapi import Depends as _Depends_mon
        from platform_monitoring.router import create_monitoring_router
        from app.routers.v3.auth import require_admin as _require_admin_mon
        from app.routers.v3.admin_api import get_tool_stats as _get_tool_stats_mon

        async def _mcp_stats_provider():
            # get_tool_stats is sync + expects a user dict; admin scope only needs is_admin.
            return _get_tool_stats_mon(user={"is_admin": True})

        app.include_router(
            create_monitoring_router(
                admin_dependency=_Depends_mon(_require_admin_mon),
                mcp_stats_provider=_mcp_stats_provider,
            )
        )
    except Exception as _router_exc:
        logging.getLogger("app.main").warning("monitoring router not mounted: %s", _router_exc)

app.include_router(v3_exports_router)
app.include_router(v3_curation_router)
app.include_router(v3_brain_questions_router)
app.include_router(v3_sources_router)
app.include_router(v3_sessions_router)
app.include_router(v3_metrics_router, prefix="/v3")
app.include_router(v3_brain_router)
app.include_router(v3_runs_router)
app.include_router(v3_preflight_router)
app.include_router(v3_findings_grades_router)
app.include_router(v3_wallet_router)
app.include_router(v3_runs_cost_router)
app.include_router(v3_share_router)
app.include_router(v3_templates_router)
app.include_router(v3_replay_router)
app.include_router(v3_evidence_router)
app.include_router(v3_health_router)
app.include_router(v3_working_memory_router)
app.include_router(v3_investigation_templates_router)
app.include_router(v3_absorption_router)
app.include_router(v3_modes_router)
