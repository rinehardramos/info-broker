"""TDD tests for app.memory.skills — procedural memory / research skills."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch


def _arun(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------


def test_estimate_cost_free_tools():
    """Free tools only -> 0.0."""
    from app.memory.skills import estimate_cost

    result = estimate_cost(["ddg_search", "web_crawl", "wikipedia_api"])
    assert result == 0.0


def test_estimate_cost_mixed_tools():
    """Mixed tools -> sum of individual costs."""
    from app.memory.skills import estimate_cost

    # ddg_search=0.0, linkedin_profile=0.10, ai_scoring=0.02, apollo_zoominfo=0.10
    result = estimate_cost(["ddg_search", "linkedin_profile", "ai_scoring", "apollo_zoominfo"])
    assert abs(result - 0.22) < 1e-9


def test_estimate_cost_empty():
    """Empty list -> 0.0."""
    from app.memory.skills import estimate_cost

    assert estimate_cost([]) == 0.0


# ---------------------------------------------------------------------------
# extract_tool_sequence
# ---------------------------------------------------------------------------


def test_extract_tool_sequence_from_trail():
    """Trail with 3 branches, tools deduplicated in first-seen order."""
    from app.memory.skills import extract_tool_sequence

    trail = {
        "branches": [
            {"tools_used": ["ddg_search", "web_crawl"]},
            {"tools_used": ["web_crawl", "linkedin_profile"]},
            {"tools_used": ["ai_scoring", "ddg_search"]},
        ]
    }
    result = extract_tool_sequence(trail)
    assert result == ["ddg_search", "web_crawl", "linkedin_profile", "ai_scoring"]


def test_extract_tool_sequence_empty():
    """Empty dict and branches=[] both return []."""
    from app.memory.skills import extract_tool_sequence

    assert extract_tool_sequence({}) == []
    assert extract_tool_sequence({"branches": []}) == []


# ---------------------------------------------------------------------------
# create_skill_from_run
# ---------------------------------------------------------------------------


def test_create_skill_from_run():
    """create_skill_from_run calls execute with INSERT and calls _index_skill_to_qdrant."""
    from app.memory.skills import create_skill_from_run

    result_data = {
        "entity_type": "organization",
        "keywords": ["acme", "corp"],
        "trail": {
            "branches": [
                {"tools_used": ["ddg_search", "web_crawl"]},
            ]
        },
        "pipeline": {"nodes": []},
        "branch_pattern": {"fanout": 1},
        "findings": [{"title": "Finding A"}, {"title": "Finding B"}],
        "entities_found": 3,
        "tool_calls": 5,
        "error_rate": 0.0,
    }

    execute_calls = []

    def fake_execute(query, params=()):
        execute_calls.append((query, params))

    async def fake_index(*args, **kwargs):
        pass

    with (
        patch("app.memory.skills.execute", fake_execute),
        patch("app.memory.skills._index_skill_to_qdrant", fake_index),
    ):
        skill_id = _arun(
            create_skill_from_run(
                run_id="run-abc-111",
                query="Acme Corp research",
                result=result_data,
                duration_seconds=30,
            )
        )

    assert len(execute_calls) == 1
    insert_sql, _ = execute_calls[0]
    assert "INSERT INTO research_skills" in insert_sql
    assert skill_id is not None


# ---------------------------------------------------------------------------
# get_matching_skills
# ---------------------------------------------------------------------------


def test_get_matching_skills():
    """get_matching_skills queries DB, scores by keyword overlap, returns results."""
    from app.memory.skills import get_matching_skills

    fake_skills = [
        {
            "id": "skill-1",
            "query": "Acme Corp research",
            "keywords": ["acme", "corp", "organization"],
            "tool_sequence": ["ddg_search", "web_crawl"],
            "quality_score": 0.8,
            "efficiency": 0.9,
            "times_adopted": 2,
            "times_suggested": 3,
            "estimated_cost_usd": 0.0,
            "findings_count": 5,
        },
        {
            "id": "skill-2",
            "query": "Generic research",
            "keywords": ["generic"],
            "tool_sequence": ["ddg_search"],
            "quality_score": 0.5,
            "efficiency": 0.6,
            "times_adopted": 0,
            "times_suggested": 1,
            "estimated_cost_usd": 0.0,
            "findings_count": 2,
        },
    ]

    with patch("app.memory.skills.fetch_all", return_value=fake_skills):
        results = _arun(get_matching_skills("Acme Corp research", limit=3))

    # Results should be returned (keyword overlap scoring)
    assert isinstance(results, list)
    assert len(results) >= 1
    # skill-1 should rank higher due to keyword overlap
    assert results[0]["id"] == "skill-1"


# ---------------------------------------------------------------------------
# format_skills_for_prompt
# ---------------------------------------------------------------------------


def test_format_skills_for_prompt():
    """format_skills_for_prompt produces 'SUGGESTED STRATEGIES' section."""
    from app.memory.skills import format_skills_for_prompt

    skills = [
        {
            "id": "skill-1",
            "query": "Acme Corp research",
            "tool_sequence": ["ddg_search", "web_crawl", "linkedin_profile"],
            "quality_score": 0.85,
            "findings_count": 7,
            "estimated_cost_usd": 0.10,
            "efficiency": 0.9,
        }
    ]

    output = format_skills_for_prompt(skills)
    assert "SUGGESTED STRATEGIES" in output
    assert "ddg_search" in output
    assert "web_crawl" in output
