"""Benchmark reports API — persist + serve gold-set benchmark runs, and trigger
new runs from the admin UI.

- POST /v3/benchmarks/reports        ingest a report (run_benchmark posts here; API-key auth)
- GET  /v3/benchmarks/reports        list reports (admin)
- GET  /v3/benchmarks/reports/{id}   full report (admin)
- POST /v3/benchmarks/run            trigger a benchmark run in the background (admin)
- GET  /v3/benchmarks/run/status     is a run active? (admin)
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import require_api_key
from app.routers.v3.auth import require_admin
from app.routers.v3.db import fetch_all, fetch_one

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v3/benchmarks", tags=["v3-benchmarks"])

# Default leads gold-set items a UI-triggered run benchmarks.
_DEFAULT_ITEMS = [
    "leads-gen-fsbo-chicago-001",
    "leads-gen-rental-austin-001",
    "leads-gen-fsbo-phoenix-001",
    "leads-gen-agent-austin-001",
]

# In-process state for a UI-triggered run (single concurrent run).
_RUN_STATE: dict = {"active": False, "started_at": None, "proc": None, "items": []}


# ---------------------------------------------------------------------------
# Ingest + read
# ---------------------------------------------------------------------------

class ReportIn(BaseModel):
    label: str | None = None
    report: dict


def _summary(report: dict) -> tuple[float | None, int | None, float | None]:
    overall = (report.get("aggregates") or {}).get("overall") or {}
    return (
        overall.get("mean_score"),
        overall.get("total_items"),
        overall.get("gamed_pct"),
    )


@router.post("/reports", status_code=201)
def ingest_report(body: ReportIn, _key: str = Depends(require_api_key)) -> dict:
    """Store a benchmark report (called by run_benchmark after a run)."""
    mean_score, total_items, gamed_pct = _summary(body.report)
    row = fetch_one(
        """
        INSERT INTO benchmark_reports (label, mean_score, total_items, gamed_pct, report)
        VALUES (%s, %s, %s, %s, %s::jsonb)
        RETURNING id::text, created_at
        """,
        (body.label, mean_score, total_items, gamed_pct, json.dumps(body.report)),
    )
    log.info("benchmarks: ingested report id=%s mean_score=%s items=%s", row["id"], mean_score, total_items)
    return {"id": row["id"], "mean_score": mean_score, "total_items": total_items}


@router.get("/reports")
def list_reports(_user: dict = Depends(require_admin)) -> list[dict]:
    rows = fetch_all(
        """
        SELECT id::text, created_at, label, mean_score, total_items, gamed_pct
          FROM benchmark_reports
         ORDER BY created_at DESC
         LIMIT 100
        """,
        (),
    )
    return [
        {
            "id": r["id"],
            "created_at": str(r["created_at"]),
            "label": r["label"],
            "mean_score": r["mean_score"],
            "total_items": r["total_items"],
            "gamed_pct": r["gamed_pct"],
        }
        for r in rows
    ]


@router.get("/reports/{report_id}")
def get_report(report_id: str, _user: dict = Depends(require_admin)) -> dict:
    row = fetch_one(
        "SELECT id::text, created_at, label, report FROM benchmark_reports WHERE id = %s",
        (report_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    report = row["report"] if isinstance(row["report"], dict) else json.loads(row["report"])
    return {"id": row["id"], "created_at": str(row["created_at"]), "label": row["label"], "report": report}


# ---------------------------------------------------------------------------
# Run trigger (background subprocess; single concurrent run)
# ---------------------------------------------------------------------------

class RunIn(BaseModel):
    items: list[str] | None = None
    label: str | None = None


def _run_active() -> bool:
    proc = _RUN_STATE.get("proc")
    if _RUN_STATE.get("active") and proc is not None and proc.poll() is None:
        return True
    # process finished (or none) → clear stale active flag
    if _RUN_STATE.get("active") and (proc is None or proc.poll() is not None):
        _RUN_STATE["active"] = False
    return False


@router.post("/run", status_code=202)
def trigger_run(body: RunIn, _user: dict = Depends(require_admin)) -> dict:
    """Spawn a benchmark run in the background. The run posts its report back to
    /v3/benchmarks/reports on completion (appears in the list). Single concurrent
    run — returns 409 if one is already active. NOTE: a run spends real brain time
    (several minutes per item)."""
    if _run_active():
        raise HTTPException(status_code=409, detail="A benchmark run is already in progress")

    items = body.items or _DEFAULT_ITEMS
    api_key = os.getenv("INFO_BROKER_API_KEY", "")
    label = body.label or f"UI run {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    out_path = f"/tmp/bench_ui_{int(time.time())}.json"

    env = {
        **os.environ,
        "LOCAL_STACK_URL": "http://localhost:8000",
        "BENCH_USERNAME": os.getenv("BENCH_USERNAME", "admin"),
        "BENCH_PASSWORD": os.getenv("BENCH_PASSWORD", "admin"),
        "INFO_BROKER_API_KEY": api_key,
        # tell the CLI to POST its report back to this API on completion
        "BENCHMARK_INGEST_URL": "http://localhost:8000",
        "BENCHMARK_INGEST_LABEL": label,
        "BENCH_TIMEOUT_S": os.getenv("BENCH_TIMEOUT_S", "1200"),
    }
    cmd = [sys.executable, "-m", "benchmarks.run_benchmark", "--out-json", out_path,
           "--items", *items, "--log-level", "WARNING"]
    try:
        proc = subprocess.Popen(cmd, env=env, cwd="/app",
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        log.error("benchmarks: failed to spawn run: %s", exc)
        raise HTTPException(status_code=500, detail=f"Could not start run: {exc}")

    _RUN_STATE.update({"active": True, "started_at": datetime.now(timezone.utc).isoformat(),
                       "proc": proc, "items": items})
    log.info("benchmarks: started UI run pid=%s items=%s", proc.pid, items)
    return {"status": "started", "items": items, "label": label}


@router.get("/run/status")
def run_status(_user: dict = Depends(require_admin)) -> dict:
    active = _run_active()
    return {"active": active, "started_at": _RUN_STATE.get("started_at") if active else None,
            "items": _RUN_STATE.get("items") if active else []}
