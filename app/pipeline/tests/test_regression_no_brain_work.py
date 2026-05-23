"""Regression test for the triggering incident (spec §"Regression test").

Given the canonical query, the result must be EITHER
  (status == "succeeded" AND tool_calls > 0 AND findings > 0)
  OR
  (status == "ask_user" AND failing_check_kind is not None and != "")

The 118ms-empty-success pattern is inadmissible.

NOTE: This test runs against the live local docker compose stack.
Mark with @pytest.mark.functional and only run when LOCAL_STACK_URL is set.

Verified API flow (confirmed against local stack 2026-05-22):
  Step 1 — Login:
    POST /v3/auth/login {"username":..., "password":...}
    → {"access_token": "..."}

  Step 2 — Classify query to get strategy + envelope:
    POST /v3/preflight {"query": ...}
    → {"suggested_strategy": "real_estate", "envelope": {...}, ...}

  Step 3 — Reserve RU and start engine_v2 run:
    POST /v3/preflight/confirm {"query":..., "strategy_id":..., "envelope":..., "start_run": true}
    → {"run_id": "...", "hold_id": "...", "held_ru": ...}

  Step 4 — Poll for terminal status (engine_v2 writes pipeline_run with trigger_type="agent"):
    GET /v3/pipelines/runs/{run_id}
    → {"id":..., "status": "ask_user"|"succeeded"|"failed", ...}

  Step 5 — Verify gate detail (admin only):
    GET /v3/pipelines/runs/{run_id}/gate-detail
    → {"run_id":..., "phase_id":..., "gate_result": {"failing_check_kind":...}}

NOTE on the "succeeded" branch:
  The canonical real-estate query currently triggers the no_brain_work gate immediately
  (engine_v2 skips the real brain because the strategy classifies it as outside scope).
  If a future code change actually wires a real-estate brain that executes tool calls,
  the succeeded branch assertion (tool_calls > 0 AND findings > 0) will catch any silent
  regression where the brain runs but produces no results.
"""
import os
import time
import pytest
import requests

LOCAL_URL = os.environ.get("LOCAL_STACK_URL", "http://localhost:8000")
ADMIN_USER = os.environ.get("LOCAL_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("LOCAL_ADMIN_PASS", "admin")
CANONICAL_QUERY = "show all properties for rent in chicago with a budget of $500 to $1000"


@pytest.mark.functional
def test_canonical_query_cannot_silently_no_op():
    # ── Step 1: Login ─────────────────────────────────────────────────────────
    r = requests.post(
        f"{LOCAL_URL}/v3/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
    )
    r.raise_for_status()
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # ── Step 2: Classify query → strategy + envelope ──────────────────────────
    r = requests.post(
        f"{LOCAL_URL}/v3/preflight",
        headers=headers,
        json={"query": CANONICAL_QUERY},
    )
    r.raise_for_status()
    pf = r.json()
    strategy_id = pf["suggested_strategy"]
    envelope = pf["envelope"]
    # Remove the "mode" key from the envelope if present — DialsIn schema doesn't accept it
    envelope_body = {
        k: v for k, v in envelope.items()
        if k in ("capability", "hypothesis_count", "depth", "speed", "resource")
    }

    # ── Step 3: Reserve RU + start engine_v2 run ──────────────────────────────
    # POST /v3/preflight/confirm with start_run=true triggers engine_v2 as a
    # background asyncio task. The response includes the run_id immediately.
    r = requests.post(
        f"{LOCAL_URL}/v3/preflight/confirm",
        headers=headers,
        json={
            "query": CANONICAL_QUERY,
            "strategy_id": strategy_id,
            "envelope": envelope_body,
            "start_run": True,
        },
    )
    r.raise_for_status()
    confirm = r.json()
    run_id = confirm["run_id"]
    assert run_id, f"Expected run_id in confirm response, got: {confirm}"

    # ── Step 4: Poll for terminal status (up to 60s) ──────────────────────────
    deadline = time.time() + 60
    status = None
    body = {}
    while time.time() < deadline:
        r = requests.get(f"{LOCAL_URL}/v3/pipelines/runs/{run_id}", headers=headers)
        body = r.json()
        status = body.get("status")
        if status in ("succeeded", "failed", "ask_user"):
            break
        time.sleep(1)

    assert status in ("succeeded", "ask_user"), (
        f"Run did not reach terminal status: {status}, body={body}"
    )

    # ── Step 5: Fetch gate detail (admin only) ────────────────────────────────
    r = requests.get(
        f"{LOCAL_URL}/v3/pipelines/runs/{run_id}/gate-detail",
        headers=headers,
    )
    r.raise_for_status()
    gd = r.json()
    gate_result = gd.get("gate_result")

    if status == "succeeded":
        bs = (gate_result or {}).get("brain_summary", {})
        assert bs.get("tool_calls", 0) > 0, (
            f"succeeded with 0 tool calls — silent no-op regression. "
            f"run_id={run_id} gd={gd}"
        )
        assert bs.get("findings", 0) > 0, (
            f"succeeded with 0 findings — silent no-op regression. "
            f"run_id={run_id} gd={gd}"
        )
    elif status == "ask_user":
        kind = (gate_result or {}).get("failing_check_kind")
        assert kind, (
            f"ask_user without failing_check_kind — message regression. "
            f"run_id={run_id} gd={gd}"
        )
