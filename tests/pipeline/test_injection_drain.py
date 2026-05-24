"""Tests for mid-run injection integration: strategist drain + scoped_brain prompt.

Covers:
1. A pending injection in the queue lands in unit_of_work["user_directive"]
   after Strategist.execute runs a phase.
2. If multiple directives are enqueued, they are joined with newlines.
3. user_directive survives replan (overlay block propagates it).
4. _build_scoped_prompt includes USER DIRECTIVE section when user_directive is set.
5. _build_scoped_prompt does NOT include USER DIRECTIVE section when absent.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.pipeline.catalogs.budget import BudgetEnvelope
from app.pipeline.catalogs.schemas import CheckSpec, GateSpec, PhaseSpec, Strategy
from app.pipeline.runners import injection_queue
from app.pipeline.runners.scoped_brain import _build_scoped_prompt
from app.pipeline.catalogs.schemas import Tactic, TaskSpec


# ---------------------------------------------------------------------------
# Helpers (mirrored from test_engine_v2_emits_expected_events.py)
# ---------------------------------------------------------------------------

def _make_envelope() -> BudgetEnvelope:
    return BudgetEnvelope(
        speed="normal",
        capability="general",
        resource="medium",
        depth="search",
        hypothesis_count="single",
    )


def _make_phase(phase_id: str, on_fail: str = "terminate") -> PhaseSpec:
    return PhaseSpec(
        id=phase_id,
        depends_on=[],
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


def _passing_tactician_output(uow_capture: list | None = None):
    async def _fn(phase_spec, unit_of_work, slot_idx):
        if uow_capture is not None:
            uow_capture.append(dict(unit_of_work))
        return {
            "slot_idx": slot_idx,
            "findings": [
                {
                    "candidate_name": "Alice",
                    "source_class": "live_search",
                    "confidence": 0.9,
                    "evidence_snippet": "found",
                }
            ],
            "metadata": {
                "hypotheses_explored": 1,
                "primary_signals_count": 1,
                "disconfirm_count": 0,
                "surviving_hypothesis_count": 1,
                "actual_ru": 1,
            },
            "candidate_names": ["Alice"],
            "ranked_candidates": [{"name": "Alice", "confidence": 0.9}],
        }
    return _fn


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Test: drain merges into unit_of_work["user_directive"]
# ---------------------------------------------------------------------------

class TestStrategistDrain:
    def _run_single_phase_capture_uow(self, run_id: str) -> list[dict]:
        """Run one phase, capture unit_of_work dicts seen by tactician_fn."""
        phase = _make_phase("gather")
        strategy = _make_strategy([phase])
        envelope = _make_envelope()

        captured: list[dict] = []

        async def _run_test():
            with patch("app.pipeline.strategist.wallet") as mock_wallet:
                mock_wallet.consume = MagicMock()
                from app.pipeline.strategist import Strategist
                strategist = Strategist(
                    strategy=strategy,
                    envelope=envelope,
                    run_id=run_id,
                    user_id="user-test",
                    hold_id="hold-test",
                )
                await strategist.execute(
                    query="test query",
                    classifier_output={},
                    tactician_fn=_passing_tactician_output(captured),
                )
            return captured

        return _run(_run_test())

    def test_pending_injection_lands_in_user_directive(self):
        run_id = f"drain-test-{__import__('uuid').uuid4().hex[:8]}"
        injection_queue.drain(run_id)  # clean

        injection_queue.enqueue(run_id, "focus on LinkedIn profiles")

        captured = self._run_single_phase_capture_uow(run_id)
        assert captured, "tactician_fn was never called"
        uow = captured[0]
        assert "user_directive" in uow
        assert "focus on LinkedIn profiles" in uow["user_directive"]

    def test_multiple_injections_joined_in_directive(self):
        run_id = f"drain-multi-{__import__('uuid').uuid4().hex[:8]}"
        injection_queue.drain(run_id)

        injection_queue.enqueue(run_id, "directive one")
        injection_queue.enqueue(run_id, "directive two")

        captured = self._run_single_phase_capture_uow(run_id)
        assert captured
        directive = captured[0].get("user_directive", "")
        assert "directive one" in directive
        assert "directive two" in directive

    def test_no_injection_no_directive_key(self):
        run_id = f"drain-empty-{__import__('uuid').uuid4().hex[:8]}"
        injection_queue.drain(run_id)  # ensure empty

        captured = self._run_single_phase_capture_uow(run_id)
        assert captured
        # user_directive should not be set (or empty) when nothing was injected
        assert not captured[0].get("user_directive")

    def test_drain_clears_after_phase(self):
        """Injections are consumed once; second run should see nothing."""
        run_id = f"drain-once-{__import__('uuid').uuid4().hex[:8]}"
        injection_queue.drain(run_id)

        injection_queue.enqueue(run_id, "consumed instruction")

        self._run_single_phase_capture_uow(run_id)

        # After the phase ran, the queue must be empty
        assert injection_queue.pending_count(run_id) == 0


# ---------------------------------------------------------------------------
# Test: user_directive survives replan overlay
# ---------------------------------------------------------------------------

class TestUserDirectiveSurvivesReplan:
    def test_user_directive_propagated_on_replan(self):
        """If user_directive is set before a replan attempt, it must survive overlay."""
        phase = _make_phase("gather", on_fail="replan")
        strategy = _make_strategy([phase])
        envelope = _make_envelope()

        run_id = f"replan-directive-{__import__('uuid').uuid4().hex[:8]}"
        injection_queue.drain(run_id)
        injection_queue.enqueue(run_id, "survive replan")

        captured: list[dict] = []
        attempt = [0]

        async def _mixed_fn(phase_spec, unit_of_work, slot_idx):
            attempt[0] += 1
            captured.append(dict(unit_of_work))
            # First attempt fails gate (no signals), second passes
            if attempt[0] == 1:
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
            return {
                "slot_idx": slot_idx,
                "findings": [
                    {
                        "candidate_name": "Bob",
                        "source_class": "live_search",
                        "confidence": 0.8,
                        "evidence_snippet": "found",
                    }
                ],
                "metadata": {
                    "hypotheses_explored": 1,
                    "primary_signals_count": 1,
                    "disconfirm_count": 0,
                    "surviving_hypothesis_count": 1,
                    "actual_ru": 1,
                },
                "candidate_names": ["Bob"],
                "ranked_candidates": [{"name": "Bob", "confidence": 0.8}],
            }

        async def _run_test():
            with patch("app.pipeline.strategist.wallet") as mock_wallet:
                mock_wallet.consume = MagicMock()
                from app.pipeline.strategist import Strategist
                strategist = Strategist(
                    strategy=strategy,
                    envelope=envelope,
                    run_id=run_id,
                    user_id="user-test",
                    hold_id="hold-test",
                )
                await strategist.execute(
                    query="test",
                    classifier_output={},
                    tactician_fn=_mixed_fn,
                )

        _run(_run_test())

        assert len(captured) >= 2, "Expected at least 2 attempts (fail + pass)"
        # The directive from the first attempt must appear in the second attempt too
        directive_second = captured[1].get("user_directive", "")
        assert "survive replan" in directive_second, (
            f"user_directive not propagated to second attempt; got: {directive_second!r}"
        )


# ---------------------------------------------------------------------------
# Test: _build_scoped_prompt renders user_directive
# ---------------------------------------------------------------------------

class TestScopedBrainUserDirective:
    def _minimal_tactic(self) -> Tactic:
        return Tactic(
            id="web_search",
            phase_compatibility=["gather"],
            accepts={"query": ""},
            produces=[TaskSpec(technique_id="ddg_search")],
            cost_class="cheap",
        )

    def test_user_directive_appears_in_prompt(self):
        tactic = self._minimal_tactic()
        unit_of_work = {
            "query": "find Alice",
            "user_directive": "also check Twitter profiles",
        }
        prompt = _build_scoped_prompt(tactic, unit_of_work, capability_tier="general")
        assert "USER DIRECTIVE" in prompt
        assert "also check Twitter profiles" in prompt
        assert "mid-run steering" in prompt

    def test_user_directive_absent_when_not_set(self):
        tactic = self._minimal_tactic()
        unit_of_work = {"query": "find Bob"}
        prompt = _build_scoped_prompt(tactic, unit_of_work, capability_tier="general")
        assert "USER DIRECTIVE" not in prompt

    def test_user_directive_placement_after_corrective_hint(self):
        """user_directive section must appear before the ## Unit of Work section."""
        tactic = self._minimal_tactic()
        unit_of_work = {
            "query": "test",
            "user_directive": "my directive",
        }
        prompt = _build_scoped_prompt(tactic, unit_of_work, capability_tier="general")
        directive_pos = prompt.index("USER DIRECTIVE")
        uow_pos = prompt.index("## Unit of Work")
        assert directive_pos < uow_pos, "USER DIRECTIVE must appear before ## Unit of Work"

    def test_corrective_hint_and_directive_both_present(self):
        tactic = self._minimal_tactic()
        unit_of_work = {
            "query": "test",
            "corrective_hint": "try harder",
            "user_directive": "also check records",
        }
        prompt = _build_scoped_prompt(tactic, unit_of_work, capability_tier="general")
        assert "CORRECTIVE HINT" in prompt
        assert "USER DIRECTIVE" in prompt
        assert "also check records" in prompt
