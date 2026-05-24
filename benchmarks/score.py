"""Scoring + anti-gaming guards for the benchmark harness.

This module is intentionally PURE — ``score_item`` and all its helpers are
side-effect-free functions that operate on plain dicts. They can be unit-tested
without a running stack, a database, or any network access.

Anti-gaming guards (hard-fail → item_score=0)
----------------------------------------------
1. TRAINING_ONLY   — no real tool calls OR all branches have
                     source_class ∈ {training_knowledge}.
2. UNREGISTERED_TOOL — any technique_id in the trail branches that is not
                       in the registered technique catalog.
3. SKIPPED_PHASES  — the resolved strategy's declared phases did not all run
                     (trail.phases subset vs strategy.phases).
4. RAG_SHORTCUT    — an expected_fact with must_be_live=True was satisfied
                     only via source_class == "prior_research".

Scoring (when no guard trips)
------------------------------
- Per expected_fact: keyword/normalized-substring match against the run's
  findings text + a citation check.
- coverage = matched_facts / total_expected_facts
- source_quality = weighted average of the best source_class seen across
  matched facts (live_official/primary_official > live_search > prior_research
  > training_knowledge).
- item_score = coverage × source_quality  (both in [0, 1])

Aggregation
-----------
``aggregate_scores`` groups per-item results by template / mode / strategy /
tactic / technique and emits per-group mean scores.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Source-class quality weights
# ---------------------------------------------------------------------------

#: Quality weight per source_class, used for source_quality calculation.
#: Higher = better provenance. Unknown classes get 0.1 (penalised, not zeroed).
SOURCE_CLASS_WEIGHTS: dict[str, float] = {
    "live_official": 1.0,
    "primary_official": 1.0,
    "registry": 0.95,
    "live_search": 0.75,
    "news": 0.65,
    "aggregator": 0.55,
    "social": 0.45,
    "prior_research": 0.30,
    "training_knowledge": 0.10,
    "unknown": 0.10,
}

#: Source classes that count as "not live" for the RAG_SHORTCUT guard.
_NON_LIVE_CLASSES: frozenset[str] = frozenset({"prior_research", "training_knowledge"})

#: Source classes that count as "training only" for the TRAINING_ONLY guard.
_TRAINING_CLASSES: frozenset[str] = frozenset({"training_knowledge"})


# ---------------------------------------------------------------------------
# Registered technique catalog loader
# ---------------------------------------------------------------------------

def load_registered_technique_ids(
    techniques_dir: Path | None = None,
) -> frozenset[str]:
    """Return the set of technique ids registered in the catalog.

    Loads from ``app/pipeline/catalogs/registries/techniques/`` relative to
    the repo root (two levels above this file). Accepts an explicit override
    path for testing.

    Falls back to an empty frozenset (not a hard error) so callers can decide
    whether a missing catalog is fatal.
    """
    if techniques_dir is None:
        # Resolve relative to this file: benchmarks/ → repo_root/
        repo_root = Path(__file__).resolve().parent.parent
        techniques_dir = (
            repo_root / "app" / "pipeline" / "catalogs" / "registries" / "techniques"
        )

    if not techniques_dir.exists():
        return frozenset()

    try:
        from app.pipeline.catalogs.loader import load_catalog  # type: ignore[import]

        catalog = load_catalog("technique", techniques_dir)
        return frozenset(catalog.keys())
    except Exception:
        # Fallback: parse TECHNIQUE["id"] from each file without importing app
        ids: set[str] = set()
        for path in techniques_dir.glob("*.py"):
            if path.name.startswith("_"):
                continue
            text = path.read_text(errors="ignore")
            m = re.search(r'"id"\s*:\s*"([^"]+)"', text)
            if m:
                ids.add(m.group(1))
        return frozenset(ids)


# ---------------------------------------------------------------------------
# Text-matching helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower().strip())


def _salient_tokens(claim: str) -> list[str]:
    """Extract meaningful tokens from a claim string.

    Strips common stop-words so that a claim like "Tim Cook is the CEO of
    Apple Inc" yields tokens like ["tim", "cook", "ceo", "apple", "inc"].
    """
    _STOPWORDS = {
        "is", "are", "was", "were", "the", "a", "an", "of", "in", "at",
        "to", "for", "by", "and", "or", "that", "this", "it", "its",
        "as", "on", "with", "from", "has", "have", "had", "be", "been",
        "who", "what", "when", "where", "which", "their", "he", "she",
        "they", "them", "his", "her",
    }
    tokens = re.findall(r"[a-z0-9]+", _normalize(claim))
    salient = [t for t in tokens if t not in _STOPWORDS and len(t) > 1]
    return salient


def _findings_text(findings: list[dict]) -> str:
    """Concatenate all text-bearing fields from a findings list into one blob."""
    parts: list[str] = []
    for f in findings:
        for field in ("claim", "evidence_summary", "evidence_snippet",
                      "candidate_name", "summary", "text", "content"):
            val = f.get(field)
            if val and isinstance(val, str):
                parts.append(val)
    return " ".join(parts)


def _claim_matches(claim: str, findings_blob: str) -> bool:
    """Return True when enough salient tokens of *claim* appear in *findings_blob*.

    Threshold: ≥ 60 % of salient tokens must be present (handles paraphrasing).
    Minimum threshold: at least 1 token must match.
    """
    tokens = _salient_tokens(claim)
    if not tokens:
        return False
    blob = _normalize(findings_blob)
    matched = sum(1 for t in tokens if t in blob)
    return matched / len(tokens) >= 0.60


def _has_citation(findings: list[dict]) -> bool:
    """Return True when at least one finding has a non-empty source_url."""
    return any(
        bool(f.get("source_url") or f.get("authoritative_source"))
        for f in findings
    )


def _best_source_class(findings: list[dict]) -> str:
    """Return the source_class with the highest quality weight across all findings."""
    best_weight = 0.0
    best_class = "unknown"
    for f in findings:
        sc = f.get("source_class") or "unknown"
        w = SOURCE_CLASS_WEIGHTS.get(sc, 0.10)
        if w > best_weight:
            best_weight = w
            best_class = sc
    return best_class


# ---------------------------------------------------------------------------
# Anti-gaming guard helpers
# ---------------------------------------------------------------------------

def _guard_training_only(trail: dict) -> str | None:
    """Guard 1 — training_only: no real tool calls or all branches are training-only.

    Returns the guard name if tripped, else None.
    """
    tool_calls: int = trail.get("tool_calls", 0)
    branches: list[dict] = trail.get("branches", [])

    # Explicit tool_calls counter at trail level is the fastest check.
    if isinstance(tool_calls, int) and tool_calls == 0 and branches:
        return "training_only"

    # All branches have source_class in the training set.
    if branches and all(
        (b.get("source_class") or "training_knowledge") in _TRAINING_CLASSES
        for b in branches
    ):
        return "training_only"

    # No branches at all — nothing was researched.
    if not branches:
        return "training_only"

    return None


def _guard_unregistered_tools(
    trail: dict,
    registered_ids: frozenset[str],
) -> str | None:
    """Guard 2 — unregistered_tool: any technique_id not in the catalog.

    Returns the guard name if tripped, else None.
    Skips the check when registered_ids is empty (catalog unavailable).
    """
    if not registered_ids:
        return None  # Can't check — skip

    branches: list[dict] = trail.get("branches", [])
    for branch in branches:
        tid = branch.get("technique_id") or ""
        if tid and tid not in registered_ids:
            return "unregistered_tool"

    return None


def _guard_skipped_phases(
    trail: dict,
    strategy_phases: list[str],
) -> str | None:
    """Guard 3 — skipped_phases: a required strategy phase did not run.

    Compares the trail's ``phases`` list against *strategy_phases*.
    Returns the guard name if any required phase is absent, else None.
    """
    if not strategy_phases:
        return None  # No declared phases to check against

    phases_ran: list[str] = trail.get("phases", [])
    ran_set = set(phases_ran)
    for required_phase in strategy_phases:
        if required_phase not in ran_set:
            return "skipped_phases"

    return None


def _guard_rag_shortcut(
    expected_facts: list[dict],
    findings: list[dict],
    findings_blob: str,
) -> str | None:
    """Guard 4 — rag_shortcut: a must_be_live fact matched only via prior_research.

    For each expected_fact with must_be_live=True that DID match the findings,
    check whether EVERY finding that could supply that match has a non-live
    source_class. If so, the shortcut guard fires.

    Returns the guard name if tripped, else None.
    """
    live_facts = [f for f in expected_facts if f.get("must_be_live")]
    if not live_facts:
        return None

    # Build a list of (claim, source_classes_that_matched) from findings.
    # A finding "contributes" to a claim if its text helps the claim match.
    for fact in live_facts:
        claim = fact.get("claim", "")
        if not _claim_matches(claim, findings_blob):
            # Fact didn't match at all — skipped_phases or coverage handles this;
            # not a RAG shortcut.
            continue

        # The fact DID match. Check whether any contributing finding is live.
        tokens = _salient_tokens(claim)
        contributing: list[dict] = []
        for fd in findings:
            fd_text = " ".join(
                str(fd.get(field, ""))
                for field in ("claim", "evidence_summary", "evidence_snippet",
                              "candidate_name", "summary", "text", "content")
            )
            fd_tokens = set(re.findall(r"[a-z0-9]+", _normalize(fd_text)))
            overlap = sum(1 for t in tokens if t in fd_tokens)
            if overlap / max(len(tokens), 1) >= 0.50:
                contributing.append(fd)

        if not contributing:
            continue  # Weird edge-case — no individual finding matched; skip

        # If ALL contributing findings are non-live, the guard fires.
        all_non_live = all(
            (fd.get("source_class") or "unknown") in _NON_LIVE_CLASSES
            for fd in contributing
        )
        if all_non_live:
            return "rag_shortcut"

    return None


# ---------------------------------------------------------------------------
# Per-item scoring
# ---------------------------------------------------------------------------

def score_item(
    gold_item: dict,
    trail: dict,
    findings: list[dict],
    *,
    registered_technique_ids: frozenset[str] | None = None,
    strategy_phases: list[str] | None = None,
) -> dict[str, Any]:
    """Score a single benchmark item against its run output.

    This function is PURE — no I/O, no side effects.

    Parameters
    ----------
    gold_item:
        The gold-set item dict (id, query, expected_facts, domain, …).
    trail:
        The ``trail`` JSON blob from the ``research_trails`` DB row.
        Expected keys: ``branches``, ``phases``, ``phases_full``, ``tool_calls``.
    findings:
        The ``findings`` JSON list from the ``research_trails`` DB row.
        Each finding is a dict with optional keys: claim, evidence_summary,
        source_class, source_url, technique_id, etc.
    registered_technique_ids:
        Frozenset of technique ids from the catalog. Pass None to skip guard 2.
    strategy_phases:
        List of phase ids the resolved strategy declares. Pass None to skip guard 3.

    Returns
    -------
    dict with keys:
        item_id          : str
        item_score       : float  — 0.0 if gamed, else coverage * source_quality
        coverage         : float  — matched / expected (0.0 if gamed)
        source_quality   : float  — weighted source class score (0.0 if gamed)
        gaming_flags     : list[str] — empty when clean, else guard name(s) tripped
        fact_matches     : list[dict] — per-expected-fact match detail
        tripped_guard    : str | None — first guard name that fired (for report)
    """
    item_id: str = gold_item.get("id", "unknown")
    expected_facts: list[dict] = gold_item.get("expected_facts", [])

    # Resolve registered technique ids (lazy load catalog if not supplied)
    if registered_technique_ids is None:
        registered_technique_ids = load_registered_technique_ids()

    # -----------------------------------------------------------------------
    # Anti-gaming guards — evaluated in order; first tripped guard wins.
    # -----------------------------------------------------------------------
    gaming_flags: list[str] = []

    guard1 = _guard_training_only(trail)
    if guard1:
        gaming_flags.append(guard1)

    guard2 = _guard_unregistered_tools(trail, registered_technique_ids)
    if guard2:
        gaming_flags.append(guard2)

    if strategy_phases is not None:
        guard3 = _guard_skipped_phases(trail, strategy_phases)
        if guard3:
            gaming_flags.append(guard3)

    # Build findings blob for text matching (needed for guard 4 + scoring)
    findings_blob = _findings_text(findings)

    guard4 = _guard_rag_shortcut(expected_facts, findings, findings_blob)
    if guard4:
        gaming_flags.append(guard4)

    tripped_guard: str | None = gaming_flags[0] if gaming_flags else None

    # If ANY guard tripped, item_score = 0 immediately.
    if gaming_flags:
        fact_matches = [
            {
                "claim": f.get("claim", ""),
                "matched": False,
                "has_citation": False,
                "source_class": None,
                "score": 0.0,
                "skip_reason": f"gaming guard: {tripped_guard}",
            }
            for f in expected_facts
        ]
        return {
            "item_id": item_id,
            "item_score": 0.0,
            "coverage": 0.0,
            "source_quality": 0.0,
            "gaming_flags": gaming_flags,
            "tripped_guard": tripped_guard,
            "fact_matches": fact_matches,
        }

    # -----------------------------------------------------------------------
    # Per-fact matching
    # -----------------------------------------------------------------------
    matched_count = 0
    quality_weights: list[float] = []
    fact_matches: list[dict] = []

    for fact in expected_facts:
        claim = fact.get("claim", "")
        matched = _claim_matches(claim, findings_blob)
        has_cite = _has_citation(findings) if matched else False
        best_sc = _best_source_class(findings) if matched else "unknown"
        sc_weight = SOURCE_CLASS_WEIGHTS.get(best_sc, 0.10) if matched else 0.0

        # A fact is "matched" only when both text match AND citation present.
        fact_matched = matched and has_cite
        if fact_matched:
            matched_count += 1
            quality_weights.append(sc_weight)

        fact_matches.append({
            "claim": claim,
            "matched": fact_matched,
            "text_matched": matched,
            "has_citation": has_cite,
            "source_class": best_sc if matched else None,
            "source_quality_weight": sc_weight,
            "score": sc_weight if fact_matched else 0.0,
        })

    total = len(expected_facts)
    coverage: float = matched_count / total if total > 0 else 0.0
    source_quality: float = (
        sum(quality_weights) / len(quality_weights) if quality_weights else 0.0
    )
    item_score: float = coverage * source_quality

    return {
        "item_id": item_id,
        "item_score": round(item_score, 4),
        "coverage": round(coverage, 4),
        "source_quality": round(source_quality, 4),
        "gaming_flags": gaming_flags,
        "tripped_guard": tripped_guard,
        "fact_matches": fact_matches,
    }


# ---------------------------------------------------------------------------
# Aggregate reporting
# ---------------------------------------------------------------------------

def aggregate_scores(
    results: list[dict],
    run_metadata: list[dict] | None = None,
) -> dict[str, Any]:
    """Aggregate per-item scores by template / mode / strategy / tactic / technique.

    Parameters
    ----------
    results:
        List of dicts from ``score_item`` calls.
    run_metadata:
        Optional list of per-item run metadata dicts (same index as results).
        Each may contain: strategy, mode, template, tactic_ids, technique_ids.

    Returns
    -------
    dict with keys:
        overall   : {mean_score, total_items, gamed_items, gamed_pct}
        by_domain : {domain: {mean_score, n}}
        by_strategy : {strategy_id: {mean_score, n}}
        by_mode   : {mode: {mean_score, n}}
        by_technique : {technique_id: {mean_score, n}}
    """
    if not results:
        return {"overall": {"mean_score": 0.0, "total_items": 0, "gamed_items": 0, "gamed_pct": 0.0}}

    meta: list[dict] = run_metadata or [{} for _ in results]

    total = len(results)
    gamed = sum(1 for r in results if r.get("gaming_flags"))
    all_scores = [r["item_score"] for r in results]
    overall_mean = sum(all_scores) / total if total else 0.0

    def _group_mean(key: str) -> dict[str, dict]:
        groups: dict[str, list[float]] = {}
        for r, m in zip(results, meta):
            val = m.get(key) or r.get(key) or "unknown"
            groups.setdefault(val, []).append(r["item_score"])
        return {k: {"mean_score": round(sum(v) / len(v), 4), "n": len(v)} for k, v in groups.items()}

    # Technique aggregation: one result may have multiple techniques
    by_technique: dict[str, list[float]] = {}
    for r, m in zip(results, meta):
        for tid in m.get("technique_ids") or []:
            by_technique.setdefault(tid, []).append(r["item_score"])

    return {
        "overall": {
            "mean_score": round(overall_mean, 4),
            "total_items": total,
            "gamed_items": gamed,
            "gamed_pct": round(gamed / total * 100, 1) if total else 0.0,
        },
        "by_domain": _group_mean("domain"),
        "by_strategy": _group_mean("strategy"),
        "by_mode": _group_mean("mode"),
        "by_template": _group_mean("template"),
        "by_technique": {
            k: {"mean_score": round(sum(v) / len(v), 4), "n": len(v)}
            for k, v in by_technique.items()
        },
    }


# ---------------------------------------------------------------------------
# Human-readable summary
# ---------------------------------------------------------------------------

def render_summary_table(
    item_results: list[dict],
    aggregates: dict[str, Any],
) -> str:
    """Return a plain-text summary table for console / log output."""
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("BENCHMARK RESULTS — per-item")
    lines.append("=" * 72)
    header = f"{'ID':<28} {'SCORE':>6} {'COV':>6} {'SQ':>6} {'GUARD':<20}"
    lines.append(header)
    lines.append("-" * 72)
    for r in item_results:
        guard = r.get("tripped_guard") or "-"
        lines.append(
            f"{r['item_id']:<28} {r['item_score']:>6.3f} "
            f"{r['coverage']:>6.3f} {r['source_quality']:>6.3f} "
            f"{guard:<20}"
        )
    lines.append("=" * 72)

    ov = aggregates.get("overall", {})
    lines.append(
        f"OVERALL  mean={ov.get('mean_score', 0):.3f}  "
        f"items={ov.get('total_items', 0)}  "
        f"gamed={ov.get('gamed_items', 0)} ({ov.get('gamed_pct', 0):.1f}%)"
    )
    lines.append("")

    for group_key in ("by_strategy", "by_mode", "by_domain"):
        grp = aggregates.get(group_key, {})
        if grp:
            lines.append(f"  {group_key}:")
            for name, stats in sorted(grp.items()):
                lines.append(
                    f"    {name:<28} mean={stats['mean_score']:.3f}  n={stats['n']}"
                )

    return "\n".join(lines)
