"""Backend tests for the wallet router (UI-P4 + Enhancement 3.4).

Tests do NOT hit Postgres — all DB calls are patched at the router module level.
"""
from __future__ import annotations

import os
import sys
import uuid
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Minimal environment stubs so app.main imports cleanly without live services
# ---------------------------------------------------------------------------
os.environ.setdefault("INFO_BROKER_API_KEY", "test-secret-key")
os.environ.setdefault("POSTGRES_DB", "info_broker")
os.environ.setdefault("POSTGRES_USER", "user")
os.environ.setdefault("POSTGRES_PASSWORD", "password")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6333")

sys.modules.setdefault("qdrant_client", MagicMock())
sys.modules.setdefault("qdrant_client.models", MagicMock())

from fastapi.testclient import TestClient  # noqa: E402

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_USER_ID = str(uuid.uuid4())
_RUN_ID = str(uuid.uuid4())
_DB_PATH = "app.routers.v3.wallet"

_WALLET_ROW = {
    "balance_ru": 150,
    "held_ru": 8,
    "available_ru": 142,
    "floor_ru": 20,
    "spent_ru_lifetime": 320,
    "created_at": "2026-01-01T00:00:00+00:00",
    "version": 5,
}

_NO_OPS_ROW = {"consumed": 0}


def _user(uid: str = _USER_ID) -> dict:
    return {"id": uid, "username": "tester", "is_active": True, "role": "analyst", "is_admin": False}


def _make_client(user_id: str = _USER_ID) -> TestClient:
    from app.main import app
    from app.routers.v3.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _user(user_id)
    return TestClient(app)


# ---------------------------------------------------------------------------
# test_get_wallet_returns_snapshot
# ---------------------------------------------------------------------------

class TestGetWallet:
    def test_get_wallet_returns_snapshot(self):
        client = _make_client()
        with (
            patch(f"{_DB_PATH}._auto_provision"),
            patch(f"{_DB_PATH}.fetch_one", return_value=_WALLET_ROW),
        ):
            r = client.get("/v3/wallet")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["balance_ru"] == 150
        assert data["held_ru"] == 8
        assert data["available_ru"] == 142
        assert data["floor_ru"] == 20
        assert data["spent_ru_lifetime"] == 320
        assert data["version"] == 5

    def test_get_wallet_auto_provisions_when_no_row(self):
        """_auto_provision is called; subsequent fetch_one returns provisioned row."""
        call_count = {"n": 0}

        def fetch_side(*_args, **_kwargs):
            call_count["n"] += 1
            return _WALLET_ROW

        client = _make_client()
        with (
            patch(f"{_DB_PATH}._auto_provision") as mock_prov,
            patch(f"{_DB_PATH}.fetch_one", side_effect=fetch_side),
        ):
            r = client.get("/v3/wallet")
        assert r.status_code == 200
        mock_prov.assert_called_once_with(_USER_ID)
        assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# test_get_wallet_transactions_paginates
# ---------------------------------------------------------------------------

class TestGetWalletTransactions:
    def _make_op(self, op: str = "hold", delta: int = -5, idx: int = 0) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "operation": op,
            "amount_ru": abs(delta),
            "balance_before": 100,
            "balance_after": 100 + delta,
            "held_before": 0,
            "held_after": abs(delta) if delta < 0 else 0,
            "run_id": _RUN_ID,
            "metadata": None,
            "created_at": f"2026-01-0{idx + 1}T00:00:00+00:00",
        }

    def test_get_wallet_transactions_paginates(self):
        ops = [self._make_op("consume_phase_0", -5, i) for i in range(3)]
        client = _make_client()
        with (
            patch(f"{_DB_PATH}.fetch_one", return_value={"n": 10}),
            patch(f"{_DB_PATH}.fetch_all", return_value=ops),
        ):
            r = client.get("/v3/wallet/transactions?limit=3&offset=0")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["total"] == 10
        assert len(data["transactions"]) == 3

    def test_get_wallet_transactions_empty(self):
        client = _make_client()
        with (
            patch(f"{_DB_PATH}.fetch_one", return_value={"n": 0}),
            patch(f"{_DB_PATH}.fetch_all", return_value=[]),
        ):
            r = client.get("/v3/wallet/transactions")
        assert r.status_code == 200
        assert r.json()["total"] == 0
        assert r.json()["transactions"] == []


