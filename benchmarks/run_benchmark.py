"""Benchmark driver — runs the real app pipeline against the curated gold-set.

Usage
-----
    # Basic run against the local stack
    LOCAL_STACK_URL=http://localhost:8000 python -m benchmarks.run_benchmark

    # Limit to specific item ids
    LOCAL_STACK_URL=http://localhost:8000 python -m benchmarks.run_benchmark \
        --items person-jobs-001 company-kyb-001

    # Write JSON report to a file
    LOCAL_STACK_URL=http://localhost:8000 python -m benchmarks.run_benchmark \
        --out-json /tmp/benchmark_report.json

Environment variables
---------------------
LOCAL_STACK_URL       Base URL for the API (default: http://localhost:8000)
BENCH_USERNAME        Username for login (default: admin)
BENCH_PASSWORD        Password for login (default: admin)
BENCH_TIMEOUT_S       Max seconds to wait for each run (default: 300)
BENCH_POLL_INTERVAL_S Poll interval in seconds (default: 5)
INFO_BROKER_API_KEY   API key for GET /v3/research-trails (X-API-Key header).
                      Without this the harness falls back to the old path and
                      will see empty trails for benchmark runs (trigger_type=agent).

Design notes
------------
- No mocking — exercises the real preflight → confirm → poll → trail path.
- Reads ``research_trails`` row via GET /v3/research-trails/{run_id} using
  X-API-Key header (INFO_BROKER_API_KEY). Falls back to runs/{id}.research
  when key is absent (only works for agent_is trigger_type runs).
- Strategy phases are extracted from the preflight ``suggested_strategy`` and
  used to feed the ``skipped_phases`` anti-gaming guard.
- Per-item run metadata (strategy, mode, techniques used) is recorded and
  passed to ``aggregate_scores`` for component-level reporting.
- 429 rate-limit responses on preflight/confirm are retried with exponential
  backoff (up to 4 retries, starting at 2s).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
import yaml

# Ensure repo root is on sys.path so we can import from app.*
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from benchmarks.score import (  # noqa: E402
    aggregate_scores,
    build_recommendations,
    lead_richness,
    load_registered_technique_ids,
    render_recommendations,
    render_summary_table,
    score_item,
)

log = logging.getLogger("benchmarks.run")

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

BASE_URL: str = os.getenv("LOCAL_STACK_URL", "http://localhost:8000").rstrip("/")
USERNAME: str = os.getenv("BENCH_USERNAME", "admin")
PASSWORD: str = os.getenv("BENCH_PASSWORD", "admin")
TIMEOUT_S: int = int(os.getenv("BENCH_TIMEOUT_S", "300"))
POLL_INTERVAL_S: float = float(os.getenv("BENCH_POLL_INTERVAL_S", "5"))
_INFO_BROKER_API_KEY: str = os.getenv("INFO_BROKER_API_KEY", "")

_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"succeeded", "failed", "cancelled", "error", "ask_user"}
)

# ---------------------------------------------------------------------------
# Gold-set loader
# ---------------------------------------------------------------------------

GOLDSET_DIR = Path(__file__).resolve().parent / "goldset"


def load_goldset(item_ids: list[str] | None = None) -> list[dict]:
    """Load all gold-set items from YAML files in benchmarks/goldset/.

    Skips schema.yaml. Validates that each item has required fields.
    Optionally filters to *item_ids*.
    """
    items: list[dict] = []
    seen_ids: set[str] = set()

    for yaml_file in sorted(GOLDSET_DIR.glob("*.yaml")):
        if yaml_file.name == "schema.yaml":
            continue
        raw = yaml.safe_load(yaml_file.read_text())
        if not isinstance(raw, list):
            log.warning("Skipping %s — expected a YAML list", yaml_file.name)
            continue
        for item in raw:
            _validate_item(item, yaml_file.name)
            iid = item["id"]
            if iid in seen_ids:
                raise ValueError(f"Duplicate gold-set id {iid!r} in {yaml_file.name}")
            seen_ids.add(iid)
            items.append(item)

    if item_ids:
        items = [it for it in items if it["id"] in set(item_ids)]

    return items


def _validate_item(item: dict, filename: str) -> None:
    required = ("id", "query", "expected_facts", "domain")
    for field in required:
        if field not in item:
            raise ValueError(
                f"Gold-set item in {filename} missing required field {field!r}: {item}"
            )
    if not isinstance(item["expected_facts"], list) or not item["expected_facts"]:
        raise ValueError(
            f"Gold-set item {item.get('id')!r} in {filename}: "
            f"expected_facts must be a non-empty list"
        )
    for ef in item["expected_facts"]:
        for ef_field in ("claim", "authoritative_source", "must_be_live"):
            if ef_field not in ef:
                raise ValueError(
                    f"Gold-set item {item.get('id')!r}: expected_fact missing {ef_field!r}"
                )


# ---------------------------------------------------------------------------
# HTTP session helpers
# ---------------------------------------------------------------------------

def login(session: requests.Session) -> dict:
    """Login and return the auth token payload."""
    resp = session.post(
        f"{BASE_URL}/v3/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token") or data.get("token") or ""
    if not token:
        raise RuntimeError(f"Login did not return a token: {data}")
    session.headers["Authorization"] = f"Bearer {token}"
    log.info("Logged in as %s", USERNAME)
    return data


_MAX_RETRY_429 = 4          # up to 4 retries on 429
_RETRY_BASE_DELAY_S = 2.0   # 2s, 4s, 8s, 16s (exponential)


def _post_with_retry(
    session: requests.Session,
    url: str,
    json_body: dict,
    timeout: int = 30,
) -> requests.Response:
    """POST with exponential backoff on HTTP 429 (rate limit)."""
    delay = _RETRY_BASE_DELAY_S
    for attempt in range(_MAX_RETRY_429 + 1):
        resp = session.post(url, json=json_body, timeout=timeout)
        if resp.status_code == 429 and attempt < _MAX_RETRY_429:
            retry_after = float(resp.headers.get("Retry-After", delay))
            wait = max(retry_after, delay)
            log.warning(
                "429 on %s (attempt %d/%d) — waiting %.1fs",
                url,
                attempt + 1,
                _MAX_RETRY_429 + 1,
                wait,
            )
            time.sleep(wait)
            delay *= 2
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()  # Exhausted retries — let it propagate
    return resp  # unreachable; satisfies type checker


def post_preflight(session: requests.Session, item: dict) -> dict:
    """POST /v3/preflight and return the response body."""
    body: dict[str, Any] = {"query": item["query"]}
    if item.get("mode"):
        body["mode"] = item["mode"]
    if item.get("template"):
        body["strategy"] = item["template"]

    resp = _post_with_retry(session, f"{BASE_URL}/v3/preflight", body, timeout=30)
    return resp.json()


def post_confirm(
    session: requests.Session,
    item: dict,
    preflight_out: dict,
) -> dict:
    """POST /v3/preflight/confirm with start_run=True."""
    envelope = preflight_out["envelope"]
    confirm_body = {
        "query": item["query"],
        "strategy_id": preflight_out["suggested_strategy"],
        "envelope": {
            "capability": envelope.get("capability", "general"),
            "hypothesis_count": envelope.get("hypothesis_count", "competing"),
            "depth": envelope.get("depth", "search"),
            "speed": envelope.get("speed", "normal"),
            "resource": envelope.get("resource", "medium"),
        },
        "start_run": True,
    }
    resp = _post_with_retry(
        session, f"{BASE_URL}/v3/preflight/confirm", confirm_body, timeout=30
    )
    return resp.json()


def poll_run(session: requests.Session, run_id: str) -> dict:
    """Poll GET /v3/pipelines/runs/{run_id} until terminal or timeout."""
    deadline = time.time() + TIMEOUT_S
    while time.time() < deadline:
        resp = session.get(f"{BASE_URL}/v3/pipelines/runs/{run_id}", timeout=30)
        if resp.status_code == 404:
            log.debug("Run %s not found yet — retrying", run_id)
            time.sleep(POLL_INTERVAL_S)
            continue
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "")
        log.info("  run %s status=%s", run_id[:8], status)
        if status in _TERMINAL_STATUSES:
            return data
        time.sleep(POLL_INTERVAL_S)

    raise TimeoutError(
        f"Run {run_id} did not reach terminal status within {TIMEOUT_S}s"
    )


def fetch_trail(session: requests.Session, run_id: str) -> tuple[dict, list[dict], dict]:
    """Return (trail_dict, findings_list, cost_dict) from the research-trails record.

    Preferred path: ``GET /v3/research-trails/{run_id}`` using the X-API-Key header
    read from the ``INFO_BROKER_API_KEY`` environment variable.  This endpoint
    returns the *real* trail regardless of ``trigger_type`` on the run record.

    Fallback: if the API key is absent or the endpoint returns 4xx, falls back
    to ``GET /v3/pipelines/runs/{run_id}`` and reads ``data["research"]["trail"]``
    (the old path, which only works for ``trigger_type == "agent_is"`` runs).

    The top-level ``tool_calls`` from the research-trails response is injected into
    the returned ``trail`` dict so that downstream guards can read it via
    ``trail.get("tool_calls")``.

    cost_dict keys: ru_consumed (int), duration_s (float).
    """
    # --- Cost / timestamps always come from the run record (bearer auth) ---
    run_resp = session.get(f"{BASE_URL}/v3/pipelines/runs/{run_id}", timeout=30)
    run_resp.raise_for_status()
    run_data = run_resp.json()

    # Real RU consumption lives in the wallet_operations ledger, exposed via
    # GET /v3/runs/{run_id}/cost_breakdown.total_ru — NOT on the run record
    # (pipeline_runs has no ru_consumed column). Fall back to 0 if unavailable.
    ru_consumed: int = 0
    try:
        cb = session.get(f"{BASE_URL}/v3/runs/{run_id}/cost_breakdown", timeout=30)
        if cb.status_code == 200:
            ru_consumed = int(cb.json().get("total_ru") or 0)
    except Exception:
        log.debug("cost_breakdown fetch failed for %s", run_id, exc_info=True)
    started_at = run_data.get("started_at") or run_data.get("created_at") or ""
    finished_at = run_data.get("finished_at") or run_data.get("updated_at") or ""
    duration_s = 0.0
    if started_at and finished_at:
        try:
            from datetime import datetime, timezone

            def _parse(ts: str) -> datetime:
                ts = ts.rstrip("Z").split("+")[0]
                for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        return datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
                return datetime.now(timezone.utc)

            duration_s = (_parse(finished_at) - _parse(started_at)).total_seconds()
        except Exception:
            duration_s = 0.0

    cost_dict = {"ru_consumed": ru_consumed, "duration_s": duration_s}

    # --- Try the real research-trails endpoint first ---
    if _INFO_BROKER_API_KEY:
        try:
            rt_resp = requests.get(
                f"{BASE_URL}/v3/research-trails/{run_id}",
                headers={"X-API-Key": _INFO_BROKER_API_KEY},
                timeout=30,
            )
            if rt_resp.status_code == 200:
                rt_data = rt_resp.json()

                # Top-level tool_calls is the authoritative count
                top_level_tool_calls: int = rt_data.get("tool_calls") or 0

                trail: dict = rt_data.get("trail") or {}
                if isinstance(trail, str):
                    trail = json.loads(trail)

                findings: list[dict] = rt_data.get("findings") or []
                if isinstance(findings, str):
                    findings = json.loads(findings)

                # Inject top-level tool_calls so guards can read it via trail["tool_calls"]
                trail["tool_calls"] = top_level_tool_calls

                log.debug(
                    "research-trails: run_id=%s tool_calls=%d findings=%d phases=%s",
                    run_id[:8],
                    top_level_tool_calls,
                    len(findings),
                    trail.get("phases", []),
                )
                return trail, findings, cost_dict
            else:
                log.warning(
                    "research-trails endpoint returned %d for run %s — falling back",
                    rt_resp.status_code,
                    run_id[:8],
                )
        except Exception as exc:
            log.warning(
                "research-trails fetch failed for run %s: %s — falling back",
                run_id[:8],
                exc,
            )
    else:
        log.warning(
            "INFO_BROKER_API_KEY not set — falling back to runs/{id}.research path "
            "(will be empty for agent trigger_type runs)"
        )

    # --- Fallback: old path (only works for agent_is trigger_type) ---
    research = run_data.get("research") or {}
    trail = research.get("trail") or {}
    if isinstance(trail, str):
        trail = json.loads(trail)
    findings = research.get("findings") or []
    if isinstance(findings, str):
        findings = json.loads(findings)

    return trail, findings, cost_dict


# ---------------------------------------------------------------------------
# Strategy phase extractor
# ---------------------------------------------------------------------------

def _get_strategy_phases(strategy_id: str) -> list[str]:
    """Return the declared phase ids for a strategy from the catalog."""
    try:
        from pathlib import Path as _Path
        from app.pipeline.catalogs.loader import load_catalog  # type: ignore[import]

        strategies_dir = _REPO_ROOT / "app" / "pipeline" / "catalogs" / "registries" / "strategies"
        catalog = load_catalog("strategy", strategies_dir)
        strategy = catalog.get(strategy_id)
        if strategy:
            return [p.id for p in strategy.phases]
    except Exception as exc:
        log.warning("Could not load strategy catalog for %s: %s", strategy_id, exc)
    return []


# ---------------------------------------------------------------------------
# Per-item benchmark run
# ---------------------------------------------------------------------------

def run_item(
    session: requests.Session,
    item: dict,
    registered_ids: frozenset[str],
) -> tuple[dict, dict]:
    """Drive the real pipeline for one gold-set item.

    Returns (score_result, run_metadata).
    """
    item_id = item["id"]
    log.info("[%s] starting preflight", item_id)

    # 1. Preflight
    try:
        preflight_out = post_preflight(session, item)
    except requests.HTTPError as exc:
        log.error("[%s] preflight failed: %s", item_id, exc)
        return _error_result(item_id, "preflight_http_error"), {}

    strategy_id: str = preflight_out.get("suggested_strategy", "")
    mode: str = preflight_out.get("suggested_mode", "")
    strategy_phases = _get_strategy_phases(strategy_id)

    log.info("[%s] strategy=%s mode=%s", item_id, strategy_id, mode)

    # 2. Confirm + launch run
    try:
        confirm_out = post_confirm(session, item, preflight_out)
    except requests.HTTPError as exc:
        log.error("[%s] confirm failed: %s", item_id, exc)
        return _error_result(item_id, "confirm_http_error"), {}

    run_id: str = confirm_out.get("run_id", "")
    log.info("[%s] run_id=%s", item_id, run_id)

    # 3. Poll to terminal
    try:
        run_data = poll_run(session, run_id)
    except (TimeoutError, requests.HTTPError) as exc:
        log.error("[%s] polling failed: %s", item_id, exc)
        return _error_result(item_id, "poll_error"), {}

    final_status = run_data.get("status", "unknown")
    log.info("[%s] run finished status=%s", item_id, final_status)

    # 4. Fetch trail + findings + cost
    try:
        trail, findings, run_cost = fetch_trail(session, run_id)
    except Exception as exc:
        log.error("[%s] trail fetch failed: %s", item_id, exc)
        return _error_result(item_id, "trail_fetch_error"), {}

    # Extract technique_ids used (from trail branches)
    branches: list[dict] = trail.get("branches", [])
    technique_ids_used = list({b.get("technique_id", "") for b in branches if b.get("technique_id")})

    # 5. Score
    score_result = score_item(
        gold_item=item,
        trail=trail,
        findings=findings,
        registered_technique_ids=registered_ids,
        strategy_phases=strategy_phases,
    )

    # Attach richness metrics (for leads-gen items; meaningful for all domains)
    score_result["richness"] = lead_richness(findings, trail)

    # Attach cost
    score_result["cost"] = run_cost

    # Attach matched_facts_count (for cost-per-matched-fact)
    score_result["matched_facts_count"] = sum(
        1 for fm in score_result.get("fact_matches", []) if fm.get("matched")
    )

    # Per-item metadata for aggregation
    run_metadata = {
        "run_id": run_id,
        "strategy": strategy_id,
        "mode": mode,
        "domain": item.get("domain", "unknown"),
        "template": item.get("template", ""),
        "technique_ids": technique_ids_used,
        "phases_ran": trail.get("phases", []),
        "final_status": final_status,
        "trail_tool_calls": trail.get("tool_calls", 0),
    }

    log.info(
        "[%s] score=%.3f coverage=%.3f source_quality=%.3f guard=%s",
        item_id,
        score_result["item_score"],
        score_result["coverage"],
        score_result["source_quality"],
        score_result.get("tripped_guard") or "-",
    )

    return score_result, run_metadata


def _error_result(item_id: str, reason: str) -> dict:
    return {
        "item_id": item_id,
        "item_score": 0.0,
        "coverage": 0.0,
        "source_quality": 0.0,
        "gaming_flags": [],
        "tripped_guard": None,
        "fact_matches": [],
        "error": reason,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the benchmark harness against the local infobroker stack."
    )
    parser.add_argument(
        "--items",
        nargs="*",
        metavar="ID",
        help="Limit run to specific gold-set item ids.",
    )
    parser.add_argument(
        "--out-json",
        metavar="PATH",
        help="Write the full JSON report to this path.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s  %(levelname)-7s %(name)s — %(message)s",
    )

    # Load gold-set
    items = load_goldset(args.items)
    if not items:
        log.error("No gold-set items found (or none matched --items filter).")
        return 1
    log.info("Loaded %d gold-set items", len(items))

    # Load registered technique catalog once
    registered_ids = load_registered_technique_ids()
    log.info("Registered technique ids: %s", sorted(registered_ids))

    # Login
    session = requests.Session()
    session.headers["Content-Type"] = "application/json"
    try:
        login(session)
    except Exception as exc:
        log.error("Login failed: %s", exc)
        return 1

    # Run items
    all_results: list[dict] = []
    all_metadata: list[dict] = []
    for i, item in enumerate(items):
        if i > 0:
            # Small inter-item delay to reduce rate-limit risk on preflight/confirm
            time.sleep(2.0)
        result, metadata = run_item(session, item, registered_ids)
        all_results.append(result)
        all_metadata.append(metadata)

    # Aggregate
    aggregates = aggregate_scores(all_results, all_metadata)

    # Human-readable table
    table = render_summary_table(all_results, aggregates)
    print(table)

    # Build + print recommendations
    recommendations = build_recommendations(all_results, aggregates)
    rec_text = render_recommendations(recommendations)
    print(rec_text)

    # JSON report
    report = {
        "item_results": all_results,
        "run_metadata": all_metadata,
        "aggregates": aggregates,
        "recommendations": recommendations,
    }
    if args.out_json:
        out_path = Path(args.out_json)
        out_path.write_text(json.dumps(report, indent=2))
        log.info("JSON report written to %s", out_path)
    else:
        print("\nJSON report:")
        print(json.dumps(report, indent=2))

    # Optional: POST the report to the app so it appears on the admin Benchmark
    # Reports page. Enabled by BENCHMARK_INGEST_URL (set by the UI-triggered run).
    ingest_url = os.getenv("BENCHMARK_INGEST_URL")
    if ingest_url:
        try:
            resp = requests.post(
                f"{ingest_url.rstrip('/')}/v3/benchmarks/reports",
                headers={"X-API-Key": os.getenv("INFO_BROKER_API_KEY", "")},
                json={"label": os.getenv("BENCHMARK_INGEST_LABEL") or None, "report": report},
                timeout=30,
            )
            resp.raise_for_status()
            log.info("Report ingested to %s (id=%s)", ingest_url, resp.json().get("id"))
        except Exception as exc:  # noqa: BLE001
            log.warning("Report ingest failed: %s", exc)

    # Exit code: 0 if any item scored > 0, else 1
    any_scored = any(r["item_score"] > 0 for r in all_results)
    return 0 if any_scored else 1


if __name__ == "__main__":
    sys.exit(main())
