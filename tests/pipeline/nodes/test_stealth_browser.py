"""Unit tests for the stealth_browser node (Tier 2).

Pure — no real browser launched. The SSRF guard + URL handling + early-exit paths
are tested directly; the live render is validated separately against the stack.
"""
from __future__ import annotations

import asyncio

import pytest

from app.pipeline.nodes.base import RunContext
from app.pipeline.nodes.stealth_browser import (
    StealthBrowserNode,
    _collect_urls,
    _html_to_text,
    _url_is_safe,
)


def _ctx() -> RunContext:
    return RunContext(user_id="u1", run_id="r1", node_id="n1")


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin",
    "http://169.254.169.254/latest/meta-data/",
    "http://localhost/internal",
    "file:///etc/passwd",
    "ftp://example.com/x",
    "not-a-url",
])
def test_url_is_safe_rejects_internal_and_bad_schemes(url):
    assert _url_is_safe(url) is False


def test_url_is_safe_accepts_public_https():
    assert _url_is_safe("https://www.zillow.com/chicago-il/fsbo/") is True


def test_collect_urls_parses_forms_and_caps():
    # JSON array
    assert _collect_urls({"urls": '["https://a.com", "https://b.com"]'}, []) == ["https://a.com", "https://b.com"]
    # bare URL
    assert _collect_urls({"urls": "https://a.com"}, []) == ["https://a.com"]
    # comma/space separated
    assert _collect_urls({"urls": "https://a.com, https://b.com"}, []) == ["https://a.com", "https://b.com"]
    # inputs contribute urls
    got = _collect_urls({}, [{"url": "https://c.com"}])
    assert got == ["https://c.com"]
    # de-dup + cap at 12
    many = [f"https://x{i}.com" for i in range(20)]
    capped = _collect_urls({"urls": many}, [])
    assert len(capped) == 12


def test_html_to_text_strips_tags():
    html = "<html><body><script>x=1</script><main>Agent: Jane Doe (312) 555-1212</main></body></html>"
    text = _html_to_text(html)
    assert "Jane Doe" in text and "312" in text and "x=1" not in text


def test_execute_no_urls_returns_error():
    node = StealthBrowserNode()
    out = asyncio.run(node.execute({}, [], _ctx()))
    assert out and out[0].get("error")


def test_execute_only_unsafe_urls_returns_error_without_render(monkeypatch):
    node = StealthBrowserNode()
    # If render were called it would try to launch Chromium — assert it is NOT.
    import app.pipeline.nodes.stealth_browser as sb

    async def _boom(*a, **k):
        raise AssertionError("render must not run for unsafe-only URLs")
    monkeypatch.setattr(sb, "_render_pages", _boom)

    out = asyncio.run(node.execute({"urls": "http://127.0.0.1/x"}, [], _ctx()))
    assert out and "No safe" in out[0].get("error", "")


def test_execute_filters_to_safe_urls_before_render(monkeypatch):
    node = StealthBrowserNode()
    import app.pipeline.nodes.stealth_browser as sb
    captured = {}

    async def _fake_render(urls, *, wait_s, timeout, login=None):
        captured["urls"] = urls
        return [{"url": u, "content": "ok", "source_class": "live_search"} for u in urls]
    monkeypatch.setattr(sb, "_render_pages", _fake_render)

    out = asyncio.run(node.execute(
        {"urls": ["https://www.zillow.com/x", "http://127.0.0.1/x"]}, [], _ctx()
    ))
    # internal URL filtered out; only the public one reaches render
    assert captured["urls"] == ["https://www.zillow.com/x"]
    assert out[0]["content"] == "ok"


# ---------------------------------------------------------------------------
# _build_login — authenticated-session credential resolution (#item-4)
# ---------------------------------------------------------------------------

def test_build_login_none_without_site_or_login_url():
    assert StealthBrowserNode._build_login({}, _ctx()) is None
    assert StealthBrowserNode._build_login({"login_url": "https://x.com/login"}, _ctx()) is None
    assert StealthBrowserNode._build_login({"site": "x.com"}, _ctx()) is None


def test_build_login_resolves_credential(monkeypatch):
    monkeypatch.setattr("app.lib.api_keys.resolve_site_credential",
                        lambda site, **kw: {"username": "u", "password": "p"})
    login = StealthBrowserNode._build_login(
        {"login_url": "https://fsbo.com/login", "site": "fsbo.com"}, _ctx())
    assert login is not None
    assert login["url"] == "https://fsbo.com/login"
    assert login["username"] == "u" and login["password"] == "p"


def test_build_login_rejects_internal_login_url(monkeypatch):
    monkeypatch.setattr("app.lib.api_keys.resolve_site_credential",
                        lambda site, **kw: {"username": "u", "password": "p"})
    # SSRF check runs before credential use
    assert StealthBrowserNode._build_login(
        {"login_url": "http://127.0.0.1/login", "site": "x"}, _ctx()) is None


def test_build_login_none_when_no_stored_credential(monkeypatch):
    monkeypatch.setattr("app.lib.api_keys.resolve_site_credential", lambda site, **kw: None)
    assert StealthBrowserNode._build_login(
        {"login_url": "https://fsbo.com/login", "site": "fsbo.com"}, _ctx()) is None
