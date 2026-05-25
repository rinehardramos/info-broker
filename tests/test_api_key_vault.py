"""Tests for the scoped API-key vault (Phase 1).

Most tests run without a real DB by monkeypatching the DB fetch functions.
DB-integration tests are skipped when POSTGRES_HOST is not set.
"""
from __future__ import annotations

import os
import pytest


# ---------------------------------------------------------------------------
# secret_box tests
# ---------------------------------------------------------------------------


def test_encrypt_decrypt_roundtrip():
    """Fernet round-trip with the dev key."""
    from app.lib.secret_box import decrypt, encrypt

    plaintext = "super-secret-api-key-12345"
    token = encrypt(plaintext)
    assert isinstance(token, str)
    assert token != plaintext
    assert decrypt(token) == plaintext


def test_decrypt_invalid_token_raises():
    from app.lib.secret_box import decrypt

    with pytest.raises(ValueError, match="vault decrypt failed"):
        decrypt("not-a-valid-fernet-token")


def test_dev_key_warning_emitted(caplog):
    """Dev fallback MUST log a LOUD warning so it can't be silent in prod."""
    import app.lib.secret_box as sb

    # Reset warning flag so it fires again
    sb._warned_dev_key = False
    with caplog.at_level("WARNING", logger="app.lib.secret_box"):
        sb._get_fernet_key()
    assert any("VAULT_ENCRYPTION_KEY" in r.message for r in caplog.records)


