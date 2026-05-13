from __future__ import annotations

import hashlib
import hmac
import time

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient


def _sign(secret: str, ts: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), f"{ts}.".encode("utf-8") + body, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


def _build_app(monkeypatch, secret: str) -> TestClient:
    import importlib
    monkeypatch.setenv("MCP_SIGNING_SECRET", secret)
    import app.routers.v3.mcp_auth as mcp_auth
    importlib.reload(mcp_auth)

    app = FastAPI()

    @app.post("/v3/mcp/echo", dependencies=[Depends(mcp_auth.verify_mcp_signature)])
    async def echo(payload: dict) -> dict:
        return payload

    return TestClient(app)


def test_valid_signature_accepted(monkeypatch):
    client = _build_app(monkeypatch, "test-secret")
    ts = str(int(time.time()))
    body = b'{"hello":"world"}'
    r = client.post(
        "/v3/mcp/echo",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-MCP-Timestamp": ts,
            "X-MCP-Signature": _sign("test-secret", ts, body),
        },
    )
    assert r.status_code == 200, r.text


def test_missing_signature_401(monkeypatch):
    client = _build_app(monkeypatch, "test-secret")
    r = client.post("/v3/mcp/echo", json={"hello": "world"})
    assert r.status_code == 401


def test_stale_timestamp_401(monkeypatch):
    client = _build_app(monkeypatch, "test-secret")
    ts = str(int(time.time()) - 400)
    body = b'{"hello":"world"}'
    r = client.post(
        "/v3/mcp/echo",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-MCP-Timestamp": ts,
            "X-MCP-Signature": _sign("test-secret", ts, body),
        },
    )
    assert r.status_code == 401


def test_tampered_body_401(monkeypatch):
    client = _build_app(monkeypatch, "test-secret")
    ts = str(int(time.time()))
    r = client.post(
        "/v3/mcp/echo",
        content=b'{"hello":"tampered"}',
        headers={
            "Content-Type": "application/json",
            "X-MCP-Timestamp": ts,
            "X-MCP-Signature": _sign("test-secret", ts, b'{"hello":"original"}'),
        },
    )
    assert r.status_code == 401


def test_no_secret_skips_check(monkeypatch):
    client = _build_app(monkeypatch, "")
    r = client.post("/v3/mcp/echo", json={"hello": "world"})
    assert r.status_code == 200
