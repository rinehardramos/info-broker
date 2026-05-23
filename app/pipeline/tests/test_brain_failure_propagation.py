"""Brain-failure propagation: scoped_brain → engine_v2 → pipeline_runs.error_message.

The scoped_brain runner already detects BRAIN_FAILURE (HTTP 401 / 429 /
5xx / no-result) and logs at ERROR. But the run-level error_message
still came from the strategist's gate-fail terminate_reason — so the UI
showed "Gate failed on phase 'gather': checks did not pass" instead of
"Brain authentication failed (HTTP 401)". This module pins the new
propagation path.

The piece this tests is the public callback contract:
    scoped_brain_runner(..., on_failure=collector_callable)
and the helper that classifies the collected failures into a user-facing
error_message string.
"""
from __future__ import annotations

import pytest

from app.pipeline.runners.scoped_brain import (
    BrainFailure,
    summarize_brain_failures,
)


# ---------------------------------------------------------------------------
# summarize_brain_failures — turns a list of BrainFailures into one
# error_message string suitable for pipeline_runs.error_message
# ---------------------------------------------------------------------------


class TestSummarizeBrainFailures:
    def test_no_failures_returns_none(self):
        assert summarize_brain_failures([]) is None

    def test_only_non_fatal_returns_none(self):
        """A brain that returned cleanly but produced no task_calls isn't
        a fatal failure — strategist might still pass that phase."""
        non_fatal = BrainFailure(
            is_fatal=False, kind="ok", api_status=None,
            retry_count=0, api_key_source="oauth_token", message="",
        )
        assert summarize_brain_failures([non_fatal]) is None

    def test_single_auth_failure_named(self):
        f = BrainFailure(
            is_fatal=True, kind="auth_failed", api_status=401,
            retry_count=2, api_key_source="none",
            message="Failed to authenticate. API Error: 401",
        )
        msg = summarize_brain_failures([f])
        assert msg is not None
        assert "401" in msg
        assert "auth" in msg.lower() or "credentials" in msg.lower()

    def test_single_rate_limit_named(self):
        f = BrainFailure(
            is_fatal=True, kind="rate_limited", api_status=429,
            retry_count=3, api_key_source="oauth_token",
            message="Rate limited",
        )
        msg = summarize_brain_failures([f])
        assert msg is not None
        assert "429" in msg or "rate limit" in msg.lower()

    def test_single_upstream_error_named(self):
        f = BrainFailure(
            is_fatal=True, kind="upstream_error", api_status=503,
            retry_count=1, api_key_source="oauth_token",
            message="Internal server error",
        )
        msg = summarize_brain_failures([f])
        assert msg is not None
        assert "503" in msg or "upstream" in msg.lower()

    def test_no_result_event_named(self):
        f = BrainFailure(
            is_fatal=True, kind="no_result_event", api_status=None,
            retry_count=0, api_key_source="oauth_token",
            message="brain subprocess emitted no `result` event",
        )
        msg = summarize_brain_failures([f])
        assert msg is not None
        assert "subprocess" in msg.lower() or "crashed" in msg.lower() or "timeout" in msg.lower()

    def test_mixed_failures_picks_first_fatal(self):
        """When several slots fail, pick the first fatal one — the strategy
        already terminated, no point summarising all of them."""
        non_fatal = BrainFailure(False, "ok", None, 0, "oauth_token", "")
        auth = BrainFailure(True, "auth_failed", 401, 2, "none", "Failed to authenticate.")
        rate = BrainFailure(True, "rate_limited", 429, 3, "oauth_token", "Rate limited")
        msg = summarize_brain_failures([non_fatal, auth, rate])
        assert msg is not None
        assert "401" in msg  # first fatal wins

    def test_user_facing_message_does_not_leak_internal_paths(self):
        """The message lands in pipeline_runs.error_message → eventually the UI.
        It should not contain file paths or stack traces."""
        f = BrainFailure(
            is_fatal=True, kind="auth_failed", api_status=401, retry_count=2,
            api_key_source="none",
            message="Failed: /root/.claude/.credentials.json missing",
        )
        msg = summarize_brain_failures([f])
        assert msg is not None
        assert "/root/" not in msg
        assert "Traceback" not in msg


# ---------------------------------------------------------------------------
# on_failure callback wiring — scoped_brain_runner accepts it
# ---------------------------------------------------------------------------


class TestOnFailureCallback:
    """Signature contract: scoped_brain_runner must accept on_failure
    so engine_v2 can register a collector. We don't run the full subprocess
    — just verify the keyword exists in the signature."""

    def test_scoped_brain_runner_accepts_on_failure_kwarg(self):
        import inspect
        from app.pipeline.runners.scoped_brain import scoped_brain_runner
        sig = inspect.signature(scoped_brain_runner)
        assert "on_failure" in sig.parameters
        param = sig.parameters["on_failure"]
        assert param.default is None  # optional
