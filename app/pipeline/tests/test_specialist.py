"""Tests for app/pipeline/specialist.py and the 5 technique catalog entries.

MVP-M5 test suite (§10.2).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.pipeline.catalogs.loader import load_catalog
from app.pipeline.catalogs.schemas import TaskSpec, Technique
from app.pipeline.specialist import (
    Finding,
    SpecialistError,
    _NO_EVIDENCE,
    _SCHEMA_VIOLATION,
    _TOOL_ERROR,
    _TRANSPORT_ERROR,
    execute_task,
)

# ---------------------------------------------------------------------------
# Catalog path
# ---------------------------------------------------------------------------

_TECHNIQUES_DIR = (
    Path(__file__).parent.parent / "catalogs" / "registries" / "techniques"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_technique(**overrides) -> Technique:
    """Minimal valid Technique for use in specialist tests."""
    base = {
        "id": "web_search",
        "tool_name": "run_web_search",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["results"],
            "properties": {
                "results": {"type": "array"},
            },
        },
        "cost_class": "moderate",
    }
    base.update(overrides)
    return Technique.model_validate(base)


_SENTINEL = object()


def _make_task(technique_id: str = "web_search", params: dict | object = _SENTINEL) -> TaskSpec:
    resolved = {"query": "test query"} if params is _SENTINEL else params  # type: ignore[arg-type]
    return TaskSpec(
        technique_id=technique_id,
        params_template=resolved,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# 1. Catalog load tests (parametrized over 5 technique ids)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "technique_id",
    ["web_search", "image_search", "tmdb_search", "google_news", "prior_research"],
)
def test_each_technique_loads_via_catalog(technique_id: str):
    """Each technique file must be discoverable by the loader and validate cleanly."""
    catalog = load_catalog("technique", _TECHNIQUES_DIR)
    assert technique_id in catalog, (
        f"Technique '{technique_id}' not found in catalog at {_TECHNIQUES_DIR}. "
        f"Available: {list(catalog)}"
    )
    t = catalog[technique_id]
    assert t.id == technique_id
    assert t.tool_name, "tool_name must not be empty"
    assert t.cost_class in {"cheap", "moderate", "expensive"}
    assert "required" in t.input_schema or "properties" in t.input_schema
    assert "required" in t.output_schema or "properties" in t.output_schema


# ---------------------------------------------------------------------------
# 2. Input validation tests
# ---------------------------------------------------------------------------


def test_specialist_validates_input_rejects_missing_required():
    """Missing required 'query' field should return a schema_violation error."""
    technique = _make_technique()
    task = _make_task(params={})  # no 'query' key

    mock_invoke = MagicMock()
    result = execute_task(task, technique, mock_invoke)

    assert isinstance(result, SpecialistError)
    assert result.kind == _SCHEMA_VIOLATION
    assert "query" in result.details.lower() or "required" in result.details.lower()
    mock_invoke.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Happy-path tests
# ---------------------------------------------------------------------------


def test_specialist_calls_mcp_with_validated_params():
    """The validated params_template is forwarded exactly to mcp_invoke_fn."""
    technique = _make_technique()
    params = {"query": "zhao lusi curling iron", "max_results": 5}
    task = _make_task(params=params)

    mock_invoke = MagicMock(
        return_value={"results": [{"title": "x", "url": "y", "snippet": "z"}]}
    )
    execute_task(task, technique, mock_invoke)

    mock_invoke.assert_called_once_with("run_web_search", params)


def test_specialist_returns_finding_on_success():
    """Valid tool call + valid output schema → Finding with correct fields."""
    technique = _make_technique()
    task = _make_task(params={"query": "test"})

    payload = {"results": [{"title": "t", "url": "u", "snippet": "s"}]}
    mock_invoke = MagicMock(return_value=payload)

    result = execute_task(task, technique, mock_invoke)

    assert isinstance(result, Finding)
    assert result.technique_id == "web_search"
    assert result.params == {"query": "test"}
    assert result.raw_output == payload
    assert result.ts > 0


# ---------------------------------------------------------------------------
# 4. Output schema violation test
# ---------------------------------------------------------------------------


def test_specialist_returns_schema_violation_when_response_invalid():
    """Tool returns a response missing the required 'results' key → schema_violation."""
    technique = _make_technique()
    task = _make_task(params={"query": "test"})

    # Missing 'results' key entirely
    mock_invoke = MagicMock(return_value={"data": []})

    result = execute_task(task, technique, mock_invoke)

    assert isinstance(result, SpecialistError)
    assert result.kind == _SCHEMA_VIOLATION
    assert "results" in result.details.lower() or "required" in result.details.lower()


# ---------------------------------------------------------------------------
# 5. Retry tests
# ---------------------------------------------------------------------------


def test_specialist_retries_transport_error_once_then_fails():
    """A persistent transport error is retried exactly once and then returns
    a transport_error SpecialistError — not a Finding."""
    technique = _make_technique()
    task = _make_task(params={"query": "test"})

    mock_invoke = MagicMock(side_effect=TimeoutError("connection timed out"))

    result = execute_task(task, technique, mock_invoke)

    assert isinstance(result, SpecialistError)
    assert result.kind == _TRANSPORT_ERROR
    # max_attempts=2: called twice
    assert mock_invoke.call_count == 2


def test_specialist_retries_transport_error_succeeds_on_second_attempt():
    """Transport error on first attempt, success on second → Finding returned."""
    technique = _make_technique()
    task = _make_task(params={"query": "test"})

    success_payload = {"results": [{"title": "t", "url": "u", "snippet": "s"}]}
    mock_invoke = MagicMock(
        side_effect=[TimeoutError("timeout"), success_payload]
    )

    result = execute_task(task, technique, mock_invoke)

    assert isinstance(result, Finding)
    assert mock_invoke.call_count == 2


def test_specialist_does_not_retry_schema_violation():
    """Schema violation on input must NOT call mcp_invoke_fn at all."""
    technique = _make_technique()
    task = _make_task(params={})  # missing required 'query'

    mock_invoke = MagicMock()
    result = execute_task(task, technique, mock_invoke)

    assert isinstance(result, SpecialistError)
    assert result.kind == _SCHEMA_VIOLATION
    mock_invoke.assert_not_called()


def test_specialist_does_not_retry_tool_error():
    """Non-transport tool errors (e.g. ValueError) are not retried."""
    technique = _make_technique()
    task = _make_task(params={"query": "test"})

    mock_invoke = MagicMock(side_effect=ValueError("unexpected API response"))

    result = execute_task(task, technique, mock_invoke)

    assert isinstance(result, SpecialistError)
    assert result.kind == _TOOL_ERROR
    mock_invoke.assert_called_once()


# ---------------------------------------------------------------------------
# 6. No-evidence test
# ---------------------------------------------------------------------------


def test_specialist_returns_no_evidence_on_empty_results():
    """Tool returns valid schema but empty results list → no_evidence."""
    technique = _make_technique()
    task = _make_task(params={"query": "very obscure query xyz123"})

    mock_invoke = MagicMock(return_value={"results": []})
    result = execute_task(task, technique, mock_invoke)

    assert isinstance(result, SpecialistError)
    assert result.kind == _NO_EVIDENCE


# ---------------------------------------------------------------------------
# 7. Tool name verification (snapshot assertions)
# ---------------------------------------------------------------------------


def test_catalog_tool_names_match_expected():
    """Verify the 5 tool_names bound in catalog files.

    These are snapshot assertions — if a tool is renamed in the MCP server,
    this test will catch the mismatch.
    """
    catalog = load_catalog("technique", _TECHNIQUES_DIR)

    expected = {
        "web_search": "run_web_search",
        "image_search": "run_image_search",  # FLAG: not yet in mcp_server/server.py
        "tmdb_search": "run_tmdb_search",
        "google_news": "run_google_news",
        "prior_research": "get_past_research",
    }

    for tid, expected_tool in expected.items():
        assert catalog[tid].tool_name == expected_tool, (
            f"Technique '{tid}' tool_name mismatch: "
            f"expected {expected_tool!r}, got {catalog[tid].tool_name!r}"
        )
