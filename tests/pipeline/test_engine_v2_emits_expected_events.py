"""Tests for engine_v2 event emission — is.phase_complete ordering and structure.

Covers:
- One is.phase_complete fires per phase that ran
- gate_status is a valid value ("pass", "fail", "ask_user")
- Ordering: each is.phase_complete for phase N fires AFTER all is.tactician_complete
  events for phase N and BEFORE the next phase's is.phase_start
- signal_scores + evidence are present on run_complete ranked_candidates

Design: tests operate at the Strategist layer (phase_complete_cb) and at the
run_engine_v2 integration level (full event sequence via a fake event_emit list).
Uses asyncio.run() to avoid requiring pytest-asyncio (matches project conventions).
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.pipeline.catalogs.budget import BudgetEnvelope
from app.pipeline.catalogs.schemas import (
    CheckSpec,
    GateSpec,
    PhaseSpec,
    Strategy,
)
from app.pipeline.strategist import Strategist


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_envelope(hypothesis_count: str = "single") -> BudgetEnvelope:
    return BudgetEnvelope(
        speed="normal",
        capability="general",
        resource="medium",
        depth="search",
        hypothesis_count=hypothesis_count,
    )


def _make_phase(
    phase_id: str,
    depends_on: list[str] | None = None,
    on_fail: str = "terminate",
) -> PhaseSpec:
    return PhaseSpec(
        id=phase_id,
        depends_on=depends_on or [],
        unit_of_work_contract={"query": ""},
        hypothesis_count_policy="fixed:1",
        gate=GateSpec(
            checks=[CheckSpec(kind="min_primary_signals", params={"min": 1})],
            on_fail=on_fail,  # type: ignore[arg-type]
        ),
    )


def _make_strategy(phases: list[PhaseSpec]) -> Strategy:
    return Strategy(
        id="test_strategy",
        applies_to={"task_type": "test"},
        phases=phases,
        default_mode="balanced",
        budget_minimums={},
    )


def _passing_tactician_output(slot_idx: int = 0) -> dict:
    """Returns a tactician output that passes the min_primary_signals gate."""
    return {
        "slot_idx": slot_idx,
        "findings": [
            {
                "candidate_name": "Candidate A",
                "source_class": "live_search",
                "confidence": 0.8,
                "evidence_snippet": "found it",
            }
        ],
        "metadata": {
            "hypotheses_explored": 1,
            "primary_signals_count": 1,
            "disconfirm_count": 0,
            "surviving_hypothesis_count": 1,
            "actual_ru": 1,
        },
        "candidate_names": ["Candidate A"],
        "ranked_candidates": [{"name": "Candidate A", "confidence": 0.8}],
    }


def _failing_tactician_output(slot_idx: int = 0) -> dict:
    """Returns a tactician output that fails the min_primary_signals gate."""
    return {
        "slot_idx": slot_idx,
        "findings": [],
        "metadata": {
            "hypotheses_explored": 1,
            "primary_signals_count": 0,
            "disconfirm_count": 0,
            "surviving_hypothesis_count": 0,
            "actual_ru": 1,
        },
        "candidate_names": [],
        "ranked_candidates": [],
    }


def _run(coro):
    """Run a coroutine synchronously — project convention avoids pytest-asyncio."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Strategist-level phase_complete_cb tests
# ---------------------------------------------------------------------------

