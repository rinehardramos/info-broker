"""Working-memory snapshot endpoint (Path B observability).

GET /v3/runs/{run_id}/working-memory → list of all per-turn snapshots for a run,
oldest first. Used by the Result drawer's "Turns" tab to render the loop history.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v3", tags=["v3-working-memory"])


class HypothesisCommentIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)


class HypothesisCommentOut(BaseModel):
    id: str
    run_id: str
    hypothesis_id: str
    user_id: str
    body: str
    created_at: str


@router.get("/runs/{run_id}/working-memory")
async def get_working_memory(
    run_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Return all working-memory snapshots for a run, oldest first.

    The caller must own the run (or be an admin). Returns 404 if the run
    doesn't exist or 403 if the caller can't access it.
    """
    run = fetch_one(
        "SELECT id, user_id, query FROM pipeline_runs WHERE id = %s",
        (run_id,),
    )
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    # get_current_user returns a dict; access by key, not attribute.
    is_admin = bool(user.get("is_admin", False)) or user.get("role", "") == "admin"
    if str(run["user_id"]) != str(user["id"]) and not is_admin:
        raise HTTPException(status_code=403, detail="not your run")

    rows = fetch_all(
        """SELECT turn, phase, working_memory, created_at
             FROM working_memory_snapshots
            WHERE run_id = %s
            ORDER BY turn ASC""",
        (run_id,),
    )
    snapshots = []
    for r in rows:
        wm = r["working_memory"]
        # Counts are derived rather than relying on the brain to compute them.
        hyps = wm.get("hypotheses") or []
        open_hs = sum(1 for h in hyps if h.get("status") == "open")
        resolved_hs = sum(1 for h in hyps if h.get("status") in ("supported", "refuted"))
        # Source-class counts for this turn — surface the analytic-quality
        # mix at a glance ("3 primary_official, 2 news, 1 aggregator").
        sc_counts: dict[str, int] = {}
        # Aggregated deception signal for the UI banner.
        flagged = 0
        flag_counts: dict[str, int] = {}
        for f in (wm.get("findings") or []):
            cls = f.get("source_class") or "unknown"
            sc_counts[cls] = sc_counts.get(cls, 0) + 1
            risk = float(f.get("deception_risk") or 0.0)
            if risk >= 0.3:
                flagged += 1
            for flag in (f.get("deception_flags") or []):
                flag_counts[flag] = flag_counts.get(flag, 0) + 1
        # ACH ranking + matrix density for the Turns tab. Ranks hypotheses by
        # fewest inconsistencies (the load-bearing ACH rule).
        evidence = wm.get("evidence_matrix") or []
        ach_counts: list[dict] = []
        for h in (wm.get("hypotheses") or []):
            inc = sum(1 for s in evidence
                       if s.get("hypothesis_id") == h.get("id")
                       and s.get("consistency") == "inconsistent")
            con = sum(1 for s in evidence
                       if s.get("hypothesis_id") == h.get("id")
                       and s.get("consistency") == "consistent")
            ach_counts.append({
                "hypothesis_id": h.get("id"),
                "statement": h.get("statement") or "",
                "status": h.get("status") or "open",
                "inconsistencies": inc,
                "consistencies": con,
            })
        ach_counts.sort(key=lambda x: (x["inconsistencies"], -x["consistencies"]))
        snapshots.append({
            "turn": r["turn"],
            "phase": r["phase"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "counts": {
                "hypotheses_open": open_hs,
                "hypotheses_resolved": resolved_hs,
                "facts": len(wm.get("established_facts") or []),
                "findings": len(wm.get("findings") or []),
                "open_questions": sum(
                    1 for q in (wm.get("open_questions") or [])
                    if q.get("status") == "open"
                ),
                "strategies_tried": len(wm.get("strategies_attempted") or []),
            },
            "source_classes": sc_counts,
            "ach_ranking": ach_counts,
            "evidence_matrix_size": len(evidence),
            "deception": {
                "flagged_count": flagged,
                "flag_counts": flag_counts,
            },
            "working_memory": wm,   # full snapshot for click-to-expand
        })
    # The synthesis summary lives on the final snapshot (set by the brain in
    # the synthesize-phase turn). Surface it at the top level so the UI can
    # display it without parsing the full WM blob.
    final_summary = ""
    decay_summary = {"decayed_prior_count": 0, "max_decay_pct": 0}
    pir_summary: dict | None = None
    if snapshots:
        last_wm = snapshots[-1]["working_memory"]
        final_summary = (last_wm.get("synthesis_summary") or "").strip()
        # Decay summary for the UI banner — count of cross-run priors that
        # lost ≥10% of their original confidence due to age.
        for p in (last_wm.get("cross_run_priors") or []):
            base = int(p.get("base_confidence") or 0)
            dec = int(p.get("decayed_confidence") or 0)
            if base > 0 and dec < base:
                pct = round(100 * (1 - dec / base))
                if pct >= 10:
                    decay_summary["decayed_prior_count"] += 1
                    decay_summary["max_decay_pct"] = max(decay_summary["max_decay_pct"], pct)
    # PIR coverage on the final snapshot's findings — derived view, no schema changes.
    if snapshots:
        try:
            from app.pipeline.fusion.pir import (
                infer_entity_type, decompose_query_to_pirs,
                map_findings_to_pirs, generate_coverage_report,
            )
            query_text = run.get("query") or ""
            entity_type = infer_entity_type(query_text)
            final_findings_raw = snapshots[-1]["working_memory"].get("findings") or []
            # Adapt WM finding shape to PIR finding shape (it expects 'source' field
            # and reads 'content'+'title').
            adapted = [
                {"title": f.get("title", ""), "content": f.get("content", ""),
                 "source": f.get("source_tool") or f.get("source_class") or "unknown"}
                for f in final_findings_raw
            ]
            pirs = decompose_query_to_pirs(query_text, entity_type)
            pirs = map_findings_to_pirs(pirs, adapted)
            report = generate_coverage_report(pirs)
            pir_summary = {
                "entity_type": entity_type,
                "overall_coverage": report["overall_coverage"],
                "resolved_eeis": report["resolved_eeis"],
                "total_eeis": report["total_eeis"],
                "gaps": report["gaps"][:6],
                "pir_summaries": [
                    {"name": p["name"], "coverage": p["coverage"],
                     "confidence": p["confidence"]}
                    for p in report["pirs"]
                ],
            }
        except Exception as exc:
            log.warning("PIR coverage on snapshot endpoint failed: %s", exc)
    # Per-phase RU cost derived from wallet_operations — surfaces the
    # cost-dashboard view directly on the snapshot response.
    cost_summary: dict | None = None
    try:
        ops = fetch_all(
            """SELECT op, delta_ru FROM wallet_operations
                WHERE run_id = %s AND op LIKE 'consume_phase_%%'""",
            (run_id,),
        )
        if ops:
            phase_labels = {"consume_phase_0": "explore",
                            "consume_phase_1": "test",
                            "consume_phase_2": "synthesize"}
            by_phase: dict[str, int] = {}
            for o in ops:
                label = phase_labels.get(o["op"], o["op"])
                by_phase[label] = by_phase.get(label, 0) + abs(int(o["delta_ru"]))
            cost_summary = {
                "total_ru": sum(by_phase.values()),
                "by_phase": by_phase,
            }
    except Exception as exc:
        log.warning("cost summary computation failed (non-fatal): %s", exc)

    return {
        "run_id": run_id,
        "snapshots": snapshots,
        "total_turns": len(snapshots),
        "synthesis_summary": final_summary,
        "decay": decay_summary,
        "pir": pir_summary,
        "cost": cost_summary,
    }


# ── Hypothesis comments ──────────────────────────────────────────────────────
def _user_can_access_run(run_id: str, user: dict) -> bool:
    """Owner or admin only. Same gate as the snapshot endpoint."""
    row = fetch_one("SELECT user_id FROM pipeline_runs WHERE id=%s", (run_id,))
    if row is None:
        return False
    is_admin = bool(user.get("is_admin", False)) or user.get("role", "") == "admin"
    return str(row["user_id"]) == str(user["id"]) or is_admin


@router.get("/runs/{run_id}/hypotheses/{hypothesis_id}/comments")
def list_hypothesis_comments(
    run_id: str,
    hypothesis_id: str,
    user: dict = Depends(get_current_user),
) -> list[dict]:
    if not _user_can_access_run(run_id, user):
        raise HTTPException(status_code=403, detail="not your run")
    rows = fetch_all(
        """SELECT id, run_id, hypothesis_id, user_id, body, created_at
             FROM hypothesis_comments
            WHERE run_id = %s AND hypothesis_id = %s
            ORDER BY created_at ASC""",
        (run_id, hypothesis_id),
    )
    return [
        {
            "id": str(r["id"]),
            "run_id": str(r["run_id"]),
            "hypothesis_id": r["hypothesis_id"],
            "user_id": str(r["user_id"]),
            "body": r["body"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


@router.post("/runs/{run_id}/hypotheses/{hypothesis_id}/comments", status_code=201)
def post_hypothesis_comment(
    run_id: str,
    hypothesis_id: str,
    body: HypothesisCommentIn,
    user: dict = Depends(get_current_user),
) -> dict:
    if not _user_can_access_run(run_id, user):
        raise HTTPException(status_code=403, detail="not your run")
    import uuid as _uuid
    comment_id = str(_uuid.uuid4())
    execute(
        """INSERT INTO hypothesis_comments
                  (id, run_id, hypothesis_id, user_id, body)
               VALUES (%s, %s, %s, %s, %s)""",
        (comment_id, run_id, hypothesis_id, str(user["id"]), body.body.strip()),
    )
    return {"id": comment_id, "run_id": run_id, "hypothesis_id": hypothesis_id,
            "body": body.body.strip()}
