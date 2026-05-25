"""Tests for the pre-run missing-key gate logic (Phase 2, #75).

Covers app/pipeline/catalogs/technique_keys.py: the technique→key map, strategy
technique enumeration (precise, preferred-tactic-only), and the missing-key
resolver. resolve_api_key is monkeypatched so no real vault/DB is needed.
"""
from __future__ import annotations

import pytest

from app.pipeline.catalogs.technique_keys import (
    TECHNIQUE_KEY_META,
    _enumerate_technique_ids,
    check_missing_keys_for_strategy,
    node_missing_key,
)


def test_key_meta_shape_no_value_field():
    """Each entry exposes only key NAME + public setup info — never a value."""
    for tid, meta in TECHNIQUE_KEY_META.items():
        assert set(meta) == {"key_name", "display_name", "setup_url", "setup_instructions"}, tid
        assert "value" not in meta
        assert meta["key_name"] and meta["key_name"].islower()


def test_enumerate_real_estate_leads_includes_enrichment_techniques():
    tids = _enumerate_technique_ids("real_estate_leads")
    # leads_enrich_gather is the gather phase's preferred tactic
    for expected in ("hunter_email_search", "apollo_contact", "whois_owner",
                     "pipl_people", "apify_listings_search"):
        assert expected in tids, f"{expected} missing from enumeration: {sorted(tids)}"


def test_enumerate_unknown_strategy_is_empty():
    assert _enumerate_technique_ids("no_such_strategy_xyz") == set()


def test_missing_keys_when_none_configured(monkeypatch):
    """All five key-requiring techniques surface (de-duped by key_name) when the
    vault has nothing."""
    monkeypatch.setattr("app.lib.api_keys.resolve_api_key", lambda k, **kw: None)
    missing = check_missing_keys_for_strategy("real_estate_leads", user_id="u1", org_id=None)
    key_names = {m["key_name"] for m in missing}
    assert key_names == {"hunter_io_api_key", "apollo_api_key", "whoisxml_api_key",
                         "pipl_api_key", "apify_api_token"}
    # de-dup: one descriptor per key_name
    assert len(missing) == len(key_names)
    # never leaks a value
    for m in missing:
        assert "value" not in m


def test_no_missing_when_all_keys_present(monkeypatch):
    monkeypatch.setattr("app.lib.api_keys.resolve_api_key", lambda k, **kw: "configured")
    assert check_missing_keys_for_strategy("real_estate_leads", user_id="u1", org_id="o1") == []


def test_free_techniques_never_surface(monkeypatch):
    """web_search / opencorporates_owner / phone_osint need no key and must never
    appear in the gate even when nothing is configured."""
    monkeypatch.setattr("app.lib.api_keys.resolve_api_key", lambda k, **kw: None)
    missing = check_missing_keys_for_strategy("real_estate_leads", user_id="u1", org_id=None)
    surfaced_techniques = {m["technique_id"] for m in missing}
    for free in ("web_search", "opencorporates_owner", "phone_osint"):
        assert free not in surfaced_techniques


def test_generic_strategy_does_not_surface_enrichment_keys(monkeypatch):
    """Precision guard: a strategy that does not prefer leads_enrich_gather must
    NOT prompt for enrichment keys, even though that tactic is gather-compatible."""
    monkeypatch.setattr("app.lib.api_keys.resolve_api_key", lambda k, **kw: None)
    missing = check_missing_keys_for_strategy("generic_search", user_id="u1", org_id=None)
    key_names = {m["key_name"] for m in missing}
    assert "hunter_io_api_key" not in key_names
    assert "apollo_api_key" not in key_names


def test_resolve_failure_is_fail_open(monkeypatch):
    """A vault/DB error must NOT strand the run — treat as present (no gate)."""
    def boom(k, **kw):
        raise RuntimeError("db down")
    monkeypatch.setattr("app.lib.api_keys.resolve_api_key", boom)
    assert check_missing_keys_for_strategy("real_estate_leads", user_id="u1", org_id=None) == []


# ---------------------------------------------------------------------------
# node_missing_key — reactive mid-run gate (#76)
# ---------------------------------------------------------------------------


def test_node_missing_key_surfaces_when_absent(monkeypatch):
    monkeypatch.setattr("app.lib.api_keys.resolve_api_key", lambda k, **kw: None)
    desc = node_missing_key("hunter_io", user_id="u1", org_id=None)
    assert desc is not None
    assert desc["node_type"] == "hunter_io"
    assert desc["key_name"] == "hunter_io_api_key"
    assert "value" not in desc  # never a key value


def test_node_missing_key_none_when_present(monkeypatch):
    monkeypatch.setattr("app.lib.api_keys.resolve_api_key", lambda k, **kw: "configured")
    assert node_missing_key("apollo_zoominfo", user_id="u1", org_id="o1") is None


def test_node_missing_key_none_for_unmapped_node(monkeypatch):
    monkeypatch.setattr("app.lib.api_keys.resolve_api_key", lambda k, **kw: None)
    assert node_missing_key("web_search", user_id="u1", org_id=None) is None
    assert node_missing_key("totally_unknown_node", user_id="u1", org_id=None) is None


def test_node_missing_key_fail_open(monkeypatch):
    def boom(k, **kw):
        raise RuntimeError("db down")
    monkeypatch.setattr("app.lib.api_keys.resolve_api_key", boom)
    assert node_missing_key("hunter_io", user_id="u1", org_id=None) is None


def test_gate_event_emitted_and_deduped(monkeypatch):
    """_maybe_emit_missing_key_gate pushes one missing.key event per (run, key)."""
    import asyncio
    import app.routers.v3.nodes_api as na

    pushed: list[tuple[str, dict]] = []

    async def fake_push(user_id, event):
        pushed.append((user_id, event))

    monkeypatch.setattr(na, "push_event", fake_push)
    monkeypatch.setattr("app.lib.api_keys.resolve_api_key", lambda k, **kw: None)
    na._MISSING_KEY_GATE_SENT.clear()

    async def go():
        await na._maybe_emit_missing_key_gate("hunter_io", "run-xyz", "user-1", None)
        await na._maybe_emit_missing_key_gate("hunter_io", "run-xyz", "user-1", None)  # dup

    asyncio.run(go())

    assert len(pushed) == 1, "gate should be emitted once per (run_id, key_name)"
    user_id, event = pushed[0]
    assert user_id == "user-1"
    assert event["type"] == "missing.key"
    assert event["run_id"] == "run-xyz"
    assert event["key_name"] == "hunter_io_api_key"
    assert "value" not in event
