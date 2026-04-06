"""Shared FastAPI dependencies: API-key auth and DB connection helpers."""
from __future__ import annotations

import os

from fastapi import Header, HTTPException, status

API_KEY_ENV = "INFO_BROKER_API_KEY"


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> str:
    """Header-based authentication: rejects requests missing or with wrong key.

    The expected key is read from the ``INFO_BROKER_API_KEY`` env var at
    request time so tests can monkey-patch it.
    """
    expected = os.getenv(API_KEY_ENV)
    if not expected:
        # Fail closed: refuse to serve protected routes if the server has
        # no key configured. This avoids accidentally exposing data when
        # someone forgets to set the env var.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="server missing INFO_BROKER_API_KEY",
        )
    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-API-Key",
        )
    return x_api_key


def get_db_conn():
    """Yield a psycopg2 connection, closing it on request completion."""
    import psycopg2

    conn = psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", "info_broker"),
        user=os.getenv("POSTGRES_USER", "user"),
        password=os.getenv("POSTGRES_PASSWORD", "password"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
    )
    try:
        yield conn
    finally:
        conn.close()
