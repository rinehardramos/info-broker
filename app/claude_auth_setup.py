"""
Platform-portable Claude Code credential setup.

Resolves Claude Code authentication in this priority:
  1. ANTHROPIC_API_KEY env var (CI / API-key mode)
  2. CLAUDE_CODE_OAUTH_REFRESH_TOKEN env var (cloud worker)
  3. Pre-seeded /root/.claude/.credentials.json. This can be one of:
       - host_bind_mount: ~/.claude on the host is bind-mounted into the
         container. Host CLI auto-refreshes the OAuth token; container sees
         the fresh file on next brain spawn. **Preferred — no staleness.**
       - named_volume_preseeded: legacy. File was `docker cp`-ed into the
         claude_auth named volume. Goes stale when host token rotates
         (~30 days) unless re-copied. Avoid for long-running deployments.
  4. Mounted host credentials at /root/.config/anthropic/ (macOS / older
     setup-token flow). Copies into /root/.claude on first call only.

``ensure_claude_credentials()`` returns the legacy string identifier
(``api_key`` / ``oauth_env`` / ``preseeded`` / ``host_mount`` / ``none``)
so existing string-match call sites don't break.

``classify_credentials_source()`` returns the richer five-value classification
(``api_key_env`` / ``oauth_env`` / ``host_bind_mount`` /
``named_volume_preseeded`` / ``host_mount_copy`` / ``none``) — used for
admin log observability.
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


def _is_bind_mounted_dir(path: Path) -> bool:
    """Heuristic: a bind-mount's directory st_dev differs from its parent's.

    A named Docker volume mounted at /root/.claude has its OWN st_dev too —
    so this isn't a perfect bind-vs-named-volume signal on its own. But it
    correctly tells "this dir is a mount point" vs "this dir is just a
    regular directory in the container's rootfs", which is the actionable
    distinction for the admin reading the log line.
    """
    try:
        return path.stat().st_dev != path.parent.stat().st_dev
    except OSError:
        return False


def classify_credentials_source() -> str:
    """Pure classification of which auth source applies right now.

    Returns one of:
      api_key_env             — ANTHROPIC_API_KEY set
      oauth_env               — CLAUDE_CODE_OAUTH_REFRESH_TOKEN set
      host_bind_mount         — /root/.claude is a bind-mount (host live file)
      named_volume_preseeded  — /root/.claude is a Docker named volume copy
                                (subject to staleness)
      host_mount_copy         — /root/.config/anthropic mount has a file that
                                will be copied to /root/.claude on first use
      none                    — no credentials reachable; brain will 401
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "api_key_env"
    if os.environ.get("CLAUDE_CODE_OAUTH_REFRESH_TOKEN"):
        return "oauth_env"
    if _BRAIN_CREDS_FILE.exists() and _BRAIN_CREDS_FILE.stat().st_size > 0:
        return "host_bind_mount" if _is_bind_mounted_dir(_BRAIN_CREDS_DIR) else "named_volume_preseeded"
    if _HOST_CREDS_FILE.exists():
        return "host_mount_copy"
    return "none"


def ensure_claude_credentials() -> str:
    """Ensure /root/.claude/.credentials.json exists; return legacy source id."""
    source = classify_credentials_source()
    log.info("Claude creds: source=%s", source)

    if source == "api_key_env":
        return "api_key"
    if source == "oauth_env":
        return "oauth_env"
    if source in ("host_bind_mount", "named_volume_preseeded"):
        if source == "named_volume_preseeded":
            log.warning(
                "Claude creds: using named-volume copy at %s. This file does "
                "NOT auto-refresh — when the host's OAuth token rotates (~30 "
                "days), brain runs will start 401-ing silently. Bind-mount the "
                "host's ~/.claude instead via HOST_CLAUDE_DIR in .env.",
                _BRAIN_CREDS_FILE,
            )
        return "preseeded"
    if source == "host_mount_copy":
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
