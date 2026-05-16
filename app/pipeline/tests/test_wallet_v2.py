"""Tests for Wallet v2 (MVP-M1) operations in app/pipeline/budget.py.

All tests mock the DB layer by patching app.pipeline.budget.get_conn
(the name bound in the budget module at import time).  No live database needed.
Pattern mirrors tests/test_security.py (unittest.mock, pytest, no services).
"""
from __future__ import annotations

import threading
import uuid
from contextlib import contextmanager
from typing import Optional
from unittest.mock import patch

import pytest

from app.pipeline.budget import (
    ConsumeResult,
    HoldResult,
    consume,
    extend_hold,
    hold,
    refund,
    release,
)

# ---------------------------------------------------------------------------
# Fake DB helpers
# ---------------------------------------------------------------------------

class _FakeCursor:
    """Minimal psycopg2-compatible cursor.

    `responses` is a list of values returned by successive fetchone() calls.
    None means "no row".
    """

    def __init__(self, responses: list[Optional[dict]] | None = None):
        self.responses = list(responses or [])
        self._idx = 0
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> Optional[dict]:
        if self._idx < len(self.responses):
            val = self.responses[self._idx]
            self._idx += 1
            return val
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class _FakeConn:
    def __init__(self, cursor: _FakeCursor):
        self._cursor = cursor

    def cursor(self, cursor_factory=None):
        return self._cursor

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        pass


@contextmanager
def _conn_ctx(cursor: _FakeCursor):
    yield _FakeConn(cursor)


# Convenience: build a fresh hold-success cursor
def _hold_success_cursor(balance: int = 100, held_after: int = 10) -> _FakeCursor:
    # Calls in order:
    # 1. _ensure_wallet INSERT → no fetchone needed
    # 2. _idempotency_hit SELECT → None (no prior)
    # 3. UPDATE RETURNING → wallet row
    # 4. _write_op INSERT → no fetchone
    return _FakeCursor(responses=[None, {"balance_ru": balance, "held_ru": held_after}])


def _uid() -> str:
    return str(uuid.uuid4())


def _key() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# test_hold_succeeds_within_balance
# ---------------------------------------------------------------------------

def test_hold_succeeds_within_balance():
    cur = _hold_success_cursor(balance=100, held_after=10)
    with patch("app.pipeline.budget.get_conn", side_effect=lambda: _conn_ctx(cur)):
        result = hold(_uid(), _uid(), p90_ru=10, idempotency_key=_key())

    assert result.ok is True
    assert result.held_ru == 10
    assert result.reason is None


# ---------------------------------------------------------------------------
# test_hold_rejected_when_insufficient
# ---------------------------------------------------------------------------

def test_hold_rejected_when_insufficient():
    # Idempotency → None, UPDATE guard fails → None, SELECT wallet for reason
    wallet_state = {"balance_ru": 5, "held_ru": 0, "floor_ru": 0}
    cur = _FakeCursor(responses=[None, None, wallet_state])

    with patch("app.pipeline.budget.get_conn", side_effect=lambda: _conn_ctx(cur)):
        result = hold(_uid(), _uid(), p90_ru=10, idempotency_key=_key())

    assert result.ok is False
    assert result.reason == "insufficient"


# ---------------------------------------------------------------------------
# test_hold_rejected_below_floor
# ---------------------------------------------------------------------------

def test_hold_rejected_below_floor():
    # balance=100, held=0, floor=95 → post-hold balance 90 < floor 95
    # available >= p90 so reason must be "below_floor"
    wallet_state = {"balance_ru": 100, "held_ru": 0, "floor_ru": 95}
    cur = _FakeCursor(responses=[None, None, wallet_state])

    with patch("app.pipeline.budget.get_conn", side_effect=lambda: _conn_ctx(cur)):
        result = hold(_uid(), _uid(), p90_ru=10, idempotency_key=_key())

    assert result.ok is False
    assert result.reason == "below_floor"


# ---------------------------------------------------------------------------
# test_two_concurrent_holds_for_last_ru_only_one_succeeds
# ---------------------------------------------------------------------------

