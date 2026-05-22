"""500-response CORS-header echo (#97).

FastAPI's default uncaught-exception path returns a 500 without going
through CORSMiddleware, so the response has no Access-Control-Allow-*
headers. Browsers then report the failure as "CORS blocked" instead of
HTTP 500, hiding the real cause (which was the strategy-routing bug
that surfaced as #96, which we only diagnosed by stepping outside the
browser to curl).

This module pins the new exception handler's contract:
  - Uncaught exception → JSONResponse status=500, body="Internal Server Error"
  - When the request has a CORS-allowlisted Origin → response carries
    matching access-control-allow-origin
  - When the request Origin is not allowlisted → no CORS headers (don't
    leak the allowlist by echoing arbitrary origins)
  - Body never includes file paths or tracebacks
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import cors_safe_500_handler, _is_origin_allowed


# ---------------------------------------------------------------------------
# _is_origin_allowed — the matcher used by the handler
# ---------------------------------------------------------------------------


class TestOriginMatcher:
    def test_explicit_allowlist_match(self):
        assert _is_origin_allowed("https://infobroker.tech") is True
        assert _is_origin_allowed("http://localhost:5173") is True

    def test_regex_match_for_ngrok(self):
        assert _is_origin_allowed("https://abc123.ngrok-free.app") is True
        assert _is_origin_allowed("https://x.ngrok-free.dev") is True

    def test_not_in_allowlist(self):
        assert _is_origin_allowed("https://evil.example.com") is False
        assert _is_origin_allowed("") is False
        assert _is_origin_allowed(None) is False

    def test_partial_match_not_allowed(self):
        """A bare 'infobroker.tech' (no scheme) must not match a real origin."""
        assert _is_origin_allowed("infobroker.tech") is False
        # Subdomain that isn't explicitly listed
        assert _is_origin_allowed("https://evil.infobroker.tech") is False


# ---------------------------------------------------------------------------
# cors_safe_500_handler — registered as the Exception handler
# ---------------------------------------------------------------------------


def _make_test_app() -> FastAPI:
    """Tiny app with a route that intentionally throws."""
    app = FastAPI()
    # Register the exact same handler as the production app — it must
    # work standalone (no other middleware required).
    app.add_exception_handler(Exception, cors_safe_500_handler)

    @app.get("/boom")
    def boom():
        # Mirror the original masking case (UndefinedColumn) — non-HTTPException
        # so it hits the broadest handler.
        raise RuntimeError("simulated /v3/sources UndefinedColumn for #96")

    return app


class TestCorsSafe500Handler:
    def test_uncaught_exception_returns_500(self):
        client = TestClient(_make_test_app(), raise_server_exceptions=False)
        resp = client.get("/boom")
        assert resp.status_code == 500

    def test_500_body_is_generic_no_traceback_leak(self):
        client = TestClient(_make_test_app(), raise_server_exceptions=False)
        resp = client.get("/boom")
        # Body should not contain the raise message, file paths, or "Traceback"
        body = resp.text.lower()
        assert "traceback" not in body
        assert "undefinedcolumn" not in body
        assert "runtimeerror" not in body
        assert "/v3/sources" not in body
        # But it should clearly indicate it's a 500
        assert "internal server error" in body or "500" in body

    def test_500_echoes_cors_header_when_origin_allowlisted(self):
        client = TestClient(_make_test_app(), raise_server_exceptions=False)
        resp = client.get("/boom", headers={"Origin": "https://infobroker.tech"})
        assert resp.status_code == 500
        assert resp.headers.get("access-control-allow-origin") == "https://infobroker.tech"
        # Credentials flag mirrors what CORSMiddleware sets on the happy path
        assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_500_no_cors_header_for_unallowed_origin(self):
        """Don't leak the allowlist by echoing arbitrary origins."""
        client = TestClient(_make_test_app(), raise_server_exceptions=False)
        resp = client.get("/boom", headers={"Origin": "https://evil.example.com"})
        assert resp.status_code == 500
        assert "access-control-allow-origin" not in {k.lower() for k in resp.headers.keys()}

    def test_500_no_cors_header_when_no_origin_sent(self):
        """Non-CORS request (no Origin header) → no CORS headers in response."""
        client = TestClient(_make_test_app(), raise_server_exceptions=False)
        resp = client.get("/boom")
        assert resp.status_code == 500
        assert "access-control-allow-origin" not in {k.lower() for k in resp.headers.keys()}

    def test_500_echoes_ngrok_via_regex(self):
        client = TestClient(_make_test_app(), raise_server_exceptions=False)
        resp = client.get("/boom", headers={"Origin": "https://demo123.ngrok-free.app"})
        assert resp.status_code == 500
        assert resp.headers.get("access-control-allow-origin") == "https://demo123.ngrok-free.app"