# ---------------------------------------------------------------------------
# test_put_wallet_floor_updates_value
# ---------------------------------------------------------------------------

class TestPutWalletFloor:
    def test_put_wallet_floor_updates_value(self):
        updated_row = {**_WALLET_ROW, "floor_ru": 30}
        client = _make_client()

        # Build a mock conn context manager with a cursor that does nothing
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn_obj = MagicMock()
        mock_conn_obj.cursor = MagicMock(return_value=mock_cursor)
        mock_conn_obj.__enter__ = MagicMock(return_value=mock_conn_obj)
        mock_conn_obj.__exit__ = MagicMock(return_value=False)

        mock_get_conn = MagicMock(return_value=mock_conn_obj)

        with (
            patch(f"{_DB_PATH}._auto_provision"),
            patch(f"{_DB_PATH}.get_conn", mock_get_conn),
            patch(f"{_DB_PATH}.fetch_one", return_value=updated_row),
        ):
            r = client.put("/v3/wallet/floor", json={"floor_ru": 30})
        assert r.status_code == 200, r.text
        assert r.json()["floor_ru"] == 30

    def test_put_wallet_floor_rejects_negative(self):
        """floor_ru < 0 must be rejected with 422 (Pydantic validation)."""
        client = _make_client()
        r = client.put("/v3/wallet/floor", json={"floor_ru": -1})
        assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# test_get_forecast_computes_rolling_average
# ---------------------------------------------------------------------------

class TestGetForecast:
    def _fetch_one_side(self, row_30d, row_7d, wallet_row):
        call_count = {"n": 0}

        def side(*_args, **_kwargs):
            n = call_count["n"]
            call_count["n"] += 1
            if n == 0:
                return row_30d
            elif n == 1:
                return row_7d
            else:
                return wallet_row

        return side

    def test_get_forecast_computes_rolling_average(self):
        """With 7d=70 and 30d=210 consumed, rolling daily avg should be 10.0 (7d / 7)."""
        client = _make_client()
        wallet = {**_WALLET_ROW, "floor_ru": 0}
        with (
            patch(f"{_DB_PATH}.fetch_one",
                  side_effect=self._fetch_one_side(
                      {"consumed": 210},
                      {"consumed": 70},
                      wallet,
                  )),
            patch(f"{_DB_PATH}._auto_provision"),
        ):
            r = client.get("/v3/wallet/forecast")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["last_30d_consumed"] == 210
        assert data["last_7d_consumed"] == 70
        assert data["rolling_daily_avg"] == 10.0

    def test_get_forecast_predicts_floor_breach_at_current_rate(self):
        """With available=100, floor=0, daily_avg=10: days_until_floor = 10."""
        client = _make_client()
        wallet = {**_WALLET_ROW, "available_ru": 100, "floor_ru": 0}
        with (
            patch(f"{_DB_PATH}.fetch_one",
                  side_effect=self._fetch_one_side(
                      {"consumed": 300},
                      {"consumed": 70},
                      wallet,
                  )),
            patch(f"{_DB_PATH}._auto_provision"),
        ):
            r = client.get("/v3/wallet/forecast")
        assert r.status_code == 200, r.text
        data = r.json()
        # spendable_above_floor = 100 - 0 = 100, daily_avg = 10 → days = 10
        assert data["days_until_floor_ru"] == 10

    def test_get_forecast_no_consumption_returns_null_days(self):
        """Zero consumption → days_until_floor_ru is None."""
        client = _make_client()
        wallet = {**_WALLET_ROW, "available_ru": 100, "floor_ru": 0}
        with (
            patch(f"{_DB_PATH}.fetch_one",
                  side_effect=self._fetch_one_side(
                      {"consumed": 0},
                      {"consumed": 0},
                      wallet,
                  )),
            patch(f"{_DB_PATH}._auto_provision"),
        ):
            r = client.get("/v3/wallet/forecast")
        assert r.status_code == 200
        assert r.json()["days_until_floor_ru"] is None


