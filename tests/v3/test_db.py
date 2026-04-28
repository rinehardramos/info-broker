import os
import pytest
from app.routers.v3.db import run_migrations, get_conn

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_HOST"),
    reason="Postgres not available in CI without env vars"
)


def test_run_migrations_creates_tables():
    run_migrations()
    with get_conn() as conn:
        with conn.cursor() as cur:
            for table in ["ui_users", "ui_sessions", "ui_preferences",
                          "plugin_configs", "feed_monitors", "core_settings",
                          "v3_jobs"]:
                cur.execute(
                    "SELECT to_regclass(%s)",
                    (f"public.{table}",)
                )
                result = cur.fetchone()[0]
                assert result is not None, f"Table {table} was not created"
