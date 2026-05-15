"""Replay router — reconstruct UI state from a past run's research_trail.

The runStreamStore is per-session memory; navigating to a past run leaves
the live view empty (cards, phases, ranked_candidates, ach_matrix). This
endpoint returns a payload the frontend can use to seed the store as if
the events had just been replayed.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import fetch_one

router = APIRouter(prefix="/v3/runs", tags=["v3-replay"])


@router.get("/{run_id}/replay")
def get_replay(run_id: str, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Return seed payload for runStreamStore.

    Shape mirrors the in-memory RunStream state — phases, tacticians,
    cards (derived from findings), ranked_candidates, ach_matrix.
    """
    row = fetch_one(
        """SELECT id, run_id, query, trail, findings
             FROM research_trails
            WHERE run_id = %s""",
        (run_id,),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")

    trail = row["trail"] if isinstance(row["trail"], dict) else json.loads(row["trail"])
    findings_list = (
        row["findings"]
        if isinstance(row["findings"], list)
        else json.loads(row["findings"] or "[]")
    )

    branches: list[dict] = trail.get("branches", [])
    phases_full: list[dict] = trail.get("phases_full") or []

    # Derive phases dict: phase_id → PhaseState
    phases_state: dict[str, dict] = {}
    tacticians_state: dict[str, dict[int, dict]] = {}
    for p in phases_full:
        pid = p["phase_id"]
        phases_state[pid] = {
            "status": p.get("status", "passed"),
            "n_tacticians": p.get("metadata", {}).get("num_tacticians", 1),
            "distinct_candidate_names": p.get("distinct_candidate_names", []),
            "gate_status": "pass" if p.get("status") == "passed" else (
                "fail" if p.get("status") == "failed" else "ask_user"
            ),
        }
        tacticians_state[pid] = {}

    # Derive tacticians_state by slot from branches (one branch per finding)
    tacticians_seen: dict[tuple[str, int], dict] = {}
    for b in branches:
        pid = b.get("phase_id", "")
        slot = int(b.get("slot_idx", 0))
        key = (pid, slot)
        rec = tacticians_seen.setdefault(key, {
            "tactic_id": "",
            "forbidden_candidates": [],
            "candidate_names": [],
            "findings_count": 0,
            "specialist_calls": 0,
        })
        cand = b.get("candidate_name")
        if cand and cand not in rec["candidate_names"]:
            rec["candidate_names"].append(cand)
        rec["findings_count"] += 1
    for (pid, slot), rec in tacticians_seen.items():
        tacticians_state.setdefault(pid, {})[str(slot)] = rec

    # Cards — synthesize NodeCard-shaped entries from findings so
    # StreamingCardList renders them on resume.
    cards: list[dict] = []
    for i, f in enumerate(findings_list):
        cards.append({
            "nodeId": f.get("hypothesis_slot") is not None
                and f"{f.get('phase_id', '')}_{f.get('hypothesis_slot')}_{i}"
                or f"card_{i}",
            "nodeName": f.get("technique_id") or f.get("source_class", "finding"),
            "status": "succeeded",
            "preview": f.get("evidence_snippet") or f.get("evidence_summary", ""),
            "output": f,
            "sources": (
                [{"url": f.get("source_url"), "label": f.get("source_class", ""),
                  "source_class": f.get("source_class")}]
                if f.get("source_url") else []
            ),
            "confidence": f.get("confidence"),
            "startedAt": None,
            "finishedAt": None,
            "slotIdx": f.get("hypothesis_slot"),
            "phaseId": f.get("phase_id"),
        })

    return {
        "run_id": run_id,
        "query": row.get("query", ""),
        "status": trail.get("status", "unknown"),
        "terminate_reason": trail.get("terminate_reason"),
        "phases": phases_state,
        "tacticians": tacticians_state,
        "cards": cards,
        "ranked_candidates": trail.get("ranked_candidates", []),
        "ach_matrix": trail.get("ach_matrix"),
    }
