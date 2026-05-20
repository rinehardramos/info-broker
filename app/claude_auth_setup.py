"""
Platform-portable Claude Code credential setup.

Resolves Claude Code authentication in this priority:
  1. ANTHROPIC_API_KEY env var (CI / API-key mode)
  2. CLAUDE_CODE_OAUTH_REFRESH_TOKEN env var (cloud worker)
  3. Mounted host credentials at /root/.config/anthropic/ (Linux/WSL native;
     populated by `claude auth login` on the host)
  4. Pre-seeded volume at /root/.claude/.credentials.json (legacy path,
     populated by earlier setup-token flow or macOS keychain extraction)

Called once at module load. Idempotent: if creds are already in place,
no-op. If host creds are mounted, copies them into the writable
/root/.claude/ volume so Claude Code can refresh OAuth tokens in place.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

_HOST_CREDS_DIR = Path("/root/.config/anthropic")
_HOST_CREDS_FILE = _HOST_CREDS_DIR / "credentials.json"
_BRAIN_CREDS_DIR = Path("/root/.claude")
_BRAIN_CREDS_FILE = _BRAIN_CREDS_DIR / ".credentials.json"


def ensure_claude_credentials() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "api_key"

    if os.environ.get("CLAUDE_CODE_OAUTH_REFRESH_TOKEN"):
        return "oauth_env"

    if _BRAIN_CREDS_FILE.exists() and _BRAIN_CREDS_FILE.stat().st_size > 0:
        return "preseeded"

    if _HOST_CREDS_FILE.exists():
        try:
            _BRAIN_CREDS_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_HOST_CREDS_FILE, _BRAIN_CREDS_FILE)
            _BRAIN_CREDS_FILE.chmod(0o600)
            log.info("Claude creds: copied host mount -> %s", _BRAIN_CREDS_FILE)
            return "host_mount"
        except OSError as e:
            log.warning("Claude creds: host mount copy failed: %s", e)

    log.warning(
        "Claude creds: none found. Set ANTHROPIC_API_KEY, "
        "CLAUDE_CODE_OAUTH_REFRESH_TOKEN, mount host ~/.config/anthropic, "
        "or pre-seed /root/.claude/.credentials.json."
    )
    return "none"
