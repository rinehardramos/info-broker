"""
Smoke test: app imports + monitoring adapters register without crashing.
Requires real MONITORING_REDIS_URL + CLICKHOUSE_URL in the environment.
Skips if not set (CI without monitoring services).
"""
import os
import pytest

requires_monitoring = pytest.mark.skipif(
    not (os.getenv("MONITORING_REDIS_URL") and os.getenv("CLICKHOUSE_URL")),
    reason="MONITORING_REDIS_URL + CLICKHOUSE_URL not set",
)


@requires_monitoring
def test_app_imports_without_error():
    """app.main is importable with monitoring env vars present."""
    import importlib
    mod = importlib.import_module("app.main")
    assert hasattr(mod, "app")


@requires_monitoring
@pytest.mark.anyio
async def test_health_endpoint_returns_ok():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/healthz")
    assert r.status_code == 200
