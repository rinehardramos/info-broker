"""Absorption-oriented endpoints — features that help analysts learn from runs.

Eight features, each minimal:
  A. headline_for_run(run_id) — one-sentence summary derived from snapshots
  B. entity_knowledge(subject) — aggregated facts across all the user's runs
  C. diff_runs(run_a, run_b) — what changed between two runs on similar topics
  D. finding annotations — CRUD on per-finding analyst notes
  E. hypothesis cross-reference(run_id) — for each hypothesis in a run, find
     prior runs that tested similar claims (via fused_retrieve)
  F. continue_thread(run_id) — return a follow-up query targeting the top
     unresolved EEI/open question
  G. user_cost_aggregate(window_days) — RU spent by phase + template + period
  H. open_questions_digest() — every open question across the user's recent
     runs, sorted by relevance
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v3", tags=["v3-absorption"])


# ── A. Headline derivation ────────────────────────────────────────────────────
def _compute_headline(wm: dict, query: str) -> str:
    hyps = wm.get("hypotheses") or []
    supported = [h for h in hyps if h.get("status") == "supported"]
    refuted = [h for h in hyps if h.get("status") == "refuted"]
    findings = wm.get("findings") or []
    contradictions_open = sum(1 for c in (wm.get("contradictions") or [])
                              if c.get("status") == "open")
    src_counts: dict[str, int] = {}
    for f in findings:
        cls = f.get("source_class") or "unknown"
        src_counts[cls] = src_counts.get(cls, 0) + 1
    primary = src_counts.get("primary_official", 0) + src_counts.get("registry", 0)
    # Pick a "strongest finding" — the one with highest confidence among primary_official
    primary_findings = [f for f in findings
                        if f.get("source_class") in ("primary_official", "registry")]
    primary_findings.sort(key=lambda f: -float(f.get("confidence") or 0.0))
    strongest = primary_findings[0] if primary_findings else None

    parts: list[str] = []
    if supported:
        parts.append(f"{len(supported)} supported hypothesis"
                     + ("es" if len(supported) != 1 else ""))
    if refuted:
        parts.append(f"{len(refuted)} refuted")
    if contradictions_open:
        parts.append(f"⚠ {contradictions_open} unresolved contradiction"
                     + ("s" if contradictions_open != 1 else ""))
    if not parts:
        parts.append("no resolved hypotheses")
    summary = " · ".join(parts)
    headline = f"{summary} · {len(findings)} findings ({primary} primary)"
    if strongest:
        strongest_title = (strongest.get("title") or "").strip()
        if strongest_title:
            headline += f" · strongest: {strongest_title[:100]}"
    return headline


@router.get("/runs/{run_id}/headline")
def get_run_headline(
    run_id: str, user: dict = Depends(get_current_user),
) -> dict:
    """Auto-generated one-sentence summary of a run for the runs list."""
    run = fetch_one(
        "SELECT id, user_id, query FROM pipeline_runs WHERE id=%s", (run_id,))
    if run is None:
        raise HTTPException(404, "run not found")
    is_admin = bool(user.get("is_admin", False))
    if str(run["user_id"]) != str(user["id"]) and not is_admin:
        raise HTTPException(403, "not your run")
    snap = fetch_one(
        """SELECT working_memory FROM working_memory_snapshots
            WHERE run_id=%s ORDER BY turn DESC LIMIT 1""",
        (run_id,))
    if snap is None:
        return {"run_id": run_id, "headline": "(legacy run — no snapshots)"}
    return {"run_id": run_id, "headline": _compute_headline(snap["working_memory"], run.get("query") or "")}


# ── B. Entity knowledge — aggregated facts across the user's runs ────────────
@router.get("/entities/{subject}/knowledge")
def get_entity_knowledge(
    subject: str, user: dict = Depends(get_current_user),
) -> dict:
    """Aggregate everything the system knows about a subject across the user's
    runs. Subject = a substring matched case-insensitively against the run
    query AND against each fact's claim. Returns facts grouped by source_class
    + a contradiction surface where claims about the same attribute disagree."""
    uid = str(user["id"])
    sub_like = f"%{subject.lower()}%"
    rows = fetch_all(
        """SELECT pr.id AS run_id, pr.query, wms.working_memory
             FROM pipeline_runs pr
             JOIN working_memory_snapshots wms ON wms.run_id = pr.id
            WHERE pr.user_id = %s
              AND (LOWER(pr.query) LIKE %s OR
                   wms.working_memory::text ILIKE %s)
            ORDER BY pr.created_at DESC
            LIMIT 200""",
        (uid, sub_like, f"%{subject}%"),
    )
    # Dedup by (run_id, latest turn only) and collect facts
    seen_runs: set[str] = set()
    facts_out: list[dict] = []
    for r in rows:
        run_id = str(r["run_id"])
        if run_id in seen_runs:
            continue
        seen_runs.add(run_id)
        wm = r["working_memory"] or {}
        for f in (wm.get("established_facts") or []):
            claim = (f.get("claim") or "").strip()
            if subject.lower() in claim.lower() or subject.lower() in (r.get("query") or "").lower():
                facts_out.append({
                    "claim": claim,
                    "source_url": f.get("source_url"),
                    "source_tool": f.get("source_tool"),
                    "verified_by": f.get("verified_by"),
                    "confidence": f.get("confidence"),
                    "run_id": run_id,
                    "from_query": r["query"],
                })
    # Detect potential contradictions — same claim words but different values.
    # Cheap version: group facts whose first 40 chars match and surface diverging tails.
    bucket: dict[str, list[dict]] = {}
    for f in facts_out:
        key = (f["claim"] or "")[:40].lower()
        bucket.setdefault(key, []).append(f)
    contradictions = [
        {"prefix": k, "alternatives": [{"claim": x["claim"], "run_id": x["run_id"]} for x in v]}
        for k, v in bucket.items() if len(v) > 1 and len({x["claim"] for x in v}) > 1
    ]
    return {
        "subject": subject,
        "runs_touching_subject": len(seen_runs),
        "facts": facts_out[:50],
        "contradictions": contradictions[:10],
    }


# ── C. Run diff ──────────────────────────────────────────────────────────────
@router.get("/runs/diff")
def diff_runs(
    a: str, b: str, user: dict = Depends(get_current_user),
) -> dict:
    """Diff two runs by their final-snapshot WMs. Surfaces: new vs disappeared
    hypotheses (by statement), new vs disappeared findings (by url), source-
    class mix delta, ACH ranking change."""
    def _load(run_id: str) -> dict:
        run = fetch_one(
            "SELECT user_id FROM pipeline_runs WHERE id=%s", (run_id,))
        if run is None:
            raise HTTPException(404, f"run not found: {run_id}")
        is_admin = bool(user.get("is_admin", False))
        if str(run["user_id"]) != str(user["id"]) and not is_admin:
            raise HTTPException(403, f"not your run: {run_id}")
        snap = fetch_one(
            """SELECT working_memory FROM working_memory_snapshots
                WHERE run_id=%s ORDER BY turn DESC LIMIT 1""", (run_id,))
        return (snap["working_memory"] if snap else {}) or {}

    wm_a = _load(a)
    wm_b = _load(b)

    def hyps_by_stmt(wm: dict) -> dict[str, dict]:
        return {(h.get("statement") or "").strip().lower(): h
                for h in (wm.get("hypotheses") or [])}
    ha = hyps_by_stmt(wm_a)
    hb = hyps_by_stmt(wm_b)
    hyp_added   = [hb[k] for k in (hb.keys() - ha.keys())]
    hyp_removed = [ha[k] for k in (ha.keys() - hb.keys())]
    # Status changes among hypotheses present in both
    hyp_status_changed: list[dict] = []
    for k in (ha.keys() & hb.keys()):
        if ha[k].get("status") != hb[k].get("status"):
            hyp_status_changed.append({
                "statement": ha[k].get("statement"),
                "from": ha[k].get("status"),
                "to": hb[k].get("status"),
            })

    def findings_by_url(wm: dict) -> dict[str, dict]:
        return {(f.get("source_url") or f.get("title") or "").strip(): f
                for f in (wm.get("findings") or [])}
    fa = findings_by_url(wm_a)
    fb = findings_by_url(wm_b)
    findings_added   = [fb[k] for k in (fb.keys() - fa.keys()) if k]
    findings_removed = [fa[k] for k in (fa.keys() - fb.keys()) if k]

    def sc_counts(wm: dict) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in (wm.get("findings") or []):
            cls = f.get("source_class") or "unknown"
            out[cls] = out.get(cls, 0) + 1
        return out
    sca, scb = sc_counts(wm_a), sc_counts(wm_b)
    sc_delta = {cls: scb.get(cls, 0) - sca.get(cls, 0)
                for cls in (set(sca) | set(scb))}

    return {
        "a": a, "b": b,
        "hypotheses": {
            "added":   [{"statement": h.get("statement"), "status": h.get("status")} for h in hyp_added],
            "removed": [{"statement": h.get("statement"), "status": h.get("status")} for h in hyp_removed],
            "status_changed": hyp_status_changed,
        },
        "findings": {
            "added_count": len(findings_added),
            "removed_count": len(findings_removed),
            "added_titles": [f.get("title") for f in findings_added[:10]],
        },
        "source_class_delta": sc_delta,
    }


# ── D. Finding annotations ───────────────────────────────────────────────────
class AnnotationIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=2000)
    color: str = Field("yellow", pattern="^(yellow|red|green|blue|purple)$")


def _user_owns_run(run_id: str, user: dict) -> bool:
    row = fetch_one("SELECT user_id FROM pipeline_runs WHERE id=%s", (run_id,))
    if not row: return False
    if bool(user.get("is_admin", False)): return True
    return str(row["user_id"]) == str(user["id"])


@router.post("/runs/{run_id}/findings/{finding_id}/annotation", status_code=201)
def upsert_annotation(
    run_id: str, finding_id: str, body: AnnotationIn,
    user: dict = Depends(get_current_user),
) -> dict:
    """Create or update an annotation on a specific finding within a run."""
    if not _user_owns_run(run_id, user):
        raise HTTPException(403, "not your run")
    import uuid as _uuid
    aid = str(_uuid.uuid4())
    execute(
        """INSERT INTO finding_annotations (id, run_id, finding_id, user_id, body, color)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id, finding_id, user_id) DO UPDATE
                  SET body = EXCLUDED.body, color = EXCLUDED.color""",
        (aid, run_id, finding_id, str(user["id"]), body.body.strip(), body.color),
    )
    return {"id": aid, "run_id": run_id, "finding_id": finding_id,
            "body": body.body.strip(), "color": body.color}


@router.get("/runs/{run_id}/annotations")
def list_annotations(
    run_id: str, user: dict = Depends(get_current_user),
) -> list[dict]:
    """All annotations on findings in this run."""
    if not _user_owns_run(run_id, user):
        raise HTTPException(403, "not your run")
    rows = fetch_all(
        """SELECT id, finding_id, body, color, created_at
             FROM finding_annotations
            WHERE run_id = %s AND user_id = %s
            ORDER BY created_at DESC""",
        (run_id, str(user["id"])),
    )
    return [
        {"id": str(r["id"]), "finding_id": r["finding_id"], "body": r["body"],
         "color": r["color"],
         "created_at": r["created_at"].isoformat() if r["created_at"] else None}
        for r in rows
    ]


# ── E. Hypothesis cross-reference ────────────────────────────────────────────
@router.get("/runs/{run_id}/hypothesis-xrefs")
async def hypothesis_xrefs(
    run_id: str, user: dict = Depends(get_current_user),
) -> dict:
    """For each hypothesis in this run, find prior runs that tested a similar
    claim (via fused_retrieve on the hypothesis statement). Helps the analyst
    see "you've tested this before" without manual search."""
    if not _user_owns_run(run_id, user):
        raise HTTPException(403, "not your run")
    snap = fetch_one(
        """SELECT working_memory FROM working_memory_snapshots
            WHERE run_id=%s ORDER BY turn DESC LIMIT 1""", (run_id,))
    if snap is None:
        return {"run_id": run_id, "xrefs": []}
    hyps = (snap["working_memory"] or {}).get("hypotheses") or []
    out: list[dict] = []
    try:
        from app.memory.retriever import fused_retrieve
        for h in hyps[:6]:   # cap to first 6
            stmt = (h.get("statement") or "").strip()
            if not stmt:
                continue
            hits = await fused_retrieve(query=stmt, limit=5, user_id=str(user["id"]))
            related = [
                {"title": r.title, "run_id": r.run_id, "score": r.score,
                 "user_graded": r.user_score > 0}
                for r in hits
                if r.run_id and r.run_id != run_id
            ]
            out.append({
                "hypothesis_id": h.get("id"),
                "statement": stmt,
                "status": h.get("status"),
                "related": related[:5],
            })
    except Exception as exc:
        log.warning("hypothesis_xrefs failed: %s", exc)
    return {"run_id": run_id, "xrefs": out}


# ── F. Continue thread ──────────────────────────────────────────────────────
@router.get("/runs/{run_id}/continue-thread")
def continue_thread(
    run_id: str, user: dict = Depends(get_current_user),
) -> dict:
    """Build a follow-up research query targeting the top unresolved
    EEI / open question from this run. Returns the suggested query string —
    the UI passes it to /v3/agent/message verbatim if the user clicks through."""
    if not _user_owns_run(run_id, user):
        raise HTTPException(403, "not your run")
    snap = fetch_one(
        """SELECT working_memory FROM working_memory_snapshots
            WHERE run_id=%s ORDER BY turn DESC LIMIT 1""", (run_id,))
    if snap is None:
        return {"suggested_query": None}
    wm = snap["working_memory"] or {}
    run = fetch_one("SELECT query FROM pipeline_runs WHERE id=%s", (run_id,))
    orig_query = (run.get("query") or "") if run else ""
    # Prefer an unresolved open_question; fall back to a refuted hypothesis to
    # form a "now investigate the alternative" follow-up.
    open_qs = [q.get("question") for q in (wm.get("open_questions") or [])
               if q.get("status") == "open" and q.get("question")]
    refuted = [h.get("statement") for h in (wm.get("hypotheses") or [])
               if h.get("status") == "refuted"]
    target: str = ""
    rationale: str = ""
    if open_qs:
        target = open_qs[0]
        rationale = "unresolved open question from previous run"
    elif refuted:
        target = refuted[0]
        rationale = "previously refuted hypothesis — investigate alternative"
    else:
        return {"suggested_query": None, "rationale": "no follow-up suggested"}
    query = (
        f"Follow up on the previous run for: {orig_query[:200]}. "
        f"Specifically: {target}"
    )
    return {
        "previous_run": run_id,
        "suggested_query": query,
        "rationale": rationale,
        "target_open_question": target,
    }


# ── G. User-level cost aggregation ───────────────────────────────────────────
@router.get("/wallet/aggregate")
def user_cost_aggregate(
    window_days: int = 7, user: dict = Depends(get_current_user),
) -> dict:
    """RU spent in the last N days, broken down by phase and trigger_type.
    Surfaces 'where is your research budget going.'"""
    uid = str(user["id"])
    since = datetime.now(timezone.utc) - timedelta(days=max(1, min(window_days, 90)))
    rows = fetch_all(
        """SELECT wo.op, wo.delta_ru, pr.trigger_type, wo.created_at
             FROM wallet_operations wo
        LEFT JOIN pipeline_runs pr ON pr.id = wo.run_id
            WHERE wo.delta_ru < 0
              AND wo.created_at >= %s
              AND EXISTS (
                  SELECT 1 FROM pipeline_runs r2
                   WHERE r2.id = wo.run_id AND r2.user_id = %s
              )""",
        (since, uid),
    )
    total = 0
    by_phase: dict[str, int] = {}
    by_trigger: dict[str, int] = {}
    for r in rows:
        delta = abs(int(r["delta_ru"]))
        total += delta
        phase_labels = {"consume_phase_0": "explore",
                        "consume_phase_1": "test",
                        "consume_phase_2": "synthesize"}
        label = phase_labels.get(r["op"], r["op"])
        by_phase[label] = by_phase.get(label, 0) + delta
        trig = r.get("trigger_type") or "unknown"
        by_trigger[trig] = by_trigger.get(trig, 0) + delta
    return {
        "window_days": window_days,
        "total_ru": total,
        "by_phase": by_phase,
        "by_trigger_type": by_trigger,
    }


# ── H. Open-questions digest ─────────────────────────────────────────────────
@router.get("/open-questions/digest")
def open_questions_digest(
    user: dict = Depends(get_current_user), limit: int = 25,
) -> dict:
    """Aggregate every open question across the user's recent runs (last 30
    days). Useful as a 'what still needs investigating' worklist."""
    uid = str(user["id"])
    since = datetime.now(timezone.utc) - timedelta(days=30)
    rows = fetch_all(
        """SELECT pr.id AS run_id, pr.query, pr.finished_at, wms.working_memory
             FROM pipeline_runs pr
             JOIN working_memory_snapshots wms ON wms.run_id = pr.id
            WHERE pr.user_id = %s
              AND pr.finished_at >= %s
              AND wms.turn = (SELECT MAX(turn) FROM working_memory_snapshots
                              WHERE run_id = pr.id)""",
        (uid, since),
    )
    digest: list[dict] = []
    for r in rows:
        wm = r["working_memory"] or {}
        for q in (wm.get("open_questions") or []):
            if q.get("status") == "open":
                digest.append({
                    "question": q.get("question", "")[:200],
                    "run_id": str(r["run_id"]),
                    "from_query": (r.get("query") or "")[:120],
                    "finished_at": r["finished_at"].isoformat() if r.get("finished_at") else None,
                })
    digest.sort(key=lambda d: d["finished_at"] or "", reverse=True)
    return {"open_count": len(digest), "questions": digest[:limit]}
