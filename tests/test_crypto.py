"""Unit tests for app.crypto — encryption/decryption of Settings secrets."""
from __future__ import annotations

import importlib
import os

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_crypto():
    """Re-import app.crypto so _get_key() re-reads the (patched) env var."""
    import app.crypto
    importlib.reload(app.crypto)
    return app.crypto


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_roundtrip(monkeypatch):
    """encrypt_value followed by decrypt_value returns the original plaintext."""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", key)
    crypto = _reload_crypto()

    plaintext = "super-secret-api-key-12345"
    ciphertext = crypto.encrypt_value(plaintext)

    assert ciphertext.startswith("enc:")
    assert ciphertext != plaintext
    assert crypto.decrypt_value(ciphertext) == plaintext


def test_decrypt_legacy_plaintext(monkeypatch):
    """A value without the 'enc:' prefix is returned unchanged (legacy support)."""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", key)
    crypto = _reload_crypto()

    legacy = "plain-old-value"
    assert crypto.decrypt_value(legacy) == legacy


def test_no_key_encrypt_passthrough(monkeypatch):
    """When no key is configured, encrypt_value returns the plaintext unchanged."""
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)
    crypto = _reload_crypto()

    plaintext = "my-secret"
    assert crypto.encrypt_value(plaintext) == plaintext


def test_decrypt_encrypted_without_key_returns_as_is(monkeypatch):
    """An 'enc:' prefixed value with no key configured is returned as-is."""
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)
    crypto = _reload_crypto()

    # Simulate a value that was encrypted earlier but key is now missing
    stored = "enc:gAAAAABsome_opaque_ciphertext"
    assert crypto.decrypt_value(stored) == stored
