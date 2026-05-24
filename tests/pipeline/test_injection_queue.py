"""Tests for app.pipeline.runners.injection_queue.

Covers: enqueue, drain, pending_count, drain-clears, isolation between run_ids.
"""
from __future__ import annotations

import threading

import pytest

from app.pipeline.runners import injection_queue


def _clean(run_id: str) -> None:
    """Drain any leftover state for *run_id* from prior tests."""
    injection_queue.drain(run_id)


class TestEnqueueDrain:
    def test_enqueue_then_drain_returns_instruction(self):
        rid = "run-test-001"
        _clean(rid)
        injection_queue.enqueue(rid, "focus on LinkedIn profiles")
        result = injection_queue.drain(rid)
        assert result == ["focus on LinkedIn profiles"]

    def test_drain_empty_returns_empty_list(self):
        rid = "run-test-002"
        _clean(rid)
        assert injection_queue.drain(rid) == []

    def test_drain_clears_queue(self):
        rid = "run-test-003"
        _clean(rid)
        injection_queue.enqueue(rid, "instruction A")
        injection_queue.drain(rid)
        # Second drain must be empty
        assert injection_queue.drain(rid) == []

    def test_multiple_enqueues_drain_in_order(self):
        rid = "run-test-004"
        _clean(rid)
        injection_queue.enqueue(rid, "first")
        injection_queue.enqueue(rid, "second")
        injection_queue.enqueue(rid, "third")
        result = injection_queue.drain(rid)
        assert result == ["first", "second", "third"]

    def test_drain_clears_multiple(self):
        rid = "run-test-005"
        _clean(rid)
        injection_queue.enqueue(rid, "a")
        injection_queue.enqueue(rid, "b")
        injection_queue.drain(rid)
        assert injection_queue.drain(rid) == []


class TestPendingCount:
    def test_pending_count_zero_initially(self):
        rid = "run-test-006"
        _clean(rid)
        assert injection_queue.pending_count(rid) == 0

    def test_pending_count_increments(self):
        rid = "run-test-007"
        _clean(rid)
        injection_queue.enqueue(rid, "x")
        assert injection_queue.pending_count(rid) == 1
        injection_queue.enqueue(rid, "y")
        assert injection_queue.pending_count(rid) == 2

    def test_pending_count_zero_after_drain(self):
        rid = "run-test-008"
        _clean(rid)
        injection_queue.enqueue(rid, "z")
        injection_queue.drain(rid)
        assert injection_queue.pending_count(rid) == 0

    def test_pending_count_non_destructive(self):
        rid = "run-test-009"
        _clean(rid)
        injection_queue.enqueue(rid, "check")
        count_before = injection_queue.pending_count(rid)
        count_again = injection_queue.pending_count(rid)
        assert count_before == count_again == 1
        # Verify item is still there
        result = injection_queue.drain(rid)
        assert result == ["check"]


class TestIsolation:
    def test_queues_are_isolated_between_run_ids(self):
        rid_a = "run-iso-a"
        rid_b = "run-iso-b"
        _clean(rid_a)
        _clean(rid_b)

        injection_queue.enqueue(rid_a, "for A")
        injection_queue.enqueue(rid_b, "for B")

        assert injection_queue.drain(rid_a) == ["for A"]
        assert injection_queue.drain(rid_b) == ["for B"]

    def test_drain_one_does_not_affect_other(self):
        rid_a = "run-iso-c"
        rid_b = "run-iso-d"
        _clean(rid_a)
        _clean(rid_b)

        injection_queue.enqueue(rid_a, "a1")
        injection_queue.enqueue(rid_b, "b1")

        injection_queue.drain(rid_a)
        # rid_b still has its item
        assert injection_queue.pending_count(rid_b) == 1
        assert injection_queue.drain(rid_b) == ["b1"]


class TestThreadSafety:
    def test_concurrent_enqueues(self):
        """Multiple threads enqueueing concurrently should not lose items."""
        rid = "run-thread-safe"
        _clean(rid)
        n = 50

        def _enqueue_many():
            for i in range(n):
                injection_queue.enqueue(rid, f"item-{i}")

        threads = [threading.Thread(target=_enqueue_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        result = injection_queue.drain(rid)
        assert len(result) == n * 4