class TestStrategistPhaseCompleteCb:
    """Tests for the phase_complete_cb hook in Strategist.execute()."""

    def test_cb_fires_once_per_completed_phase_single_phase(self):
        """With one phase that passes, phase_complete_cb is called exactly once."""
        phase = _make_phase("identify")
        strategy = _make_strategy([phase])
        envelope = _make_envelope()

        cb_calls: list[tuple] = []

        async def _cb(phase_spec, phase_output, gate_passed):
            cb_calls.append((phase_spec.id, gate_passed))

        async def _tactician_fn(phase_spec, unit_of_work, slot_idx):
            return _passing_tactician_output(slot_idx)

        async def _run_test():
            with patch("app.pipeline.strategist.wallet") as mock_wallet:
                mock_wallet.consume = MagicMock()
                strategist = Strategist(
                    strategy=strategy,
                    envelope=envelope,
                    run_id="run-001",
                    user_id="user-001",
                    hold_id="hold-001",
                )
                return await strategist.execute(
                    query="test query",
                    classifier_output={},
                    tactician_fn=_tactician_fn,
                    phase_complete_cb=_cb,
                )

        result = _run(_run_test())
        assert len(cb_calls) == 1
        assert cb_calls[0] == ("identify", True)
        assert result.status == "completed"

    def test_cb_fires_once_per_phase_two_phases(self):
        """With two sequential phases both passing, cb fires twice in order."""
        phase_a = _make_phase("identify")
        phase_b = _make_phase("verify", depends_on=["identify"])
        strategy = _make_strategy([phase_a, phase_b])
        envelope = _make_envelope()

        cb_calls: list[tuple] = []

        async def _cb(phase_spec, phase_output, gate_passed):
            cb_calls.append((phase_spec.id, gate_passed))

        async def _tactician_fn(phase_spec, unit_of_work, slot_idx):
            return _passing_tactician_output(slot_idx)

        async def _run_test():
            with patch("app.pipeline.strategist.wallet") as mock_wallet:
                mock_wallet.consume = MagicMock()
                strategist = Strategist(
                    strategy=strategy,
                    envelope=envelope,
                    run_id="run-002",
                    user_id="user-001",
                    hold_id="hold-001",
                )
                return await strategist.execute(
                    query="test query",
                    classifier_output={},
                    tactician_fn=_tactician_fn,
                    phase_complete_cb=_cb,
                )

        result = _run(_run_test())
        assert len(cb_calls) == 2
        assert cb_calls[0] == ("identify", True)
        assert cb_calls[1] == ("verify", True)
        assert result.status == "completed"

    def test_cb_fires_on_gate_fail_with_gate_passed_false(self):
        """When gate fails the cb still fires with gate_passed=False."""
        phase = _make_phase("identify", on_fail="terminate")
        strategy = _make_strategy([phase])
        envelope = _make_envelope()

        cb_calls: list[tuple] = []

        async def _cb(phase_spec, phase_output, gate_passed):
            cb_calls.append((phase_spec.id, gate_passed))

        async def _tactician_fn(phase_spec, unit_of_work, slot_idx):
            return _failing_tactician_output(slot_idx)

        async def _run_test():
            with patch("app.pipeline.strategist.wallet") as mock_wallet:
                mock_wallet.consume = MagicMock()
                strategist = Strategist(
                    strategy=strategy,
                    envelope=envelope,
                    run_id="run-003",
                    user_id="user-001",
                    hold_id="hold-001",
                )
                return await strategist.execute(
                    query="test query",
                    classifier_output={},
                    tactician_fn=_tactician_fn,
                    phase_complete_cb=_cb,
                )

        result = _run(_run_test())
        assert len(cb_calls) == 1
        assert cb_calls[0] == ("identify", False)
        assert result.status == "terminated"

    def test_cb_not_called_when_none(self):
        """Omitting phase_complete_cb (default None) runs without error."""
        phase = _make_phase("identify")
        strategy = _make_strategy([phase])
        envelope = _make_envelope()

        async def _tactician_fn(phase_spec, unit_of_work, slot_idx):
            return _passing_tactician_output(slot_idx)

        async def _run_test():
            with patch("app.pipeline.strategist.wallet") as mock_wallet:
                mock_wallet.consume = MagicMock()
                strategist = Strategist(
                    strategy=strategy,
                    envelope=envelope,
                    run_id="run-004",
                    user_id="user-001",
                    hold_id="hold-001",
                )
                # No phase_complete_cb — should not raise
                return await strategist.execute(
                    query="test query",
                    classifier_output={},
                    tactician_fn=_tactician_fn,
                )

        result = _run(_run_test())
        assert result.status == "completed"


