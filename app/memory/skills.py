"""Procedural memory — research skills with cost tracking."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from app.routers.v3.db import execute, fetch_all, fetch_one

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool cost registry (USD per call)
# ---------------------------------------------------------------------------

_TOOL_COSTS: dict[str, float] = {
    # Free tools
    "ddg_search": 0.0,
    "web_crawl": 0.0,
    "wikipedia_api": 0.0,
    "rss_feed": 0.0,
    "news_search": 0.0,
    "whois_lookup": 0.0,
    "dns_lookup": 0.0,
    "shodan_search": 0.0,
    "github_search": 0.0,
    "patent_search": 0.0,
    "court_records": 0.0,
    "manual_scoring": 0.0,
    "agent_input": 0.0,
    # Moderate cost tools
    "ai_scoring": 0.02,
    "ai_analysis": 0.02,
    "llm_analysis": 0.02,
    # Expensive tools
    "linkedin_profile": 0.10,
    "apollo_zoominfo": 0.10,
    "clearbit": 0.10,
    "hunter_io": 0.05,
    "crunchbase": 0.05,
    "fullcontact": 0.05,
}


def estimate_cost(tool_calls: list[str]) -> float:
    """Return estimated USD cost for a sequence of tool calls."""
    return sum(_TOOL_COSTS.get(tool, 0.0) for tool in tool_calls)


def extract_tool_sequence(trail: dict) -> list[str]:
    """Extract deduplicated tool sequence from a trail dict, first-seen order.

    Expects trail to have a 'branches' key, each branch having 'tools_used'.
    """
    branches = trail.get("branches", [])
    seen: dict[str, None] = {}  # ordered set via dict keys
    for branch in branches:
        for tool in branch.get("tools_used", []):
            seen[tool] = None
    return list(seen.keys())


# ---------------------------------------------------------------------------
# Qdrant indexing
# ---------------------------------------------------------------------------


async def _index_skill_to_qdrant(
    skill_id: str,
    query: str,
    tool_sequence: list[str],
    findings_count: int,
    cost: float,
    efficiency: float,
) -> None:
    """Upsert a skill point with type='skill' into the research_memory collection."""
    try:
        from app.memory.writer import _get_qdrant_client, _embed_text
        from qdrant_client.models import PointStruct

        embed_text = " ".join(tool_sequence) + " " + query
        vector = _embed_text(embed_text)

        client = _get_qdrant_client()
        point = PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"skill:{skill_id}")),
            vector=vector,
            payload={
                "type": "skill",
                "skill_id": skill_id,
                "query": query,
                "tool_sequence": tool_sequence,
                "findings_count": findings_count,
                "estimated_cost_usd": cost,
                "efficiency": efficiency,
            },
        )
        client.upsert(collection_name="research_memory", points=[point])
        log.info("Indexed skill %s to Qdrant", skill_id)
    except Exception:
        log.exception("Failed to index skill %s to Qdrant", skill_id)


# ---------------------------------------------------------------------------
# create_skill_from_run
# ---------------------------------------------------------------------------


async def create_skill_from_run(
    run_id: str,
    query: str,
    result: dict[str, Any],
    duration_seconds: int,
) -> str:
    """Extract skill components from a run result and insert into research_skills.

    Returns the new skill_id (UUID string).
    """
    entity_type = result.get("entity_type")
    keywords: list[str] = result.get("keywords") or []
    trail: dict = result.get("trail") or {}
    pipeline = result.get("pipeline")
    branch_pattern = result.get("branch_pattern") or {}
    findings: list = result.get("findings") or []
    findings_count = len(findings)
    entities_found: int = result.get("entities_found") or 0
    tool_calls_count: int = result.get("tool_calls") or 0
    error_rate: float = result.get("error_rate") or 0.0

    tool_sequence = extract_tool_sequence(trail)
    estimated_cost = estimate_cost(tool_sequence)

    # efficiency: findings per second, bounded to 0–1 range for reasonable values
    efficiency: float = 0.0
    if duration_seconds > 0 and findings_count > 0:
        efficiency = min(findings_count / max(duration_seconds, 1), 1.0)

    # quality_score: 0 until feedback recalculates it
    quality_score = 0.0

    skill_id = str(uuid.uuid4())

    execute(
        """
        INSERT INTO research_skills (
            id, run_id, query, entity_type, keywords, tool_sequence,
            pipeline, branch_pattern, findings_count, quality_score,
            error_rate, entities_found, tool_calls, duration_seconds,
            estimated_cost_usd, efficiency
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s
        )
        """,
        (
            skill_id,
            run_id,
            query,
            entity_type,
            keywords,
            tool_sequence,
            json.dumps(pipeline) if pipeline is not None else None,
            json.dumps(branch_pattern),
            findings_count,
            quality_score,
            error_rate,
            entities_found,
            tool_calls_count,
            duration_seconds,
            estimated_cost,
            efficiency,
        ),
    )

    await _index_skill_to_qdrant(
        skill_id=skill_id,
        query=query,
        tool_sequence=tool_sequence,
        findings_count=findings_count,
        cost=estimated_cost,
        efficiency=efficiency,
    )

    log.info("Created skill %s for run_id=%s", skill_id, run_id)
    return skill_id


# ---------------------------------------------------------------------------
# get_matching_skills
# ---------------------------------------------------------------------------


async def get_matching_skills(query: str, limit: int = 3) -> list[dict]:
    """Retrieve skills from PG, rank by keyword overlap with query, return top results."""
    rows = fetch_all(
        """
        SELECT id, query, keywords, tool_sequence, quality_score, efficiency,
               times_adopted, times_suggested, estimated_cost_usd, findings_count
        FROM research_skills
        WHERE disabled = false
        ORDER BY quality_score DESC
        LIMIT 50
        """,
        (),
    )

    query_words = set(query.lower().split())

    def _overlap_score(skill: dict) -> float:
        keywords: list[str] = skill.get("keywords") or []
        kw_set = {k.lower() for k in keywords}
        overlap = len(query_words & kw_set)
        base = skill.get("quality_score") or 0.0
        return overlap * 0.5 + base

    ranked = sorted(rows, key=_overlap_score, reverse=True)
    return ranked[:limit]


# ---------------------------------------------------------------------------
# update_skill_quality
# ---------------------------------------------------------------------------


async def update_skill_quality(run_id: str) -> None:
    """Recalculate quality_score for a skill from finding_feedback AVG for the run."""
    row = fetch_one(
        """
        SELECT AVG(user_score) AS avg_score
        FROM finding_feedback
        WHERE run_id = %s
        """,
        (run_id,),
    )
    if row and row.get("avg_score") is not None:
        avg = float(row["avg_score"])
        # Normalize from [-1, 1] to [0, 1]
        quality_score = (avg + 1.0) / 2.0
        execute(
            "UPDATE research_skills SET quality_score = %s WHERE run_id = %s",
            (quality_score, run_id),
        )
        log.info("Updated quality_score=%.3f for run_id=%s", quality_score, run_id)


# ---------------------------------------------------------------------------
# format_skills_for_prompt
# ---------------------------------------------------------------------------


def format_skills_for_prompt(skills: list[dict]) -> str:
    """Format a list of skill dicts as a 'SUGGESTED STRATEGIES' prompt section."""
    if not skills:
        return ""

    lines = ["=== SUGGESTED STRATEGIES ==="]
    for i, skill in enumerate(skills, start=1):
        tool_seq = skill.get("tool_sequence") or []
        quality = skill.get("quality_score") or 0.0
        findings = skill.get("findings_count") or 0
        cost = skill.get("estimated_cost_usd") or 0.0
        efficiency = skill.get("efficiency") or 0.0
        query = skill.get("query") or ""

        lines.append(
            f"\nStrategy {i}: {query}"
        )
        lines.append(f"  Tools: {' → '.join(tool_seq)}")
        lines.append(
            f"  Quality: {quality:.2f} | Findings: {findings} | "
            f"Cost: ${cost:.2f} | Efficiency: {efficiency:.2f}"
        )

    return "\n".join(lines)
