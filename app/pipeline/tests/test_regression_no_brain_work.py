"""Regression test: the canonical real-estate query must produce real brain work.

Pre-spec 2026-05-22, the canonical real-estate query completed in ~90ms with
zero tool calls because no tactic in the catalog declared compatibility with
the new skeleton phases (extract/gather/synthesize) — see PR #116's diagnosis.

After spec 2026-05-23 (this branch), the listings_gather tactic is registered
and real_estate.gather declares preferred_tactic_id=listings_gather, so the
strategist picks it and the brain actually runs.

This test asserts the observable outcome WITHOUT depending on PR #116's
diagnostic infrastructure (gate_result on trail rows, gate-detail endpoint).
Primary signal: run duration. Pre-spec no-op runs completed in 87-200ms;
post-spec the brain subprocess takes at least ~500ms to do real work.

When PR #116 merges, a follow-up should strengthen this test to assert
failing_check_kind != 'no_brain_work' via the gate-detail endpoint.

NOTE: marked @pytest.mark.functional — runs against the local stack.
"""
from __future__ import annotations

import os
import time
from datetime import datetime

import pytest
import requests


LOCAL_URL = os.environ.get("LOCAL_STACK_URL", "http://localhost:8000")
ADMIN_USER = os.environ.get("LOCAL_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("LOCAL_ADMIN_PASS", "admin")
CANONICAL_QUERY = "show all properties for rent in chicago with a budget of $500 to $1000"


def _parse_iso(ts: str) -> datetime:
    """Parse a Postgres-shaped ISO timestamp (may end with 'Z' or '+00:00')."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


@pytest.mark.functional
def test_canonical_query_invokes_a_tactic_and_does_real_work():
    """The canonical real-estate query must NOT be a silent no-op anymore.

    Before this spec, the run completed in <200ms with 0 tool calls because
    no tactic was compatible with the gather phase. After this spec, the run
    must either succeed with real work OR fail with a non-no_brain_work
    reason — and the run duration must reflect real subprocess work (>500ms).
    """
    r = requests.post(
        f"{LOCAL_URL}/v3/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
    )
    r.raise_for_status()
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    pre = requests.post(
        f"{LOCAL_URL}/v3/preflight",
        headers=headers,
        json={"query": CANONICAL_QUERY},
    )
    pre.raise_for_status()
    preflight = pre.json()

    confirm = requests.post(
        f"{LOCAL_URL}/v3/preflight/confirm",
        headers=headers,
        json={
            "query": CANONICAL_QUERY,
            # preflight returns the chosen strategy as `suggested_strategy`,
            # but the confirm endpoint takes it as `strategy_id`
            "strategy_id": preflight["suggested_strategy"],
            "envelope": preflight["envelope"],
            "start_run": True,
        },
    )
    confirm.raise_for_status()
    run_id = confirm.json()["run_id"]

    # Poll for terminal status — up to 120s
    deadline = time.time() + 120
    status = None
    body: dict = {}
    while time.time() < deadline:
        r = requests.get(f"{LOCAL_URL}/v3/pipelines/runs/{run_id}", headers=headers)
        body = r.json()
        status = body.get("status")
        if status in ("succeeded", "failed", "ask_user"):
            break
        time.sleep(2)
    assert status in ("succeeded", "ask_user", "failed"), (
        f"Run did not reach terminal status (got {status!r}). body={body}"
    )

    started = body.get("started_at")
    finished = body.get("finished_at")
    assert started and finished, f"run missing timestamps: {body}"

    delta_ms = (_parse_iso(finished) - _parse_iso(started)).total_seconds() * 1000
    # Pre-spec no_brain_work runs were 87-200ms. Even an Apify call costs >2s;
    # even ask_user from min_listings_returned should take at least the
    # Apify call duration. 500ms catches the pure-Python no-op pattern.
    assert delta_ms > 500, (
        f"Run completed in {delta_ms:.0f}ms — pre-spec no-op pattern detected. "
        f"Expected >500ms (real brain subprocess). body={body}"
    )

    # If the run failed, the error_message should NOT be no_brain_work-style.
    if status == "failed":
        err = (body.get("error_message") or "").lower()
        assert "no_brain_work" not in err and "no compatible tactic" not in err, (
            f"Run failed with no_brain_work-style error — tactic catalog regression. body={body}"
        )
