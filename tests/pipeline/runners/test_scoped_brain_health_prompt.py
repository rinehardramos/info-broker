"""Unit tests for health-aware tool ordering in scoped_brain._build_scoped_prompt."""
from __future__ import annotations

import time
from unittest.mock import patch

from app.pipeline.catalogs.schemas import Tactic, TaskSpec
from app.pipeline.runners.scoped_brain import _build_scoped_prompt


def _make_tactic(technique_ids: list[str]) -> Tactic:
    """Build a minimal Tactic with the given techniques in produces."""
    return Tactic(
        id="test_tactic",
        phase_compatibility=["gather"],
        accepts={"signals": "test"},
        produces=[
            TaskSpec(
                technique_id=tid,
                params_template={"query": "{hypothesis_query}"},
                expect_schema={},
                fail_modes=[],
                budget_ru=1,
            )
            for tid in technique_ids
        ],
        cost_class="moderate",
        required_techniques=[],
    )


def _fake_cache_with_unhealthy(node_type: str, key_name: str) -> dict:
    return {
        node_type: (
            time.time(),
            {
                "healthy": False,
                "error": f"{key_name} not set",
                "requires_key": key_name,
                "setup_url": None,
                "setup_instructions": None,
            },
        )
    }


# ---------------------------------------------------------------------------
# Healthy-only tactic: no change in ordering
# ---------------------------------------------------------------------------

def test_all_healthy_tools_listed_without_warning():
    tactic = _make_tactic(["web_search"])
    with patch("app.routers.v3.pipelines._health_cache", {}):
        prompt = _build_scoped_prompt(tactic, {"query": "test query"}, "general")
    assert "mcp__info-broker-mcp__run_web_search" in prompt
    assert "⚠" not in prompt
    assert "UNAVAILABLE" not in prompt


# ---------------------------------------------------------------------------
# Mixed tactic: healthy BEFORE unhealthy in the prompt
# ---------------------------------------------------------------------------

def test_healthy_tools_listed_before_unhealthy():
    """web_search (healthy) must appear BEFORE hunter_email_search (unhealthy)."""
    tactic = _make_tactic(["hunter_email_search", "web_search"])
    fake_cache = _fake_cache_with_unhealthy("hunter_io", "HUNTER_API_KEY")

    with patch("app.routers.v3.pipelines._health_cache", fake_cache):
        prompt = _build_scoped_prompt(
            tactic, {"query": "test query"}, "general"
        )

    pos_web = prompt.index("run_web_search")
    pos_hunter = prompt.index("run_hunter_email_search")
    assert pos_web < pos_hunter, (
        "web_search (healthy) should appear before hunter_email_search (unhealthy)"
    )


def test_unhealthy_tool_annotated_with_warning_glyph():
    """Unhealthy tools must carry ⚠ in the prompt."""
    tactic = _make_tactic(["hunter_email_search", "web_search"])
    fake_cache = _fake_cache_with_unhealthy("hunter_io", "HUNTER_API_KEY")

    with patch("app.routers.v3.pipelines._health_cache", fake_cache):
        prompt = _build_scoped_prompt(tactic, {"query": "test query"}, "general")

    assert "⚠" in prompt
    assert "UNAVAILABLE" in prompt
    assert "HUNTER_API_KEY" in prompt


def test_prompt_contains_prefer_healthy_instruction():
    """The prompt must contain the instruction to prefer healthy tools."""
    tactic = _make_tactic(["hunter_email_search", "web_search"])
    fake_cache = _fake_cache_with_unhealthy("hunter_io", "HUNTER_API_KEY")

    with patch("app.routers.v3.pipelines._health_cache", fake_cache):
        prompt = _build_scoped_prompt(tactic, {"query": "test query"}, "general")

    assert "Prefer the healthy tools" in prompt


def test_all_unhealthy_still_included():
    """Even with all tools unhealthy, all are still listed (tactic may require them)."""
    tactic = _make_tactic(["hunter_email_search"])
    fake_cache = _fake_cache_with_unhealthy("hunter_io", "HUNTER_API_KEY")

    with patch("app.routers.v3.pipelines._health_cache", fake_cache):
        prompt = _build_scoped_prompt(tactic, {"query": "test query"}, "general")

    assert "run_hunter_email_search" in prompt
    assert "⚠" in prompt


def test_cache_miss_treated_as_healthy():
    """A technique with no cache entry (unknown) must be listed as healthy (no ⚠)."""
    tactic = _make_tactic(["hunter_email_search"])
    with patch("app.routers.v3.pipelines._health_cache", {}):
        prompt = _build_scoped_prompt(tactic, {"query": "test query"}, "general")

    assert "⚠" not in prompt
    assert "mcp__info-broker-mcp__run_hunter_email_search" in prompt
