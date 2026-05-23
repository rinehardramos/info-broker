"""Real-environment functional test: canonical real-estate query reaches Apify.

Asserts:
  - The run completes (succeeded OR ask_user with the right kind) within 120s
  - On succeeded: tool_calls >= 1, invoked_tools contains 'apify_listings_search'
  - On ask_user: failing_check_kind == 'min_listings_returned' (Apify returned 0)
    — NEVER 'no_brain_work' (which would mean the listings_gather tactic wasn't picked)

Requires LOCAL_STACK_URL + admin creds + APIFY_API_TOKEN configured on
the API container.

Spec: docs/superpowers/specs/2026-05-23-research-skeleton-tactic-completion-design.md
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
def test_canonical_real_estate_query_invokes_apify_and_returns_listings():
    # Skip if APIFY_API_TOKEN is not configured — the test would fail with
    # a non-min_listings_returned failing_check_kind (missing key error),
    # which would surface as a false regression signal.
    if not os.environ.get("APIFY_API_TOKEN"):
        pytest.skip("APIFY_API_TOKEN not configured — skipping Apify functional test")

    # Login
    r = requests.post(
        f"{LOCAL_URL}/v3/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
    )
    r.raise_for_status()
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Use the preflight + confirm flow (per PR #116 Task 15 finding — agent/message
    # uses a different engine path that doesn't go through engine_v2 / the strategist)
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
            "strategy_id": preflight["suggested_strategy"],
            "envelope": preflight["envelope"],
            "start_run": True,
        },
    )
    confirm.raise_for_status()
    run_id = confirm.json()["run_id"]

    # Poll for terminal status (up to 120s — Apify scrape can be slow)
    deadline = time.time() + 120
    status = None
    body = {}
    while time.time() < deadline:
        r = requests.get(f"{LOCAL_URL}/v3/pipelines/runs/{run_id}", headers=headers)
        body = r.json()
        status = body.get("status")
        if status in ("succeeded", "failed", "ask_user"):
            break
        time.sleep(2)
    assert status in ("succeeded", "ask_user"), (
        f"Run did not reach terminal status (got {status!r}). body={body}"
    )

    # Fetch gate detail (admin only)
    r = requests.get(
        f"{LOCAL_URL}/v3/pipelines/runs/{run_id}/gate-detail",
        headers=headers,
    )
    r.raise_for_status()
    gd = r.json()
    gate_result = gd.get("gate_result") or {}
    brain_summary = gate_result.get("brain_summary") or {}
    invoked_tools = brain_summary.get("invoked_tools") or []

    if status == "succeeded":
        # Real Apify work expected
        assert brain_summary.get("tool_calls", 0) >= 1, (
            f"succeeded with 0 tool calls — listings_gather may not have been picked. gd={gd}"
        )
        assert "apify_listings_search" in invoked_tools, (
            f"succeeded but Apify was not invoked — listings_gather tactic may not have "
            f"been picked. invoked_tools={invoked_tools}, gd={gd}"
        )
    elif status == "ask_user":
        # Acceptable only if Apify returned zero matching listings.
        kind = gate_result.get("failing_check_kind")
        assert kind == "min_listings_returned", (
            f"ask_user but failing_check_kind={kind!r} — expected only "
            f"min_listings_returned (zero Apify matches). 'no_brain_work' would mean "
            f"the tactic catalog regressed. gd={gd}"
        )
