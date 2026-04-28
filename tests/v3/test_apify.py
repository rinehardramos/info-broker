import os
import pytest
from fastapi.testclient import TestClient
from app.main import app

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_HOST"),
    reason="Requires Postgres"
)

client = TestClient(app)


def _register_and_login(username: str, pw: str) -> str:
    from passlib.context import CryptContext
    from app.routers.v3.db import execute
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    execute(
        "INSERT INTO ui_users (username, password_hash) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (username, ctx.hash(pw)),
    )
    creds = {"username": username, "password": pw}
    resp = client.post("/v3/auth/login", json=creds)
    return resp.json()["access_token"]


def test_apify_tables_exist():
    from app.routers.v3.db import fetch_one
    r1 = fetch_one(
        "SELECT table_name FROM information_schema.tables WHERE table_name = 'apify_run_configs'"
    )
    assert r1 is not None, "apify_run_configs table missing"
    r2 = fetch_one(
        "SELECT table_name FROM information_schema.tables WHERE table_name = 'apify_runs'"
    )
    assert r2 is not None, "apify_runs table missing"