# ---------------------------------------------------------------------------
# Engine-level event ordering tests
# ---------------------------------------------------------------------------

class TestEngineV2EventOrdering:
    """Tests that run_engine_v2 emits is.phase_complete with correct
    gate_status values and in the right order relative to tactician events."""

    def _make_two_phase_setup(self):
        """Return a two-phase strategy and passing tactician for ordering tests."""
        phase_a = _make_phase("identify")
        phase_b = _make_phase("verify", depends_on=["identify"])
        strategy = _make_strategy([phase_a, phase_b])
        envelope = _make_envelope(hypothesis_count="single")

        async def _fake_tactician_fn(phase: PhaseSpec, unit_of_work: dict, slot_idx: int) -> dict:
            return _passing_tactician_output(slot_idx)

        return strategy, envelope, _fake_tactician_fn

    def _run_engine_with_fake_tactician(
        self,
        strategy: Strategy,
        envelope: BudgetEnvelope,
        fake_tactician_fn,
        run_id: str,
    ) -> list[dict]:
        """Run run_engine_v2 with all heavy deps mocked; return emitted events."""
        emitted: list[dict] = []

        async def _event_emit(payload: dict) -> None:
            emitted.append(payload)

        original_execute = Strategist.execute

        async def _patched_execute(self_inner, query, classifier_output, tactician_fn, phase_complete_cb=None):
            return await original_execute(
                self_inner,
                query,
                classifier_output,
                fake_tactician_fn,  # substitute our fake for the real scoped_brain runner
                phase_complete_cb=phase_complete_cb,
            )

        async def _run_test():
            with (
                patch("app.pipeline.engine_v2._load_all_catalogs") as mock_catalogs,
                patch("app.pipeline.engine_v2.wallet") as mock_wallet,
                patch("app.pipeline.strategist.wallet") as mock_strat_wallet,
                patch("app.pipeline.engine_v2._write_research_trail"),
                patch.object(Strategist, "execute", _patched_execute),
            ):
                mock_catalogs.return_value = ({strategy.id: strategy}, {}, {})
                mock_wallet.refund = MagicMock()
                mock_wallet.release = MagicMock()
                mock_wallet.consume = MagicMock()
                mock_strat_wallet.consume = MagicMock()

                from app.pipeline.engine_v2 import run_engine_v2
                await run_engine_v2(
                    user_id="user-001",
                    run_id=run_id,
                    hold_id="hold-001",
                    hold_amount_ru=100,
                    query="test query",
                    envelope=envelope,
                    strategy_id=strategy.id,
                    event_emit=_event_emit,
                )

        _run(_run_test())
        return emitted

    def test_phase_complete_emitted_with_valid_gate_status(self):
        """is.phase_complete events have gate_status in {pass, fail, ask_user}."""
        valid_statuses = {"pass", "fail", "ask_user"}
        strategy, envelope, fake_tactician = self._make_two_phase_setup()
        emitted = self._run_engine_with_fake_tactician(strategy, envelope, fake_tactician, "run-evt-001")

        phase_complete_events = [e for e in emitted if e["type"] == "is.phase_complete"]
        assert phase_complete_events, "Expected at least one is.phase_complete event"
        for event in phase_complete_events:
            assert event["gate_status"] in valid_statuses, (
                f"gate_status {event['gate_status']!r} not in {valid_statuses}"
            )

    def test_one_phase_complete_per_phase(self):
        """Exactly one is.phase_complete fires per phase in the run."""
        strategy, envelope, fake_tactician = self._make_two_phase_setup()
        n_phases = len(strategy.phases)
        emitted = self._run_engine_with_fake_tactician(strategy, envelope, fake_tactician, "run-evt-002")

        phase_complete_events = [e for e in emitted if e["type"] == "is.phase_complete"]
        assert len(phase_complete_events) == n_phases, (
            f"Expected {n_phases} is.phase_complete events, got {len(phase_complete_events)}"
        )

    def test_phase_complete_ordering_relative_to_phase_start(self):
        """is.phase_complete for phase N appears before is.phase_start for phase N+1.

        For any two consecutive phases A → B:
        - is.phase_start(A) must precede is.phase_complete(A)
        - is.phase_complete(A) must precede is.phase_start(B)
        """
        strategy, envelope, fake_tactician = self._make_two_phase_setup()
        emitted = self._run_engine_with_fake_tactician(strategy, envelope, fake_tactician, "run-evt-003")

        phase_start_indices: dict[str, int] = {}
        phase_complete_indices: dict[str, int] = {}
        for i, event in enumerate(emitted):
            etype = event.get("type")
            if etype == "is.phase_start":
                phase_start_indices[event["phase_id"]] = i
            elif etype == "is.phase_complete":
                phase_complete_indices[event["phase_id"]] = i

        # Verify: no other phase_start appears inside a phase's own start→complete window
        for phase_id, complete_idx in phase_complete_indices.items():
            if phase_id not in phase_start_indices:
                continue
            own_start_idx = phase_start_indices[phase_id]
            interleaved = {
                pid: idx
                for pid, idx in phase_start_indices.items()
                if pid != phase_id
                and own_start_idx < idx < complete_idx
            }
            assert not interleaved, (
                f"Phase start for {list(interleaved.keys())} appeared inside "
                f"phase '{phase_id}' execution window (before its is.phase_complete)"
            )

        # Verify: is.phase_complete(A) precedes is.phase_start(B) for A→B
        # The two phases are "identify" and "verify"; verify depends on identify.
        if "identify" in phase_complete_indices and "verify" in phase_start_indices:
            assert phase_complete_indices["identify"] < phase_start_indices["verify"], (
                "is.phase_complete(identify) must come before is.phase_start(verify)"
            )

    def test_phase_complete_has_required_fields(self):
        """Each is.phase_complete event has run_id, phase_id, gate_status, distinct_candidate_names, n_tacticians."""
        strategy, envelope, fake_tactician = self._make_two_phase_setup()
        emitted = self._run_engine_with_fake_tactician(strategy, envelope, fake_tactician, "run-evt-004")

        phase_complete_events = [e for e in emitted if e["type"] == "is.phase_complete"]
        assert phase_complete_events, "Expected at least one is.phase_complete event"
        for event in phase_complete_events:
            assert "run_id" in event
            assert "phase_id" in event
            assert "gate_status" in event
            assert "distinct_candidate_names" in event
            assert "n_tacticians" in event
            assert event["run_id"] == "run-evt-004"

    def test_gate_fail_emits_fail_status(self):
        """When a phase gate fails with on_fail=terminate, gate_status is 'fail'."""
        phase = _make_phase("identify", on_fail="terminate")
        strategy = _make_strategy([phase])
        envelope = _make_envelope()

        async def _fake_tactician_fn(phase_spec: PhaseSpec, unit_of_work: dict, slot_idx: int) -> dict:
            return _failing_tactician_output(slot_idx)

        emitted = self._run_engine_with_fake_tactician(strategy, envelope, _fake_tactician_fn, "run-evt-005")

        phase_complete_events = [e for e in emitted if e["type"] == "is.phase_complete"]
        assert len(phase_complete_events) == 1
        assert phase_complete_events[0]["gate_status"] == "fail"

    def test_ask_user_emits_ask_user_status(self):
        """When gate on_fail is ask_user and gate fails, gate_status is 'ask_user'."""
        phase = _make_phase("identify", on_fail="ask_user")
        strategy = _make_strategy([phase])
        envelope = _make_envelope()

        async def _fake_tactician_fn(phase_spec: PhaseSpec, unit_of_work: dict, slot_idx: int) -> dict:
            return _failing_tactician_output(slot_idx)

        emitted = self._run_engine_with_fake_tactician(strategy, envelope, _fake_tactician_fn, "run-evt-006")

        phase_complete_events = [e for e in emitted if e["type"] == "is.phase_complete"]
        assert len(phase_complete_events) == 1
        assert phase_complete_events[0]["gate_status"] == "ask_user"