# ---------------------------------------------------------------------------
# test_get_run_cost_breakdown_*
# ---------------------------------------------------------------------------

class TestRunCostBreakdown:
    _RUN_ROW = {
        "id": _RUN_ID,
        "status": "succeeded",
        "started_at": "2026-01-01T00:00:00+00:00",
        "finished_at": "2026-01-01T00:05:00+00:00",
        "query": "test query",
        "budget_plan": None,
    }

    def _make_ops(self) -> list[dict]:
        return [
            {
                "id": str(uuid.uuid4()),
                "op": "hold",
                "delta_ru": 20,
                "balance_after": 130,
                "held_after": 20,
                "reason": None,
                "created_at": "2026-01-01T00:00:01+00:00",
                "idempotency_key": "hold-key",
            },
            {
                "id": str(uuid.uuid4()),
                "op": "consume_phase_0",
                "delta_ru": -5,
                "balance_after": 125,
                "held_after": 15,
                "reason": None,
                "created_at": "2026-01-01T00:01:00+00:00",
                "idempotency_key": "consume-0-key",
            },
            {
                "id": str(uuid.uuid4()),
                "op": "consume_phase_1",
                "delta_ru": -7,
                "balance_after": 118,
                "held_after": 8,
                "reason": None,
                "created_at": "2026-01-01T00:02:00+00:00",
                "idempotency_key": "consume-1-key",
            },
            {
                "id": str(uuid.uuid4()),
                "op": "release",
                "delta_ru": -8,
                "balance_after": 118,
                "held_after": 0,
                "reason": None,
                "created_at": "2026-01-01T00:05:00+00:00",
                "idempotency_key": "release-key",
            },
        ]

    def test_get_run_cost_breakdown_aggregates_by_phase(self):
        client = _make_client()
        with (
            patch(f"{_DB_PATH}.fetch_one", return_value=self._RUN_ROW),
            patch(f"{_DB_PATH}.fetch_all", return_value=self._make_ops()),
        ):
            r = client.get(f"/v3/runs/{_RUN_ID}/cost_breakdown")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["total_ru"] == 12  # 5 + 7 from consume_phase_* ops
        phase_ids = [p["phase_id"] for p in data["by_phase"]]
        assert "consume_phase_0" in phase_ids
        assert "consume_phase_1" in phase_ids
        by_phase_map = {p["phase_id"]: p["ru_consumed"] for p in data["by_phase"]}
        assert by_phase_map["consume_phase_0"] == 5
        assert by_phase_map["consume_phase_1"] == 7

    def test_get_run_cost_breakdown_returns_run_operations(self):
        client = _make_client()
        ops = self._make_ops()
        with (
            patch(f"{_DB_PATH}.fetch_one", return_value=self._RUN_ROW),
            patch(f"{_DB_PATH}.fetch_all", return_value=ops),
        ):
            r = client.get(f"/v3/runs/{_RUN_ID}/cost_breakdown")
        assert r.status_code == 200, r.text
        data = r.json()
        # All 4 ops (hold, consume_phase_0, consume_phase_1, release) should be present
        assert len(data["wallet_operations"]) == 4
        op_names = [o["op"] for o in data["wallet_operations"]]
        assert "hold" in op_names
        assert "release" in op_names

    def test_get_run_cost_breakdown_includes_technique_placeholder_note(self):
        client = _make_client()
        with (
            patch(f"{_DB_PATH}.fetch_one", return_value=self._RUN_ROW),
            patch(f"{_DB_PATH}.fetch_all", return_value=self._make_ops()),
        ):
            r = client.get(f"/v3/runs/{_RUN_ID}/cost_breakdown")
        assert r.status_code == 200
        data = r.json()
        assert "TODO" in data["by_technique_note"]
        assert len(data["by_technique"]) > 0

    def test_get_run_cost_breakdown_404_for_unknown_run(self):
        client = _make_client()
        with patch(f"{_DB_PATH}.fetch_one", return_value=None):
            r = client.get(f"/v3/runs/{uuid.uuid4()}/cost_breakdown")
        assert r.status_code == 404
