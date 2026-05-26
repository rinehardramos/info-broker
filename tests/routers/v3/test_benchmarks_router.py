"""Unit tests for benchmark report summary extraction + run-state logic (pure)."""
from __future__ import annotations

from app.routers.v3 import benchmarks as b


def test_summary_extracts_overall():
    report = {"aggregates": {"overall": {"mean_score": 0.62, "total_items": 4, "gamed_pct": 25.0}}}
    mean, items, gamed = b._summary(report)
    assert mean == 0.62 and items == 4 and gamed == 25.0


def test_summary_missing_aggregates_is_none():
    assert b._summary({}) == (None, None, None)
    assert b._summary({"aggregates": {}}) == (None, None, None)


def test_run_active_false_when_no_proc():
    b._RUN_STATE.update({"active": False, "proc": None})
    assert b._run_active() is False


def test_run_active_clears_stale_flag_when_proc_finished():
    class _Done:
        def poll(self):  # finished process
            return 0
    b._RUN_STATE.update({"active": True, "proc": _Done()})
    assert b._run_active() is False
    assert b._RUN_STATE["active"] is False


def test_run_active_true_while_proc_alive():
    class _Alive:
        def poll(self):  # still running
            return None
    b._RUN_STATE.update({"active": True, "proc": _Alive()})
    assert b._run_active() is True
    b._RUN_STATE.update({"active": False, "proc": None})  # reset
