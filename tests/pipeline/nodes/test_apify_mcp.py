"""Unit tests for the ApifyMcpNode (generic Apify Actor bridge)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from app.pipeline.nodes.apify_mcp import ApifyMcpNode
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")


def _arun(coro):
    return asyncio.run(coro)


def _make_apify_mock(items: list[dict], run_meta: dict | None = None):
    """Return (MockClass, mock_instance) for ApifyClient with dataset returning items."""
    if run_meta is None:
        run_meta = {"defaultDatasetId": "ds-999"}

    mock_dataset = MagicMock()
    mock_dataset.iterate_items.return_value = iter(items)

    mock_actor_handle = MagicMock()
    mock_actor_handle.call.return_value = run_meta

    mock_instance = MagicMock()
    mock_instance.actor.return_value = mock_actor_handle
    mock_instance.dataset.return_value = mock_dataset

    MockClass = MagicMock(return_value=mock_instance)
    return MockClass, mock_instance


# ---------------------------------------------------------------------------
# Node metadata
# ---------------------------------------------------------------------------

def test_node_metadata():
    node = ApifyMcpNode()
    assert node.node_type == "apify_mcp"
    assert node.display_name == "Apify Actor (Generic)"
    assert node.category == "enrich"
    props = node.config_schema["properties"]
    assert "actor_id" in props
    assert "input" in props
    assert "max_items" in props
    assert "timeout" in props
    assert "actor_id" in node.config_schema.get("required", [])


# ---------------------------------------------------------------------------
# test_execute_missing_actor_id → returns error entry immediately
# ---------------------------------------------------------------------------

def test_execute_missing_actor_id():
    node = ApifyMcpNode()

    def _raise():
        raise RuntimeError("Apify API key not found")

    with patch("app.pipeline.nodes.apify_actor._resolve_api_key", side_effect=_raise):
        results = _arun(node.execute({}, [], CTX))

    assert len(results) == 1
    assert "error" in results[0]


def test_execute_empty_actor_id_returns_error():
    """An empty actor_id config key should return an error without hitting the API."""
    node = ApifyMcpNode()

    with patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake-key"):
        results = _arun(node.execute({"actor_id": ""}, [], CTX))

    assert len(results) == 1
    assert "error" in results[0]
    assert results[0].get("source") == "apify"


# ---------------------------------------------------------------------------
# test_execute_runs_actor — verifies actor_id and input are forwarded
# ---------------------------------------------------------------------------

def test_execute_runs_actor():
    node = ApifyMcpNode()
    actor_input = {"startUrls": [{"url": "https://example.com"}]}
    items = [{"title": "Example", "url": "https://example.com"}]
    MockApify, mock_instance = _make_apify_mock(items)

    with (
        patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake-key"),
        patch("apify_client.ApifyClient", MockApify),
    ):
        results = _arun(node.execute(
            {"actor_id": "apify/web-scraper", "input": actor_input, "max_items": 10},
            [],
            CTX,
        ))

    # Verify actor slug construction: "/" → "~"
    actor_slug_used = mock_instance.actor.call_args[0][0]
    assert actor_slug_used == "apify~web-scraper"

    # Verify input was forwarded
    call_kwargs = mock_instance.actor.return_value.call.call_args[1]
    assert call_kwargs["run_input"] == actor_input

    assert len(results) == 1
    assert results[0]["title"] == "Example"
    assert results[0]["source"] == "apify"


# ---------------------------------------------------------------------------
# test_execute_returns_raw_items — no field mapping, source injected
# ---------------------------------------------------------------------------

def test_execute_returns_raw_items():
    node = ApifyMcpNode()
    raw_items = [
        {"some_field": "value1", "another": 42},
        {"some_field": "value2", "another": 99},
    ]
    MockApify, _ = _make_apify_mock(raw_items)

    with (
        patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake-key"),
        patch("apify_client.ApifyClient", MockApify),
    ):
        results = _arun(node.execute(
            {"actor_id": "owner~my-actor"},
            [],
            CTX,
        ))

    assert len(results) == 2
    # Raw fields preserved as-is
    assert results[0]["some_field"] == "value1"
    assert results[1]["another"] == 99
    # source injected when not present
    assert results[0]["source"] == "apify"
    assert results[1]["source"] == "apify"


def test_execute_raw_items_preserves_existing_source():
    """If the item already has a 'source' key, it must NOT be overwritten."""
    node = ApifyMcpNode()
    raw_items = [{"data": "x", "source": "custom-source"}]
    MockApify, _ = _make_apify_mock(raw_items)

    with (
        patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake-key"),
        patch("apify_client.ApifyClient", MockApify),
    ):
        results = _arun(node.execute({"actor_id": "owner~actor"}, [], CTX))

    assert results[0]["source"] == "custom-source"


# ---------------------------------------------------------------------------
# test_execute_without_api_key
# ---------------------------------------------------------------------------

def test_execute_without_api_key():
    """A missing Apify key must degrade to an error dict, never raise.

    Raising propagates out of execute() to the node route handler, which turns
    it into an HTTP 500 and can abort the pipeline run. The node must instead
    return a graceful error entry so parallel (free) branches keep running.
    """
    node = ApifyMcpNode()

    def _raise():
        raise RuntimeError(
            "Apify API key not found. Set APIFY_API_TOKEN in .env or configure it in Settings."
        )

    with patch("app.pipeline.nodes.apify_actor._resolve_api_key", side_effect=_raise):
        results = _arun(node.execute({"actor_id": "owner~actor"}, [], CTX))

    assert len(results) == 1
    assert "error" in results[0]
    assert results[0].get("source") == "apify"
    assert "key" in results[0]["error"].lower()


# ---------------------------------------------------------------------------
# test_execute_handles_empty_dataset
# ---------------------------------------------------------------------------

def test_execute_handles_empty_dataset():
    node = ApifyMcpNode()
    MockApify, _ = _make_apify_mock([])

    with (
        patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake-key"),
        patch("apify_client.ApifyClient", MockApify),
    ):
        results = _arun(node.execute({"actor_id": "owner~actor"}, [], CTX))

    assert results == []


# ---------------------------------------------------------------------------
# test_execute_handles_actor_failure
# ---------------------------------------------------------------------------

def test_execute_handles_actor_failure():
    """A network error from the actor call should return an error entry."""
    node = ApifyMcpNode()

    mock_actor_handle = MagicMock()
    mock_actor_handle.call.side_effect = Exception("connection timeout")
    mock_instance = MagicMock()
    mock_instance.actor.return_value = mock_actor_handle

    MockApify = MagicMock(return_value=mock_instance)

    with (
        patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake-key"),
        patch("apify_client.ApifyClient", MockApify),
    ):
        results = _arun(node.execute({"actor_id": "owner~actor"}, [], CTX))

    assert len(results) == 1
    assert "error" in results[0]
    assert results[0]["source"] == "apify"


# ---------------------------------------------------------------------------
# test_execute_respects_max_items
# ---------------------------------------------------------------------------

def test_execute_respects_max_items():
    """Results must be truncated to max_items."""
    node = ApifyMcpNode()
    many_items = [{"i": n} for n in range(20)]
    MockApify, _ = _make_apify_mock(many_items)

    with (
        patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake-key"),
        patch("apify_client.ApifyClient", MockApify),
    ):
        results = _arun(node.execute(
            {"actor_id": "owner~actor", "max_items": 5},
            [],
            CTX,
        ))

    assert len(results) == 5
