"""ensure_claude_credentials priority chain + source classification.

The function now also classifies HOW it found the credentials so admin
logs distinguish auto-refreshing bind-mount paths from one-shot copies.
This matters because the named-volume `preseeded` path is a
COPY — once an expired file is in the volume, it stays expired until
manually replaced. The bind-mount path is LIVE — the host CLI refreshes
the file and the container picks it up on next spawn.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest import mock

import pytest

import app.claude_auth_setup as auth_setup
from app.claude_auth_setup import (
    ensure_claude_credentials,
    classify_credentials_source,
)


def _write_creds(path: Path, expires_in_seconds: int = 24 * 3600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    now_ms = int(time.time() * 1000)
    path.write_text(json.dumps({
        "claudeAiOauth": {
            "accessToken": "sk-ant-oat01-test",
            "refreshToken": "sk-ant-oat01-test-refresh",
            "expiresAt": now_ms + expires_in_seconds * 1000,
            "scopes": ["user:inference"],
            "subscriptionType": "max",
        }
    }))
    path.chmod(0o600)


# ---------------------------------------------------------------------------
# classify_credentials_source — pure function, no side effects
# ---------------------------------------------------------------------------


class TestClassifyCredentialsSource:
    def test_api_key_env_var(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-api03-xx"}, clear=False):
            assert classify_credentials_source() == "api_key_env"

    def test_oauth_refresh_token_env_var(self):
        env = {"CLAUDE_CODE_OAUTH_REFRESH_TOKEN": "tok"}
        # Remove other auth vars that would take precedence
        with mock.patch.dict(os.environ, env, clear=True):
            assert classify_credentials_source() == "oauth_env"

    def test_bind_mount_when_creds_dir_is_a_host_bind(self, tmp_path, monkeypatch):
        """A bind-mounted /root/.claude is detected by checking whether the
        directory's inode lives on a different filesystem than /root."""
        # Skip if we can't simulate inode-on-different-fs cheaply.
        # Best-effort: the function should at least return *some* preseeded
        # variant; we differentiate by checking st_dev between dir and parent
        # in the impl. Mock that.
        fake = tmp_path / "creds.json"
        _write_creds(fake)
        with mock.patch.object(auth_setup, "_BRAIN_CREDS_DIR", tmp_path), \
             mock.patch.object(auth_setup, "_BRAIN_CREDS_FILE", fake), \
             mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(auth_setup, "_is_bind_mounted_dir", return_value=True):
            assert classify_credentials_source() == "host_bind_mount"

    def test_named_volume_preseeded_when_not_bind_mounted(self, tmp_path):
        fake = tmp_path / "creds.json"
        _write_creds(fake)
        with mock.patch.object(auth_setup, "_BRAIN_CREDS_DIR", tmp_path), \
             mock.patch.object(auth_setup, "_BRAIN_CREDS_FILE", fake), \
             mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(auth_setup, "_is_bind_mounted_dir", return_value=False):
            assert classify_credentials_source() == "named_volume_preseeded"

    def test_none_when_no_creds(self, tmp_path):
        with mock.patch.object(auth_setup, "_BRAIN_CREDS_DIR", tmp_path), \
             mock.patch.object(auth_setup, "_BRAIN_CREDS_FILE", tmp_path / "missing.json"), \
             mock.patch.object(auth_setup, "_HOST_CREDS_FILE", tmp_path / "also-missing"), \
             mock.patch.dict(os.environ, {}, clear=True):
            assert classify_credentials_source() == "none"


# ---------------------------------------------------------------------------
# ensure_claude_credentials still returns the legacy string identifier
# (used by callers; don't break their string-match)
# ---------------------------------------------------------------------------


class TestEnsureCredsBackwardsCompat:
    def test_api_key_returns_api_key(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-api03-xx"}, clear=False):
            assert ensure_claude_credentials() == "api_key"

    def test_returns_preseeded_when_volume_has_creds(self, tmp_path):
        fake = tmp_path / "creds.json"
        _write_creds(fake)
        with mock.patch.object(auth_setup, "_BRAIN_CREDS_DIR", tmp_path), \
             mock.patch.object(auth_setup, "_BRAIN_CREDS_FILE", fake), \
             mock.patch.dict(os.environ, {}, clear=True):
            assert ensure_claude_credentials() == "preseeded"
