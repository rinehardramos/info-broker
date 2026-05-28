"""Test that the llm_pricing table is created by the migration."""
import os
import uuid
import psycopg2
import psycopg2.extras
import pytest


@pytest.fixture
def pg_conn():
    """Real Postgres connection using the same env vars as the app."""
    database_url = os.getenv("DATABASE_URL")
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
    conn.autocommit = False
    yield conn
    conn.rollback()
    conn.close()


def test_llm_pricing_table_exists(pg_conn):
    """After running v3_migrate(), the llm_pricing table must exist."""
    from app.routers.v3.db import run_migrations
    run_migrations()

    cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'llm_pricing'
        ORDER BY ordinal_position
        """
    )
    cols = {row["column_name"] for row in cur.fetchall()}
    expected = {
        "id", "model_id", "provider",
        "input_usd_per_1m", "output_usd_per_1m",
        "cache_creation_usd_per_1m", "cache_read_usd_per_1m",
        "effective_from", "updated_by", "updated_at", "notes",
    }
    assert expected.issubset(cols), f"Missing columns: {expected - cols}"


def test_llm_pricing_index_exists(pg_conn):
    cur = pg_conn.cursor()
    cur.execute(
        """
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'llm_pricing'
          AND indexname = 'idx_llm_pricing_model_eff'
        """
    )
    assert cur.fetchone() is not None, "idx_llm_pricing_model_eff index missing"


def test_llm_pricing_insert_and_query(pg_conn):
    """Can insert a pricing row and retrieve it."""
    from app.routers.v3.db import run_migrations
    run_migrations()

    row_id = str(uuid.uuid4())
    cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        INSERT INTO llm_pricing
            (id, model_id, provider, input_usd_per_1m, output_usd_per_1m)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, model_id
        """,
        (row_id, "claude-sonnet-4-6", "anthropic", "3.0000", "15.0000"),
    )
    row = cur.fetchone()
    assert row["id"] == row_id
    assert row["model_id"] == "claude-sonnet-4-6"
    pg_conn.rollback()
