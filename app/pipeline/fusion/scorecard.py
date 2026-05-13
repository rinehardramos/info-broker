"""Strategy scorecard engine — Admiralty Code grading (source A-F × credibility 1-6)."""

from __future__ import annotations
import logging
from collections import defaultdict

from app.pipeline.strategies.analyzer import PIVOT_TOOL_MAP

log = logging.getLogger(__name__)

# Admiralty Code
# Source reliability:  A=completely reliable, B=usually, C=fairly, D=not usually, E=unreliable, F=cannot judge
# Info credibility:    1=confirmed, 2=probably true, 3=possibly true, 4=doubtful, 5=improbable, 6=cannot judge

SOURCE_LABELS = {
    "A": "Completely reliable",
    "B": "Usually reliable",
    "C": "Fairly reliable",
    "D": "Not usually reliable",
    "E": "Unreliable",
    "F": "Cannot be judged",
}
CRED_LABELS = {
    "1": "Confirmed by other sources",
    "2": "Probably true",
    "3": "Possibly true",
    "4": "Doubtful",
    "5": "Improbable",
    "6": "Cannot be judged",
}

# Numeric sort order (lower = better)
_SOURCE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5}
_CRED_ORDER = {"1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5}


def _split(code: str) -> tuple[str, str]:
    """Split 'B2' into ('B', '2'). Falls back to ('F', '6')."""
    if len(code) == 2 and code[0] in SOURCE_LABELS and code[1] in CRED_LABELS:
        return code[0], code[1]
    return "F", "6"


def auto_grade_technique(result_count: int, error: str | None) -> str:
    """Admiralty grade for a single tool call."""
    if error:
        if "timeout" in str(error).lower() or "rate" in str(error).lower():
            return "D4"  # Not usually reliable / doubtful
        return "E5"      # Unreliable / improbable
    if result_count >= 5:
        return "A1"  # Completely reliable / confirmed
    if result_count >= 3:
        return "A2"  # Completely reliable / probably true
    if result_count >= 1:
        return "B2"  # Usually reliable / probably true
    return "C3"      # Fairly reliable / possibly true (clean negative)


def grade_comment_technique(tool: str, grade: str, result_count: int, error: str | None) -> str:
    src, cred = _split(grade)
    if src in ("A", "B"):
        return f"{tool} produced {result_count} finding(s) — effective, continue using."
    if src == "C":
        return f"{tool} returned no results but ran cleanly — may not apply to this target type."
    if src == "D":
        return f"{tool} encountered rate-limit/timeout: {error or 'rate limit'} — retry with different params."
    if src == "E":
        return f"{tool} FAILED: {error or 'error'} — investigate tool config or skip until fixed."
    return f"{tool} reliability unknown — insufficient data."


def grade_comment_tactic(name: str, grade: str, yield_rate: float, technique_grades: list[str]) -> str:
    src, cred = _split(grade)
    if src in ("A", "B"):
        return f"Tactic '{name}' is effective (yield {yield_rate:.0%}). Use as primary approach for this selector type."
    if src == "C":
        return f"Tactic '{name}' produced some results (yield {yield_rate:.0%}). Consider supplementing with additional tools."
    if src in ("D", "E"):
        failed = sum(1 for g in technique_grades if _split(g)[0] in ("D", "E", "F"))
        return f"Tactic '{name}' underperformed (yield {yield_rate:.0%}, {failed} tools failed). Try alternative approaches."
    return f"Tactic '{name}' completely failed. All tools returned errors. Investigate tool configurations."


def grade_comment_strategy(name: str, grade: str, completeness_pct: float, gaps: list[str] | None) -> str:
    src, cred = _split(grade)
    if src in ("A", "B"):
        return f"Strategy '{name}' achieved {completeness_pct:.0%} coverage. Well-executed investigation."
    if src == "C":
        gap_str = f" Gaps: {', '.join(gaps[:3])}" if gaps else ""
        return f"Strategy '{name}' achieved {completeness_pct:.0%} coverage.{gap_str} Go deeper on missing domains."
    if src in ("D", "E"):
        gap_str = f" Missing: {', '.join(gaps[:5])}" if gaps else ""
        return f"Strategy '{name}' only {completeness_pct:.0%} coverage.{gap_str} Increase depth and use more tools."
    return f"Strategy '{name}' failed — no meaningful coverage. Check that tools are configured and accessible."


def auto_grade_tactic(techniques: list[dict]) -> str:
    if not techniques:
        return "F6"

    grades = [t["auto_grade"] for t in techniques]
    total_results = sum(t.get("result_count", 0) for t in techniques)
    yield_rate = total_results / max(len(techniques), 1)

    fail_count = sum(1 for g in grades if _split(g)[0] in ("E", "F"))
    a_count = sum(1 for g in grades if _split(g)[0] == "A")

    if fail_count == len(grades):
        return "F6"
    if yield_rate >= 0.7 and a_count >= 1:
        return "A1"
    if yield_rate >= 0.4 or sum(1 for g in grades if _split(g)[0] in ("A", "B")) >= 2:
        return "B2"
    if total_results >= 1:
        return "C3"
    if total_results == 0 and fail_count > 0:
        return "E5"
    return "D4"


def auto_grade_strategy(tactics: list[dict], completeness_pct: float) -> str:
    if not tactics:
        return "F6"

    grades = [t["auto_grade"] for t in tactics]
    b_plus = sum(1 for g in grades if _split(g)[0] in ("A", "B"))
    f_count = sum(1 for g in grades if _split(g)[0] == "F")

    if completeness_pct >= 0.8 and b_plus >= 3 and f_count == 0:
        return "A1"
    if completeness_pct >= 0.6 and b_plus >= 2:
        return "B2"
    if completeness_pct >= 0.4 and b_plus >= 1:
        return "C3"
    if completeness_pct >= 0.2:
        return "D4"
    if any(_split(g)[0] not in ("E", "F") for g in grades):
        return "E5"
    return "F6"


def _is_broken_tool_finding(f: dict) -> bool:
    """Return True if a finding represents a blocked/error tool call."""
    if f.get("confidence", 100) != 0:
        return False
    title = str(f.get("title", "")).lower()
    source = str(f.get("source", "")).lower()
    content = str(f.get("content", "")).lower()
    keywords = (
        "blocked", "403", "401", "not configured", "api key", "unauthorized",
        "timeout", "unavailable", "structurally", "error",
    )
    return any(kw in title or kw in source or kw in content for kw in keywords)


def build_scorecard(
    trail: "dict | list",
    findings: "list[dict] | str | None" = None,
    completeness_pct: "float | str" = 0.0,
    entity_type: str = "person",
) -> dict:
    """Build an Admiralty-graded scorecard.

    Supports two calling conventions:
      build_scorecard(trail_dict, findings_list, completeness_pct, entity_type)  — production
      build_scorecard(findings_list, run_id_str, entity_type_str)                — verify / tests
    """
    # Detect findings-first calling convention: build_scorecard(findings, run_id, entity_type)
    if isinstance(trail, list):
        findings = trail
        # completeness_pct arg holds entity_type in this mode; findings arg holds run_id (ignored)
        entity_type = str(completeness_pct) if completeness_pct else "person"
        trail = {}
        completeness_pct = 0.0
    else:
        if findings is None:
            findings = []
        if not isinstance(completeness_pct, float):
            try:
                completeness_pct = float(completeness_pct)
            except (TypeError, ValueError):
                completeness_pct = 0.0

    findings = findings or []

    # ------------------------------------------------------------------
    # Blocked-tool penalty
    # ------------------------------------------------------------------
    blocked_count = sum(1 for f in findings if _is_broken_tool_finding(f))
    # Legacy alias kept for any internal callers
    broken_tool_count = blocked_count
    total_findings = len(findings)
    broken_ratio = blocked_count / max(total_findings, 1)

    if broken_ratio >= 0.3:
        blocked_penalty = min(blocked_count * 4, 20)
        original_completeness = completeness_pct
        completeness_pct = max(0.0, completeness_pct - blocked_penalty / 100.0)
        log.warning(
            "Blocked-tool penalty applied: %d/%d findings are blocked (%.0f%%). "
            "Completeness reduced from %.2f to %.2f (penalty=%d).",
            blocked_count,
            total_findings,
            broken_ratio * 100,
            original_completeness,
            completeness_pct,
            blocked_penalty,
        )

    branches = trail.get("branches", []) if isinstance(trail, dict) else []

    if not branches:
        return {
            "strategy": {
                "name": entity_type,
                "auto_grade": "F6",
                "admiralty_source": "F",
                "user_grade": None,
                "completeness_pct": completeness_pct,
                "comment": "",
            },
            "tactics": [],
            "entity_type": entity_type,
            "blocked_tools": blocked_count,
        }

    tactic_groups: dict[str, list[dict]] = defaultdict(list)

    for branch in branches:
        tools = branch.get("tools_used", [])
        branch_findings = branch.get("findings_count", 0)
        branch_status = branch.get("status", "unknown")
        per_tool = branch_findings / max(len(tools), 1)

        for tool in tools:
            clean_tool = tool.replace("run_", "")
            selector_type = PIVOT_TOOL_MAP.get(clean_tool, "unknown")

            error = None
            if branch_status in ("needs_tool", "depth_exhausted") and branch_findings == 0:
                error = f"Branch status: {branch_status}"

            auto_grade = auto_grade_technique(int(per_tool), error)
            technique = {
                "tool": tool,
                "result_count": int(per_tool),
                "error": error,
                "auto_grade": auto_grade,
                "user_grade": None,
                "branch_name": branch.get("name", ""),
                "branch_status": branch_status,
                "comment": grade_comment_technique(tool, auto_grade, int(per_tool), error),
            }
            tactic_groups[selector_type].append(technique)

    tactics = []
    for selector_type, techniques in tactic_groups.items():
        name = f"{selector_type}_investigation"
        yield_rate = sum(t["result_count"] for t in techniques) / max(len(techniques), 1)
        auto_grade = auto_grade_tactic(techniques)
        tactic = {
            "name": name,
            "selector_type": selector_type,
            "yield_rate": yield_rate,
            "auto_grade": auto_grade,
            "user_grade": None,
            "techniques": techniques,
            "comment": grade_comment_tactic(name, auto_grade, yield_rate, [t["auto_grade"] for t in techniques]),
        }
        tactics.append(tactic)

    tactics.sort(key=lambda t: _SOURCE_ORDER.get(_split(t["auto_grade"])[0], 5))

    # Pyramid of Pain boost: TTP-level findings increase effective completeness
    pyramid_bonus = 0
    pyramid_summary: dict = {}
    try:
        from app.pipeline.fusion.pyramid_scoring import annotate_findings, PYRAMID_LABELS
        annotated = [f for f in findings if isinstance(f, dict)]
        annotate_findings(annotated)
        pyramid_levels = [f.get("pyramid_level", 1) for f in annotated]
        if pyramid_levels:
            high_pyramid_ratio = sum(1 for lvl in pyramid_levels if lvl >= 5) / len(pyramid_levels)
            # Up to +0.10 boost to completeness_pct for investigations rich in TTP-level findings
            pyramid_bonus = round(high_pyramid_ratio * 10)
            completeness_pct = min(1.0, completeness_pct + high_pyramid_ratio * 0.10)
            level_counts: dict[int, int] = {}
            for lvl in pyramid_levels:
                level_counts[lvl] = level_counts.get(lvl, 0) + 1
            pyramid_summary = {
                "finding_count": len(pyramid_levels),
                "high_pyramid_count": sum(1 for lvl in pyramid_levels if lvl >= 5),
                "high_pyramid_ratio": round(high_pyramid_ratio, 3),
                "pyramid_bonus": pyramid_bonus,
                "level_distribution": {
                    PYRAMID_LABELS.get(lvl, str(lvl)): cnt
                    for lvl, cnt in sorted(level_counts.items())
                },
            }
    except Exception:
        pass

    strategy_grade = auto_grade_strategy(tactics, completeness_pct)

    # Cap admiralty_source grade based on blocked-tool ratio
    # broken_ratio >= 0.6 → floor at "D"; >= 0.4 → floor at "C"
    if blocked_count > 0:
        src_letter, cred_digit = _split(strategy_grade)
        if broken_ratio >= 0.6 and _SOURCE_ORDER.get(src_letter, 5) < _SOURCE_ORDER["D"]:
            src_letter = "D"
            strategy_grade = src_letter + cred_digit
        elif broken_ratio >= 0.4 and _SOURCE_ORDER.get(src_letter, 5) < _SOURCE_ORDER["C"]:
            src_letter = "C"
            strategy_grade = src_letter + cred_digit

    strategy = {
        "name": entity_type,
        "auto_grade": strategy_grade,
        "admiralty_source": _split(strategy_grade)[0],
        "user_grade": None,
        "completeness_pct": completeness_pct,
        "comment": grade_comment_strategy(entity_type, strategy_grade, completeness_pct, []),
    }

    result = {
        "strategy": strategy,
        "tactics": tactics,
        "entity_type": entity_type,
        "blocked_tools": blocked_count,
    }
    if pyramid_summary:
        result["pyramid_summary"] = pyramid_summary
    return result


def backfill_scorecards() -> int:
    try:
        from app.routers.v3.db import fetch_all, execute
        import json

        rows = fetch_all(
            "SELECT run_id, trail, findings, query FROM research_trails WHERE scorecard IS NULL AND trail IS NOT NULL LIMIT 50"
        ) or []

        count = 0
        for row in rows:
            trail = row.get("trail")
            findings = row.get("findings")
            if not trail or not isinstance(trail, dict):
                continue

            scorecard = build_scorecard(
                trail=trail,
                findings=findings if isinstance(findings, list) else [],
                completeness_pct=0.0,
                entity_type="person",
            )

            execute(
                "UPDATE research_trails SET scorecard = %s WHERE run_id = %s",
                (json.dumps(scorecard), str(row["run_id"])),
            )
            count += 1

        return count
    except Exception as exc:
        log.warning("Scorecard backfill failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Match-weighted confidence: P(query | candidate), not P(candidate exists)
# ---------------------------------------------------------------------------
import datetime as _dt

_CURRENT_YEAR_QES = _dt.date.today().year
_FEMALE_QES = {"girl", "woman", "female", "lady"}
_MALE_QES   = {"boy", "man", "male", "guy"}
_WEAPON_QES = {"shotgun", "gun", "firearm", "weapon", "pistol", "rifle"}
_SPIDER_QES = {"spider", "spiderman", "spider-man", "noir", "silk", "venom", "marvel"}


def _primary_match_qes(primary_text: str, candidate: dict) -> bool:
    lower = primary_text.lower()
    genders = candidate.get("top_billed_genders") or []
    top_g = genders[0] if genders else 0
    if any(w in lower for w in _FEMALE_QES):
        return top_g == 1
    if any(w in lower for w in _MALE_QES):
        return top_g == 2
    return True


def _supporting_match_qes(supporting_text: str, candidate: dict) -> bool:
    if not supporting_text:
        return False
    lower = supporting_text.lower()
    ov = (candidate.get("overview") or "").lower()
    return any(w in lower and w in ov for w in _WEAPON_QES)


def _context_match_qes(context_text: str, candidate: dict) -> bool:
    if not context_text:
        return True
    lower = context_text.lower()
    title_ov = ((candidate.get("title") or "") + " " + (candidate.get("overview") or "")).lower()
    if any(w in lower for w in _SPIDER_QES):
        if any(w in title_ov for w in _SPIDER_QES):
            return True
    if candidate.get("actor_connection"):
        return True
    return False


def query_explanatory_score(candidate: dict, signals: dict, medium_type: str = "unknown") -> float:
    """P(query|candidate) confidence. Weights: PRIMARY 0.40, SUPPORTING 0.25,
    CONTEXT 0.15, recency 0.10, multi-branch 0.10, medium_type +0.15/-0.25."""
    score = 0.0
    if _primary_match_qes(signals.get("primary", ""), candidate):
        score += 0.40
    if _supporting_match_qes(signals.get("supporting", ""), candidate):
        score += 0.25
    if _context_match_qes(signals.get("context", ""), candidate):
        score += 0.15
    year = candidate.get("year")
    if year and year >= _CURRENT_YEAR_QES - 1:
        score += 0.10
    if len(candidate.get("branches") or []) >= 2:
        score += 0.10

    # Medium-type signal from PreFlight clarifications
    candidate_medium = str(candidate.get("medium_type") or candidate.get("source_class") or "").lower()
    if medium_type == "advertisement":
        if "ad" in candidate_medium or "campaign" in candidate_medium or "commercial" in candidate_medium:
            score += 0.15
        elif candidate_medium and "ad" not in candidate_medium:
            score -= 0.25

    return max(0.0, min(1.0, round(score, 2)))
