"""Bounded-concurrency wrapper for tactician fan-out.

When the strategist fans out N tacticians for a phase (e.g. 15 disconfirm
slots for a 10-hypothesis red_team), every slot spawns a Claude Code
subprocess of ~300 MB. With docker mem_limit=1g the container hit a
memory-cgroup OOM and exited 137, orphaning every in-flight run
(issue #113).

The fix wraps the gather call in `gather_bounded(tasks, max_concurrent)`,
which uses an asyncio.Semaphore to keep no more than ``max_concurrent``
coroutines runnable at once. The remaining tasks queue and run as slots
free. Order of results is preserved (same contract as asyncio.gather).
"""
from __future__ import annotations

import asyncio
import time

import pytest

from app.pipeline.strategist import gather_bounded


def _run(coro):
    """Repo convention — wrap async tests in asyncio.run from a sync test."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


def test_returns_results_in_order():
    async def main():
        async def co(i):
            await asyncio.sleep(0.01)
            return i
        return await gather_bounded([co(i) for i in range(5)], max_concurrent=2)
    assert _run(main()) == [0, 1, 2, 3, 4]


def test_zero_or_negative_max_concurrent_falls_back_to_unbounded():
    """Defensive: misconfigured 0 or -1 shouldn't deadlock — fall back
    to unbounded asyncio.gather semantics."""
    async def main():
        async def co(i):
            return i
        return await gather_bounded([co(i) for i in range(3)], max_concurrent=0)
    assert _run(main()) == [0, 1, 2]


def test_empty_task_list_returns_empty():
    async def main():
        return await gather_bounded([], max_concurrent=3)
    assert _run(main()) == []


# ---------------------------------------------------------------------------
# Concurrency limit actually enforced
# ---------------------------------------------------------------------------


def test_max_two_concurrent_observable():
    """Wall-clock test: 6 tasks * 50ms sleep with max_concurrent=2 should
    take ~150ms (3 batches), not ~50ms (all parallel)."""
    async def main():
        async def slow_task(i):
            await asyncio.sleep(0.05)
            return i
        t0 = time.monotonic()
        results = await gather_bounded([slow_task(i) for i in range(6)], max_concurrent=2)
        elapsed = time.monotonic() - t0
        return results, elapsed

    results, elapsed = _run(main())
    assert results == [0, 1, 2, 3, 4, 5]
    # 3 sequential batches of 2 × ~50ms ≈ 150ms; allow generous slack for CI noise
    assert 0.12 < elapsed < 0.35, f"elapsed={elapsed:.3f}s — bound not enforced"


def test_peak_concurrency_never_exceeds_limit():
    """Direct counter: track in-flight at any moment."""
    async def main():
        in_flight = 0
        peak = 0
        lock = asyncio.Lock()

        async def task():
            nonlocal in_flight, peak
            async with lock:
                in_flight += 1
                if in_flight > peak:
                    peak = in_flight
            await asyncio.sleep(0.01)
            async with lock:
                in_flight -= 1
            return None

        await gather_bounded([task() for _ in range(10)], max_concurrent=3)
        return peak

    peak = _run(main())
    assert peak <= 3, f"peak in-flight {peak} exceeded the limit of 3"


# ---------------------------------------------------------------------------
# Error propagation matches asyncio.gather
# ---------------------------------------------------------------------------


def test_propagates_first_exception():
    async def main():
        async def ok(i):
            return i
        async def boom():
            raise RuntimeError("kapow")
        await gather_bounded([ok(1), boom(), ok(2)], max_concurrent=2)

    with pytest.raises(RuntimeError, match="kapow"):
        _run(main())
