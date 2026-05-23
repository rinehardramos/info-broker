"""Real-environment functional test: canonical real-estate query reaches Apify.

After spec 2026-05-23, real_estate.gather.preferred_tactic_id='listings_gather',
which requires the apify_listings_search technique (Apify Zillow scraper).
This test asserts the system goes far enough to invoke a real Apify call.

Without PR #116's diagnostic infrastructure on this branch, we cannot inspect
gate_result.invoked_tools directly. Instead we infer Apify involvement from
run duration — an Apify call costs >1s even for an empty result set. When
PR #116 merges, follow-up should add an explicit 'apify_listings_search'
invocation assertion via the (then-populated) gate-detail endpoint.

Requires LOCAL_STACK_URL + admin creds + APIFY_API_TOKEN (or APIFY_API_KEY).

Spec: docs/superpowers/specs/2026-05-23-research-skeleton-tactic-completion-design.md
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
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


@pytest.mark.functional
def test_canonical_real_estate_query_does_real_work_via_apify():
    """When APIFY_API_TOKEN is set, the canonical real-estate query must take
    >1000ms (real Apify call). When unset, skip.
    """
    if not os.environ.get("APIFY_API_TOKEN") and not os.environ.get("APIFY_API_KEY"):
        pytest.skip(
            "APIFY_API_TOKEN / APIFY_API_KEY not configured — skipping Apify functional test"
        )

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

    # Apify Zillow scrape can take 60+ seconds — poll up to 180s
    deadline = time.time() + 180
    status = None
    body: dict = {}
    while time.time() < deadline:
        r = requests.get(f"{LOCAL_URL}/v3/pipelines/runs/{run_id}", headers=headers)
        body = r.json()
        status = body.get("status")
        if status in ("succeeded", "failed", "ask_user"):
            break
        time.sleep(3)
    assert status in ("succeeded", "ask_user", "failed"), (
        f"Run did not reach terminal (got {status!r}). body={body}"
    )

    started = body.get("started_at")
    finished = body.get("finished_at")
    assert started and finished, f"run missing timestamps: {body}"

    delta_ms = (_parse_iso(finished) - _parse_iso(started)).total_seconds() * 1000
    # An Apify call typically takes >2s even for an empty result; >1000ms is a
    # safe lower bound. Pre-spec runs completed in ~90ms.
    assert delta_ms > 1000, (
        f"Apify-bearing run completed in {delta_ms:.0f}ms — too fast for a real "
        f"Apify call. Tactic catalog may have regressed. body={body}"
    )
