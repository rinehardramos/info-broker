from __future__ import annotations
import pytest


def test_sanitize_strips_script_tag():
    from app.security import sanitize_user_input
    out = sanitize_user_input("<script>x</script>hi")
    assert "<script>" not in out
    assert "</script>" not in out


def test_sanitize_strips_img_onerror():
    from app.security import sanitize_user_input
    out = sanitize_user_input("<img src=x onerror=alert(1)>foo")
    assert "<img" not in out
    assert "onerror" not in out
    assert "foo" in out


def test_sanitize_truncates_to_max_length():
    from app.security import sanitize_user_input
    out = sanitize_user_input("a" * 9000, max_length=4000)
    assert len(out) == 4000


def test_sanitize_handles_none():
    from app.security import sanitize_user_input
    assert sanitize_user_input(None) == ""


def test_sanitize_idempotent():
    from app.security import sanitize_user_input
    once = sanitize_user_input("<b>hello</b>")
    twice = sanitize_user_input(once)
    assert once == twice


def test_agent_message_in_strips_html():
    from app.routers.v3.models import AgentMessageIn
    m = AgentMessageIn(message="<img src=x onerror=alert(1)>hello")
    assert "<img" not in m.message
    assert "hello" in m.message


def test_agent_message_in_max_length_8000():
    from pydantic import ValidationError
    from app.routers.v3.models import AgentMessageIn
    with pytest.raises(ValidationError):
        AgentMessageIn(message="x" * 8001)


def test_pipeline_in_strips_html():
    from app.routers.v3.models import PipelineIn
    p = PipelineIn(name="<script>alert(1)</script>My Pipeline")
    assert "<script>" not in p.name
    assert "My Pipeline" in p.name


def test_pipeline_in_name_max_length():
    from pydantic import ValidationError
    from app.routers.v3.models import PipelineIn
    with pytest.raises(ValidationError):
        PipelineIn(name="x" * 256)


# ---------------------------------------------------------------------------
# safe_fetch_url — browser impersonation path (curl_cffi) preserves SSRF guards
# ---------------------------------------------------------------------------
import builtins  # noqa: E402
import pytest  # noqa: E402
import security as _sec  # noqa: E402
from security import safe_fetch_url, UnsafeURLError  # noqa: E402


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin",
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata
    "http://localhost:8000/internal",
])
def test_impersonate_does_not_bypass_ssrf_guard(url):
    """The SSRF host check runs BEFORE the impersonate branch — internal targets
    must be rejected even when impersonate is requested."""
    with pytest.raises(UnsafeURLError):
        safe_fetch_url(url, impersonate="chrome")


def test_impersonate_rejects_non_http_scheme():
    with pytest.raises(UnsafeURLError):
        safe_fetch_url("file:///etc/passwd", impersonate="chrome")


def test_fetch_impersonated_falls_back_when_curl_cffi_missing(monkeypatch):
    """If curl_cffi isn't installed, _fetch_impersonated returns None so the
    caller transparently uses the plain requests path (no crash)."""
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "curl_cffi" or name.startswith("curl_cffi."):
            raise ImportError("simulated: curl_cffi not installed")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    out = _sec._fetch_impersonated(
        "https://example.com",
        timeout=5, max_bytes=1000, headers=None,
        allowed_content_types=None, impersonate="chrome", host="example.com",
    )
    assert out is None
