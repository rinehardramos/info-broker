"""MCP config invariants.

Both is-mcp-config.json (host/local) and is-mcp-config.docker.json
(container) describe how Claude Code spawns the MCP server. The env
block in those configs SUPPLEMENTS the parent process env — any key
listed here overrides what the spawning process has set.

If we hardcode INFO_BROKER_API_KEY = "changeme" in the config (which we
did), the spawned MCP subprocess uses that literal "changeme" string,
not the real key from the container's env. Every MCP tool that calls
back into the API then gets 401, no tool returns data, and brain phases
"succeed" with zero findings — which is exactly the symptom seen in
the 0-card / 0s-duration screenshot.

This test asserts the config doesn't embed that footgun.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

MCP_CONFIG_FILES = [
    CONFIG_DIR / "is-mcp-config.json",
    CONFIG_DIR / "is-mcp-config.docker.json",
]


@pytest.mark.parametrize("path", MCP_CONFIG_FILES, ids=lambda p: p.name)
def test_mcp_config_does_not_hardcode_api_key(path: Path):
    """The MCP subprocess inherits INFO_BROKER_API_KEY from the spawning
    process. The config must NOT redeclare it — doing so overrides the
    real key with whatever the JSON literal says (typically 'changeme'),
    breaking every MCP tool callback with 401."""
    if not path.exists():
        pytest.skip(f"{path} not present")
    data = json.loads(path.read_text())
    for server_name, server in data.get("mcpServers", {}).items():
        env = server.get("env", {})
        assert "INFO_BROKER_API_KEY" not in env, (
            f"{path.name}::mcpServers.{server_name}.env hardcodes "
            f"INFO_BROKER_API_KEY={env.get('INFO_BROKER_API_KEY')!r} — "
            f"this overrides the parent process env when the MCP "
            f"subprocess spawns. Remove the key from the env block so "
            f"the subprocess inherits the real value."
        )


@pytest.mark.parametrize("path", MCP_CONFIG_FILES, ids=lambda p: p.name)
def test_mcp_config_still_sets_url(path: Path):
    """INFO_BROKER_URL still needs to be in env — the subprocess doesn't
    inherit it as a URL-shaped value from the spawning process (which
    has POSTGRES_HOST, not a base URL)."""
    if not path.exists():
        pytest.skip(f"{path} not present")
    data = json.loads(path.read_text())
    for server_name, server in data.get("mcpServers", {}).items():
        env = server.get("env", {})
        assert "INFO_BROKER_URL" in env, (
            f"{path.name}::mcpServers.{server_name}.env missing "
            f"INFO_BROKER_URL"
        )
