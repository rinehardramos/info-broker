"""Real-PG tests for PricingResolver."""
import asyncio
import os
import time
import uuid

import psycopg2
import psycopg2.extras
import pytest

from app.observability.pricing import PricingResolver, PriceSnapshot


@pytest.fixture
def pg_dsn() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url
    return (
        f"dbname={os.getenv('POSTGRES_DB', 'info_broker')} "
        f"user={os.getenv('POSTGRES_USER', 'user')} "
        f"password={os.getenv('POSTGRES_PASSWORD', 'password')} "
        f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')}"
    )


@pytest.fixture
def pg_conn(pg_dsn):
    conn = psycopg2.connect(pg_dsn)
    conn.autocommit = True
    yield conn
    conn.close()


def _insert_pricing(pg_conn, model_id, input_per_1m, output_per_1m,
                    provider="anthropic", pricing_id=None, effective_from=None):
    pid = pricing_id or str(uuid.uuid4())
    cur = pg_conn.cursor()
    if effective_from:
        cur.execute(
            "INSERT INTO llm_pricing (id, model_id, provider, input_usd_per_1m, output_usd_per_1m, effective_from) "
            "VALUES (%s, %s, %s, %s, %s, %s::timestamptz)",
            (pid, model_id, provider, input_per_1m, output_per_1m, effective_from),
        )
    else:
        cur.execute(
            "INSERT INTO llm_pricing (id, model_id, provider, input_usd_per_1m, output_usd_per_1m) "
            "VALUES (%s, %s, %s, %s, %s)",
            (pid, model_id, provider, input_per_1m, output_per_1m),
        )
    return pid


@pytest.mark.asyncio
async def test_get_returns_none_for_unknown_model(pg_dsn):
    resolver = PricingResolver(pg_dsn, ttl_seconds=60)
    result = await resolver.get("nonexistent-model-xyz-" + str(uuid.uuid4()))
    assert result is None


@pytest.mark.asyncio
async def test_get_returns_snapshot_for_known_model(pg_conn, pg_dsn):
    model_id = "test-model-" + str(uuid.uuid4())
    pid = _insert_pricing(pg_conn, model_id, "3.0000", "15.0000")
    try:
        resolver = PricingResolver(pg_dsn, ttl_seconds=60)
        snap = await resolver.get(model_id)
        assert snap is not None
        assert snap.pricing_id == uuid.UUID(pid)
        assert snap.model_id == model_id
        assert snap.provider == "anthropic"
        assert float(snap.input_usd_per_1m) == pytest.approx(3.0)
        assert float(snap.output_usd_per_1m) == pytest.approx(15.0)
    finally:
        pg_conn.cursor().execute("DELETE FROM llm_pricing WHERE id = %s", (pid,))


@pytest.mark.asyncio
async def test_get_returns_newest_row(pg_conn, pg_dsn):
    model_id = "test-model-multi-" + str(uuid.uuid4())
    old_pid = _insert_pricing(pg_conn, model_id, "1.0000", "5.0000",
                               effective_from="2020-01-01T00:00:00Z")
    new_pid = _insert_pricing(pg_conn, model_id, "3.0000", "15.0000",
                               effective_from="2025-01-01T00:00:00Z")
    future_pid = _insert_pricing(pg_conn, model_id, "99.0000", "99.0000",
                                  effective_from="2099-01-01T00:00:00Z")
    try:
        resolver = PricingResolver(pg_dsn, ttl_seconds=60)
        snap = await resolver.get(model_id)
        assert snap is not None
        assert snap.pricing_id == uuid.UUID(new_pid)
    finally:
        for pid in (old_pid, new_pid, future_pid):
            pg_conn.cursor().execute("DELETE FROM llm_pricing WHERE id = %s", (pid,))


@pytest.mark.asyncio
async def test_cache_ttl_expires(pg_conn, pg_dsn):
    model_id = "test-model-ttl-" + str(uuid.uuid4())
    old_pid = _insert_pricing(pg_conn, model_id, "1.0000", "5.0000")
    resolver = PricingResolver(pg_dsn, ttl_seconds=1)
    try:
        snap1 = await resolver.get(model_id)
        assert snap1 is not None and snap1.pricing_id == uuid.UUID(old_pid)
        new_pid = _insert_pricing(pg_conn, model_id, "9.0000", "99.0000")
        snap2 = await resolver.get(model_id)
        assert snap2 is not None and snap2.pricing_id == uuid.UUID(old_pid)
        await asyncio.sleep(1.1)
        snap3 = await resolver.get(model_id)
        assert snap3 is not None and snap3.pricing_id == uuid.UUID(new_pid)
    finally:
        pg_conn.cursor().execute("DELETE FROM llm_pricing WHERE model_id = %s", (model_id,))


@pytest.mark.asyncio
async def test_price_snapshot_cost_for_basic():
    pid = uuid.uuid4()
    snap = PriceSnapshot(
        pricing_id=pid, model_id="test", provider="anthropic",
        input_usd_per_1m=3.0, output_usd_per_1m=15.0,
        cache_creation_usd_per_1m=None, cache_read_usd_per_1m=None,
    )
    usage = {"input_tokens": 1_000_000, "output_tokens": 500_000,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    cost_usd, source, returned_pid = snap.cost_for(usage)
    assert source == "estimated"
    assert returned_pid == pid
    assert cost_usd == pytest.approx(10.50, rel=1e-4)


@pytest.mark.asyncio
async def test_price_snapshot_cost_for_with_cache():
    pid = uuid.uuid4()
    snap = PriceSnapshot(
        pricing_id=pid, model_id="test", provider="anthropic",
        input_usd_per_1m=3.0, output_usd_per_1m=15.0,
        cache_creation_usd_per_1m=3.75, cache_read_usd_per_1m=0.30,
    )
    usage = {"input_tokens": 0, "output_tokens": 0,
             "cache_creation_input_tokens": 1_000_000,
             "cache_read_input_tokens": 1_000_000}
    cost_usd, source, returned_pid = snap.cost_for(usage)
    assert source == "estimated"
    assert cost_usd == pytest.approx(4.05, rel=1e-4)