def test_custom_vault_key_no_warning(monkeypatch, caplog):
    """When VAULT_ENCRYPTION_KEY is set, no dev-key warning should be emitted."""
    import app.lib.secret_box as sb
    from cryptography.fernet import Fernet

    real_key = Fernet.generate_key().decode()
    monkeypatch.setenv("VAULT_ENCRYPTION_KEY", real_key)
    sb._warned_dev_key = False
    with caplog.at_level("WARNING", logger="app.lib.secret_box"):
        sb._get_fernet_key()
    assert not any("VAULT_ENCRYPTION_KEY" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# api_keys resolution tests (no real DB)
# ---------------------------------------------------------------------------


def test_user_scope_wins(monkeypatch):
    """User-scoped vault entry resolves before org / global / env."""
    from app.lib.secret_box import encrypt

    encrypted = encrypt("user-key")
    monkeypatch.setattr(
        "app.routers.v3.db.fetch_one",
        lambda q, p: {"value_encrypted": encrypted} if "owner_id = %s::uuid" in q and "scope = %s" in q else None,
    )
    from app.lib.api_keys import resolve_api_key

    result = resolve_api_key("some_api_key", user_id="user-uuid", org_id="org-uuid")
    assert result == "user-key"


def test_org_scope_when_no_user_row(monkeypatch):
    """Falls through to org scope when no user-scoped row exists."""
    from app.lib.secret_box import encrypt

    encrypted = encrypt("org-key")

    call_count = {"n": 0}

    def fake_fetch(q, p):
        call_count["n"] += 1
        # First call: user-scoped → None; second call: org-scoped → row
        if call_count["n"] == 1:
            return None
        return {"value_encrypted": encrypted}

    monkeypatch.setattr("app.routers.v3.db.fetch_one", fake_fetch)
    from app.lib.api_keys import resolve_api_key

    result = resolve_api_key("some_api_key", user_id="user-uuid", org_id="org-uuid")
    assert result == "org-key"


def test_env_fallback(monkeypatch):
    """Falls through to env var when vault and core_settings have nothing."""
    monkeypatch.setattr("app.routers.v3.db.fetch_one", lambda q, p: None)
    monkeypatch.setenv("SOME_API_KEY", "env-value")
    from app.lib.api_keys import resolve_api_key

    result = resolve_api_key("some_api_key", user_id=None, org_id=None)
    assert result == "env-value"


def test_none_returned_when_nothing_configured(monkeypatch):
    """Returns None when key is not in vault, core_settings, or env."""
    monkeypatch.setattr("app.routers.v3.db.fetch_one", lambda q, p: None)
    from app.lib.api_keys import resolve_api_key

    result = resolve_api_key("no_such_key_xyz", user_id=None, org_id=None)
    assert result is None


def test_mcp_system_user_skips_user_vault(monkeypatch):
    """mcp-system pseudo-user should not attempt a user-scoped vault lookup."""
    called = {"user_lookup": False}

    def fake_fetch(q, p):
        if "owner_id = %s::uuid" in q:
            called["user_lookup"] = True
        return None

    monkeypatch.setattr("app.routers.v3.db.fetch_one", fake_fetch)
    monkeypatch.setenv("SOME_API_KEY", "fallback")

    from app.lib.api_keys import resolve_api_key

    resolve_api_key("some_api_key", user_id="mcp-system", org_id=None)
    assert not called["user_lookup"], "mcp-system should not trigger user-vault lookup"


# ---------------------------------------------------------------------------
# RunContext org_id field test
# ---------------------------------------------------------------------------


def test_run_context_org_id_field():
    """RunContext must carry org_id; defaults to None."""
    from app.pipeline.nodes.base import RunContext

    ctx = RunContext(user_id="u1", run_id="r1", node_id="n1")
    assert ctx.org_id is None

    ctx2 = RunContext(user_id="u1", run_id="r1", node_id="n1", org_id="org-123")
    assert ctx2.org_id == "org-123"


# ---------------------------------------------------------------------------
# nodes_api header threading test
# ---------------------------------------------------------------------------


def _make_nodes_test_app(monkeypatch, captured_ctx: dict):
    """Build a minimal FastAPI app that mounts the nodes_api router with a fake node."""
    from fastapi import FastAPI

    class FakeNode:
        node_type = "fake"
        display_name = "Fake"
        category = "source"
        config_schema = {}

        async def execute(self, config, inputs, context):
            captured_ctx["user_id"] = context.user_id
            captured_ctx["org_id"] = context.org_id
            return []

    monkeypatch.setattr("app.pipeline.nodes.NodeRegistry.get", lambda nt: FakeNode())
    monkeypatch.setattr("app.pipeline.nodes.NodeRegistry.auto_discover", lambda: None)

    # Patch async tracker + push_event with coroutine stubs
    async def _anoop(*a, **kw):
        return None

    monkeypatch.setattr("app.routers.v3.nodes_api.tracker.start_session", _anoop)
    monkeypatch.setattr("app.routers.v3.nodes_api.tracker.log_call_start", _anoop)
    monkeypatch.setattr("app.routers.v3.nodes_api.tracker.log_call_complete", _anoop)
    monkeypatch.setattr("app.routers.v3.nodes_api.push_event", _anoop)
    monkeypatch.setenv("INFO_BROKER_API_KEY", "test-key")

    from app.routers.v3.nodes_api import router as nodes_router

    mini_app = FastAPI()
    mini_app.include_router(nodes_router)
    return mini_app


def test_execute_node_populates_run_context_from_headers(monkeypatch):
    """execute_node must pass X-Caller-User-Id / X-Caller-Org-Id to RunContext."""
    from fastapi.testclient import TestClient

    captured_ctx: dict = {}
    mini_app = _make_nodes_test_app(monkeypatch, captured_ctx)

    client = TestClient(mini_app)
    resp = client.post(
        "/v3/nodes/fake/execute",
        json={},
        headers={
            "X-API-Key": "test-key",
            "X-Caller-User-Id": "test-user-uuid",
            "X-Caller-Org-Id": "test-org-uuid",
        },
    )
    assert resp.status_code == 200, resp.text
    assert captured_ctx.get("user_id") == "test-user-uuid"
    assert captured_ctx.get("org_id") == "test-org-uuid"


def test_execute_node_defaults_to_mcp_system_without_headers(monkeypatch):
    """execute_node defaults user_id to 'mcp-system' when no headers provided."""
    from fastapi.testclient import TestClient

    captured_ctx: dict = {}
    mini_app = _make_nodes_test_app(monkeypatch, captured_ctx)

    client = TestClient(mini_app)
    resp = client.post(
        "/v3/nodes/fake/execute",
        json={},
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 200, resp.text
    assert captured_ctx.get("user_id") == "mcp-system"
    assert captured_ctx.get("org_id") is None


# ---------------------------------------------------------------------------
# ApiKeyEntry response model — presence only (no value field)
# ---------------------------------------------------------------------------


def test_get_api_keys_never_returns_value():
    """ApiKeyEntry model MUST NOT have a 'value' or 'value_encrypted' field."""
    from app.routers.v3.settings import ApiKeyEntry

    fields = set(ApiKeyEntry.model_fields.keys())
    assert "value" not in fields, "ApiKeyEntry must not expose value"
    assert "value_encrypted" not in fields, "ApiKeyEntry must not expose value_encrypted"
    assert "key_name" in fields
    assert "scope" in fields


# ---------------------------------------------------------------------------
# DB integration tests (skipped without POSTGRES_HOST)
# ---------------------------------------------------------------------------

_HAS_DB = bool(os.getenv("POSTGRES_HOST"))


@pytest.mark.skipif(not _HAS_DB, reason="requires POSTGRES_HOST")
def test_vault_upsert_and_resolve():
    """Round-trip: store a key via execute(), resolve via resolve_api_key()."""
    from app.routers.v3.db import execute, fetch_one
    from app.lib.secret_box import encrypt
    from app.lib.api_keys import resolve_api_key

    import uuid
    test_user = str(uuid.uuid4())
    key_name = f"test_key_{test_user[:8]}"
    plaintext = "integration-test-value"

    execute(
        """INSERT INTO api_key_vault (key_name, scope, owner_id, value_encrypted)
           VALUES (%s, 'user', %s::uuid, %s)
           ON CONFLICT (key_name, scope, owner_id) DO UPDATE
           SET value_encrypted = EXCLUDED.value_encrypted""",
        (key_name, test_user, encrypt(plaintext)),
    )

    resolved = resolve_api_key(key_name, user_id=test_user, org_id=None)
    assert resolved == plaintext

    # Cleanup
    execute(
        "DELETE FROM api_key_vault WHERE key_name = %s AND owner_id = %s::uuid",
        (key_name, test_user),
    )


@pytest.mark.skipif(not _HAS_DB, reason="requires POSTGRES_HOST")
def test_global_reupsert_updates_not_duplicates():
    """Re-upserting a GLOBAL key (owner_id IS NULL) must UPDATE the existing row,
    not insert a duplicate. Requires UNIQUE NULLS NOT DISTINCT — otherwise NULL≠NULL
    means ON CONFLICT never fires and global key rotation silently fails."""
    from app.routers.v3.db import execute, fetch_all
    from app.lib.secret_box import encrypt
    from app.lib.api_keys import resolve_api_key

    import uuid
    key_name = f"test_global_{uuid.uuid4().hex[:8]}"

    def _upsert(value: str) -> None:
        execute(
            """INSERT INTO api_key_vault (key_name, scope, owner_id, value_encrypted)
               VALUES (%s, 'global', NULL, %s)
               ON CONFLICT (key_name, scope, owner_id) DO UPDATE
               SET value_encrypted = EXCLUDED.value_encrypted""",
            (key_name, encrypt(value)),
        )

    try:
        _upsert("first-value")
        _upsert("rotated-value")  # second upsert must UPDATE, not duplicate

        rows = fetch_all(
            "SELECT id FROM api_key_vault WHERE key_name = %s AND scope = 'global'",
            (key_name,),
        )
        assert len(rows) == 1, f"expected 1 global row after re-upsert, got {len(rows)}"
        assert resolve_api_key(key_name, user_id=None, org_id=None) == "rotated-value"
    finally:
        execute(
            "DELETE FROM api_key_vault WHERE key_name = %s AND scope = 'global'",
            (key_name,),
        )


@pytest.mark.skipif(not _HAS_DB, reason="requires POSTGRES_HOST")
def test_vault_migration_creates_table():
    """run_migrations() must create api_key_vault with the correct columns."""
    from app.routers.v3.db import fetch_one

    row = fetch_one(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = 'api_key_vault' AND column_name = 'value_encrypted'
        """,
        (),
    )
    assert row is not None, "api_key_vault.value_encrypted column not found"


# ---------------------------------------------------------------------------
# resolve_site_credential — authenticated-session credential vault (#item-4)
# ---------------------------------------------------------------------------

def test_resolve_site_credential_roundtrip(monkeypatch):
    import json
    from app.lib.secret_box import encrypt
    enc = encrypt(json.dumps({"username": "alice", "password": "s3cret"}))
    # user-scoped row matches (scope = %s present in _vault_fetch query)
    monkeypatch.setattr(
        "app.routers.v3.db.fetch_one",
        lambda q, p: {"value_encrypted": enc} if "scope = %s" in q else None,
    )
    from app.lib.api_keys import resolve_site_credential
    cred = resolve_site_credential("FSBO.com", user_id="uid", org_id=None)
    assert cred == {"username": "alice", "password": "s3cret"}


def test_resolve_site_credential_none_when_absent(monkeypatch):
    monkeypatch.setattr("app.routers.v3.db.fetch_one", lambda q, p: None)
    from app.lib.api_keys import resolve_site_credential
    assert resolve_site_credential("nope.com", user_id="uid", org_id=None) is None


def test_resolve_site_credential_skips_mcp_system(monkeypatch):
    called = {"n": 0}
    def fake(q, p):
        called["n"] += 1
        return None
    monkeypatch.setattr("app.routers.v3.db.fetch_one", fake)
    from app.lib.api_keys import resolve_site_credential
    # mcp-system pseudo-user + no org → no lookup attempted
    assert resolve_site_credential("x.com", user_id="mcp-system", org_id=None) is None
    assert called["n"] == 0