def test_two_concurrent_holds_for_last_ru_only_one_succeeds():
    """Race two threads against a shared 'balance'; only one should win."""
    balance = [10]
    held = [0]
    floor = [0]
    results: list[Optional[HoldResult]] = [None, None]
    db_lock = threading.Lock()

    def _make_ctx():
        @contextmanager
        def _ctx():
            call_log: list[str] = []

            class _RaceCursor:
                executed: list[tuple[str, tuple]] = []

                def execute(self, sql, params=()):
                    self.executed.append((sql, params))

                def fetchone(self):
                    last_sql, last_params = self.executed[-1]
                    # _ensure_wallet INSERT → None
                    if "INSERT INTO user_budget_wallets" in last_sql:
                        return None
                    # idempotency SELECT → None (fresh keys each time)
                    if "wallet_operations" in last_sql and "SELECT" in last_sql:
                        return None
                    # UPDATE with guard — serialise via lock
                    if "UPDATE user_budget_wallets" in last_sql and "held_ru" in last_sql:
                        with db_lock:
                            ru = last_params[0]
                            avail = balance[0] - held[0]
                            if avail >= ru and (balance[0] - ru) >= floor[0]:
                                held[0] += ru
                                return {"balance_ru": balance[0], "held_ru": held[0]}
                            return None
                    # _write_op INSERT → None
                    return None

                def __enter__(self): return self
                def __exit__(self, *_): pass

            conn = _FakeConn(_RaceCursor())
            yield conn

        return _ctx

    def run_hold(idx: int):
        ctx = _make_ctx()
        with patch("app.pipeline.budget.get_conn", side_effect=lambda: ctx()):
            results[idx] = hold(_uid(), _uid(), p90_ru=10, idempotency_key=_key())

    t1 = threading.Thread(target=run_hold, args=(0,))
    t2 = threading.Thread(target=run_hold, args=(1,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    successes = sum(1 for r in results if r is not None and r.ok)
    assert successes <= 1, f"Both threads succeeded (double-spend): {results}"


# ---------------------------------------------------------------------------
# test_idempotent_retry_returns_same_result
# ---------------------------------------------------------------------------

def test_idempotent_retry_returns_same_result():
    idem_key = _key()
    prior_row = {
        "id": str(uuid.uuid4()),
        "user_id": _uid(),
        "run_id": _uid(),
        "idempotency_key": idem_key,
        "op": "hold",
        "delta_ru": 20,
        "balance_after": 80,
        "held_after": 20,
        "reason": None,
        "created_at": "2026-05-15T00:00:00Z",
    }

    # _ensure_wallet INSERT executes but never calls fetchone.
    # First fetchone() call is from _idempotency_hit → returns prior_row.
    cur = _FakeCursor(responses=[prior_row])

    with patch("app.pipeline.budget.get_conn", side_effect=lambda: _conn_ctx(cur)):
        result = hold(_uid(), _uid(), p90_ru=20, idempotency_key=idem_key)

    assert result.ok is True
    assert result.hold_id == idem_key
    assert result.held_ru == 20  # held_after from prior row


# ---------------------------------------------------------------------------
# test_consume_decrements_balance_and_held
# ---------------------------------------------------------------------------

def test_consume_decrements_balance_and_held():
    # idempotency → None, UPDATE → wallet after
    cur = _FakeCursor(responses=[None, {"balance_ru": 85, "held_ru": 5}])

    with patch("app.pipeline.budget.get_conn", side_effect=lambda: _conn_ctx(cur)):
        result = consume(_uid(), _uid(), phase_n=1, actual_ru=10, idempotency_key=_key())

    assert result.ok is True
    assert result.balance_after == 85
    assert result.held_after == 5


# ---------------------------------------------------------------------------
# test_release_returns_unused_to_spendable
# ---------------------------------------------------------------------------

def test_release_returns_unused_to_spendable():
    cur = _FakeCursor(responses=[None, {"balance_ru": 90, "held_ru": 0}])

    with patch("app.pipeline.budget.get_conn", side_effect=lambda: _conn_ctx(cur)):
        release(_uid(), _uid(), remaining_ru=10, idempotency_key=_key())

    update_sqls = [sql for sql, _ in cur.executed if "UPDATE" in sql and "held_ru" in sql]
    assert update_sqls, "Expected UPDATE on held_ru for release"


# ---------------------------------------------------------------------------
# test_db_unreachable_fails_closed
# ---------------------------------------------------------------------------

def test_db_unreachable_fails_closed():
    """hold() must return ok=False when the DB connection cannot be established."""
    def _boom():
        raise ConnectionError("DB unreachable")

    with patch("app.pipeline.budget.get_conn", side_effect=_boom):
        result = hold(_uid(), _uid(), p90_ru=10, idempotency_key=_key())

    assert result.ok is False
    assert result.reason == "wallet_unavailable"
