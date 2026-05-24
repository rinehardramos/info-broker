"""Tests for Shodan, Dropbox, and Google Drive datastore nodes."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")


def _arun(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Category / metadata assertions (no I/O)
# ---------------------------------------------------------------------------

def test_all_nodes_have_correct_category():
    from app.pipeline.nodes.shodan_search import ShodanSearchNode
    from app.pipeline.nodes.dropbox_search import DropboxSearchNode
    from app.pipeline.nodes.google_drive_search import GoogleDriveSearchNode

    assert ShodanSearchNode.category == "enrich"
    # Dropbox and Google Drive use category "source" (file/datastore source nodes)
    assert DropboxSearchNode.category == "source"
    assert GoogleDriveSearchNode.category == "source"


def test_all_nodes_have_node_type():
    from app.pipeline.nodes.shodan_search import ShodanSearchNode
    from app.pipeline.nodes.dropbox_search import DropboxSearchNode
    from app.pipeline.nodes.google_drive_search import GoogleDriveSearchNode

    assert ShodanSearchNode.node_type == "shodan_search"
    assert DropboxSearchNode.node_type == "dropbox_search"
    assert GoogleDriveSearchNode.node_type == "google_drive_search"


def test_nodes_have_config_schema():
    from app.pipeline.nodes.dropbox_search import DropboxSearchNode
    from app.pipeline.nodes.google_drive_search import GoogleDriveSearchNode

    for node_cls in (DropboxSearchNode, GoogleDriveSearchNode):
        schema = node_cls.config_schema
        assert schema.get("type") == "object"
        assert "properties" in schema


# ---------------------------------------------------------------------------
# Shodan — no API key returns structured error
# ---------------------------------------------------------------------------

def test_shodan_returns_error_without_api_key():
    from app.pipeline.nodes.shodan_search import ShodanSearchNode

    node = ShodanSearchNode()
    with patch("app.pipeline.nodes.shodan_search._resolve_api_key", return_value=None):
        result = _arun(node.execute({"query": "test"}, [], CTX))
    assert len(result) == 1
    assert "error" in result[0]
    assert result[0].get("source") == "shodan"


# ---------------------------------------------------------------------------
# Dropbox — missing token / query
# ---------------------------------------------------------------------------

def test_dropbox_returns_error_without_token():
    from app.pipeline.nodes.dropbox_search import DropboxSearchNode

    node = DropboxSearchNode()
    with patch("app.pipeline.nodes.dropbox_search._resolve_token", return_value=None):
        result = _arun(node.execute({"query": "test"}, [], CTX))
    assert len(result) == 1
    assert "error" in result[0]
    assert result[0].get("source") == "dropbox"


def test_dropbox_returns_error_without_query():
    from app.pipeline.nodes.dropbox_search import DropboxSearchNode

    node = DropboxSearchNode()
    with patch("app.pipeline.nodes.dropbox_search._resolve_token", return_value="fake-token"):
        result = _arun(node.execute({}, [], CTX))
    assert len(result) == 1
    assert "error" in result[0]


def test_dropbox_search_returns_results():
    from app.pipeline.nodes.dropbox_search import DropboxSearchNode, _search_dropbox

    fake_matches = [
        {
            "metadata": {
                "metadata": {
                    "name": "report.pdf",
                    "path_display": "/Documents/report.pdf",
                    ".tag": "file",
                    "size": 12345,
                    "client_modified": "2026-01-01T00:00:00Z",
                }
            }
        }
    ]

    # Test the sync helper directly (avoids executor/httpx complexity)
    import httpx as _httpx
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {"matches": fake_matches}

    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.post.return_value = fake_response

    with patch("app.pipeline.nodes.dropbox_search.httpx.Client", return_value=fake_client):
        result = _search_dropbox("tok", "report", "", 10)

    assert len(result) == 1
    assert result[0]["title"] == "report.pdf"
    assert result[0]["source"] == "dropbox"


# ---------------------------------------------------------------------------
# Google Drive — missing credentials / query
# ---------------------------------------------------------------------------

def test_google_drive_returns_error_on_missing_credentials():
    from app.pipeline.nodes.google_drive_search import GoogleDriveSearchNode

    node = GoogleDriveSearchNode()
    with patch("app.pipeline.nodes.google_drive_search._resolve_credentials_path", return_value=None):
        with patch("app.pipeline.nodes.google_drive_search._resolve_api_key", return_value=None):
            result = _arun(node.execute({"query": "test"}, [], CTX))
    assert len(result) == 1
    assert "error" in result[0]
    assert result[0].get("source") == "google_drive"


def test_google_drive_returns_error_without_query():
    from app.pipeline.nodes.google_drive_search import GoogleDriveSearchNode

    node = GoogleDriveSearchNode()
    with patch("app.pipeline.nodes.google_drive_search._resolve_credentials_path", return_value=None):
        with patch("app.pipeline.nodes.google_drive_search._resolve_api_key", return_value="fake-key"):
            result = _arun(node.execute({}, [], CTX))
    assert len(result) == 1
    assert "error" in result[0]


def test_google_drive_search_returns_results():
    from app.pipeline.nodes.google_drive_search import _search_drive

    fake_files = [
        {
            "id": "abc123",
            "name": "Q1 Report.xlsx",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "webViewLink": "https://docs.google.com/file/abc123",
            "modifiedTime": "2026-03-01T00:00:00Z",
            "owners": [{"displayName": "Alice"}],
            "size": "98765",
        }
    ]

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {"files": fake_files}

    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.get.return_value = fake_response

    with patch("app.pipeline.nodes.google_drive_search.httpx.Client", return_value=fake_client):
        result = _search_drive(None, "fake-key", "Q1 Report", 10, "")

    assert len(result) == 1
    assert result[0]["title"] == "Q1 Report.xlsx"
    assert result[0]["source"] == "google_drive"
    assert result[0]["owners"] == ["Alice"]


# ---------------------------------------------------------------------------
# NodeRegistry registration
# ---------------------------------------------------------------------------

def test_dropbox_and_google_drive_registered():
    from app.pipeline.nodes import NodeRegistry

    NodeRegistry._nodes = {}
    NodeRegistry.auto_discover()

    assert "dropbox_search" in NodeRegistry._nodes
    assert "google_drive_search" in NodeRegistry._nodes


# ---------------------------------------------------------------------------
# Tool schema presence
# ---------------------------------------------------------------------------

def test_dropbox_has_tool_schema():
    from app.pipeline.nodes.dropbox_search import DropboxSearchNode

    schema = DropboxSearchNode().tool_schema()
    assert schema["name"] == "search_dropbox"
    assert "query" in schema["input_schema"]["properties"]


def test_google_drive_has_tool_schema():
    from app.pipeline.nodes.google_drive_search import GoogleDriveSearchNode

    schema = GoogleDriveSearchNode().tool_schema()
    assert schema["name"] == "search_google_drive"
    assert "query" in schema["input_schema"]["properties"]
