"""Tests for app/pipeline/tactician.py (MVP-M7).

All tests are synchronous (asyncio.get_event_loop().run_until_complete).
No real subprocesses or MCP calls are made -- tactic_runner_fn and
specialist_fn are injected fakes.

Gate properties defended per test:
  test_slot0_with_prior_research_selects_prior_research_seed
      -> tactic selection determinism (slot 0 + prior present -> prior_research_seed)
  test_slot1_selects_hypothesis_first_search
      -> tactic selection determinism (slot >= 1 -> hypothesis_first_search)
  test_specialist_fn_called_once_per_task_call
      -> specialist_fn is invoked for each task returned by tactic_runner_fn
  test_extracts_distinct_candidate_names_from_findings
      -> candidate_names deduplication from Finding.raw_output
  test_returns_correct_specialist_call_count
      -> specialist_calls counter matches actual invocations
  test_tactician_does_not_receive_peer_slot_data
      -> structural visibility invariant (section 7.2): no peer-state param in signature
  test_budget_exhaustion_stops_specialist_calls
      -> budget_ru ceiling prevents overspend; calls stop when ceiling hit
  test_no_tactic_for_phase_returns_empty_output_with_metadata_flag
      -> graceful degradation: metadata["no_tactic_for_phase"] is True
"""
from __future__ import annotations

import asyncio
import inspect
from typing import Any
from unittest.mock import MagicMock

from app.pipeline.catalogs.schemas import (
    CheckSpec,
    GateSpec,
    PhaseSpec,
    TaskSpec,
    Tactic,
    Technique,
)
from app.pipeline.specialist import Finding, SpecialistError
from app.pipeline.tactician import execute_tactician


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_phase(phase_id: str = "gather") -> PhaseSpec:
    return PhaseSpec(
        id=phase_id,
        depends_on=[],
        unit_of_work_contract={},
        hypothesis_count_policy="from_dial",
        gate=GateSpec(
            checks=[CheckSpec(kind="distinct_identity_count", params={"min": 3})],
            on_fail="replan",
        ),
    )


def _make_tactic(
    tactic_id: str,
    phase_ids: list[str] | None = None,
) -> Tactic:
    _phases = phase_ids if phase_ids is not None else ["gather"]
    return Tactic.model_validate({
        "id": tactic_id,
        "phase_compatibility": _phases,
        "accepts": {},
        "produces": [
            {
                "technique_id": "web_search",
                "params_template": {"query": "test"},
                "budget_ru": 1,
            }
        ],
        "cost_class": "moderate",
        "required_techniques": ["web_search"],
        "enforcement": {"min_distinct_outputs": 2},
    })

def _make_technique(technique_id: str = "web_search") -> Technique:
    return Technique(
        id=technique_id,
        tool_name="mcp__info-broker-mcp__web_search",
        input_schema={},
        output_schema={},
        cost_class="cheap",
    )


def _finding(candidate: str) -> Finding:
    return Finding(
        technique_id="web_search",
        params={"query": "test"},
        raw_output={
            "candidate": candidate,
            "url": "https://example.com",
            "snippet": f"Evidence for {candidate}",
            "confidence": 0.8,
        },
    )


def _task_call(technique_id: str = "web_search", budget_ru: int = 1) -> dict[str, Any]:
    return {
        "technique_id": technique_id,
        "params_template": {"query": "test query"},
        "expect_schema": {},
        "fail_modes": ["no_evidence"],
        "budget_ru": budget_ru,
    }


def _noop_mcp(tool_name: str, params: dict) -> Any:
    return {"results": []}


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Test: tactic selection determinism
# ---------------------------------------------------------------------------

class TestTacticSelection:
    def test_slot0_with_prior_research_selects_prior_research_seed(self):
        """slot_idx==0 with prior_research_summary -> prior_research_seed is picked."""
        phase = _make_phase("gather")
        tactics = {
            "hypothesis_first_search": _make_tactic("hypothesis_first_search"),
            "prior_research_seed": _make_tactic("prior_research_seed"),
        }
        techniques = {"web_search": _make_technique()}
        unit_of_work = {
            "objective": "verify RAG hit",
            "briefing": "",
            "prior_research_summary": "Zhao Lusi is a Chinese actress",
            "forbidden_candidates": [],
        }

        selected_tactics: list[str] = []

        def fake_runner(prompt: str, model: str) -> list[dict]:
            for line in prompt.splitlines():
                if line.startswith("tactic_id:"):
                    selected_tactics.append(line.split(":", 1)[1].strip())
            return []

        _run(execute_tactician(
            phase=phase,
            unit_of_work=unit_of_work,
            slot_idx=0,
            tactics_catalog=tactics,
            techniques_catalog=techniques,
            specialist_fn=lambda t, tech, mcp: SpecialistError("no_evidence", "fake"),
            mcp_invoke_fn=_noop_mcp,
            capability_tier="general",
            budget_ru=10,
            tactic_runner_fn=fake_runner,
        ))

        assert selected_tactics == ["prior_research_seed"]

    def test_slot1_selects_hypothesis_first_search(self):
        """slot_idx==1 -> hypothesis_first_search regardless of prior_research_summary."""
        phase = _make_phase("gather")
        tactics = {
            "hypothesis_first_search": _make_tactic("hypothesis_first_search"),
            "prior_research_seed": _make_tactic("prior_research_seed"),
        }
        techniques = {"web_search": _make_technique()}
        unit_of_work = {
            "objective": "find alternative candidate",
            "briefing": "",
            "prior_research_summary": "some prior",
            "forbidden_candidates": [],
        }

        selected_tactics: list[str] = []

        def fake_runner(prompt: str, model: str) -> list[dict]:
            for line in prompt.splitlines():
                if line.startswith("tactic_id:"):
                    selected_tactics.append(line.split(":", 1)[1].strip())
            return []

        _run(execute_tactician(
            phase=phase,
            unit_of_work=unit_of_work,
            slot_idx=1,
            tactics_catalog=tactics,
            techniques_catalog=techniques,
            specialist_fn=lambda t, tech, mcp: SpecialistError("no_evidence", "fake"),
            mcp_invoke_fn=_noop_mcp,
            capability_tier="general",
            budget_ru=10,
            tactic_runner_fn=fake_runner,
        ))

        assert selected_tactics == ["hypothesis_first_search"]


# ---------------------------------------------------------------------------
# Test: specialist dispatch
# ---------------------------------------------------------------------------

class TestSpecialistDispatch:
    def test_specialist_fn_called_once_per_task_call(self):
        """specialist_fn is invoked exactly once per task_call from tactic_runner_fn."""
        phase = _make_phase("gather")
        tactics = {"hypothesis_first_search": _make_tactic("hypothesis_first_search")}
        techniques = {"web_search": _make_technique()}

        call_log: list[str] = []

        def fake_specialist(task: TaskSpec, technique: Technique, mcp_fn) -> SpecialistError:
            call_log.append(task.technique_id)
            return SpecialistError("no_evidence", "fake")

        three_tasks = [_task_call(), _task_call(), _task_call()]

        result = _run(execute_tactician(
            phase=phase,
            unit_of_work={"objective": "test", "briefing": "", "forbidden_candidates": []},
            slot_idx=1,
            tactics_catalog=tactics,
            techniques_catalog=techniques,
            specialist_fn=fake_specialist,
            mcp_invoke_fn=_noop_mcp,
            capability_tier="general",
            budget_ru=10,
            tactic_runner_fn=lambda p, m: three_tasks,
        ))

        assert len(call_log) == 3
        assert result.specialist_calls == 3


# ---------------------------------------------------------------------------
# Test: candidate extraction and findings
# ---------------------------------------------------------------------------

class TestCandidateExtraction:
    def test_extracts_distinct_candidate_names_from_findings(self):
        """candidate_names is deduped; duplicate names from findings are collapsed."""
        phase = _make_phase("gather")
        tactics = {"hypothesis_first_search": _make_tactic("hypothesis_first_search")}
        techniques = {"web_search": _make_technique()}

        sequence = [_finding("Alice"), _finding("Bob"), _finding("Alice")]
        call_count = [0]

        def fake_specialist(task: TaskSpec, technique: Technique, mcp_fn) -> Finding:
            f = sequence[call_count[0]]
            call_count[0] += 1
            return f

        result = _run(execute_tactician(
            phase=phase,
            unit_of_work={"objective": "test", "briefing": "", "forbidden_candidates": []},
            slot_idx=1,
            tactics_catalog=tactics,
            techniques_catalog=techniques,
            specialist_fn=fake_specialist,
            mcp_invoke_fn=_noop_mcp,
            capability_tier="general",
            budget_ru=10,
            tactic_runner_fn=lambda p, m: [_task_call() for _ in range(3)],
        ))

        assert sorted(result.candidate_names) == ["Alice", "Bob"]
        assert len(result.findings) == 3

    def test_returns_correct_specialist_call_count(self):
        """TacticianOutput.specialist_calls equals actual number of specialist invocations."""
        phase = _make_phase("gather")
        tactics = {"hypothesis_first_search": _make_tactic("hypothesis_first_search")}
        techniques = {"web_search": _make_technique()}

        result = _run(execute_tactician(
            phase=phase,
            unit_of_work={"objective": "test", "briefing": "", "forbidden_candidates": []},
            slot_idx=1,
            tactics_catalog=tactics,
            techniques_catalog=techniques,
            specialist_fn=lambda t, tech, mcp: _finding("CandidateX"),
            mcp_invoke_fn=_noop_mcp,
            capability_tier="general",
            budget_ru=10,
            tactic_runner_fn=lambda p, m: [_task_call(), _task_call()],
        ))

        assert result.specialist_calls == 2


# ---------------------------------------------------------------------------
# Test: visibility invariant (section 7.2)
# ---------------------------------------------------------------------------

class TestVisibilityInvariant:
    def test_tactician_does_not_receive_peer_slot_data(self):
        """execute_tactician signature must have no peer-state parameter (section 7.2).

        Uses inspect.signature to assert no parameter name could carry
        cross-tactician data. The structural guarantee: the caller (strategist)
        cannot inject sibling findings into this function.
        """
        sig = inspect.signature(execute_tactician)
        param_names = set(sig.parameters.keys())

        forbidden = {
            "peer_findings",
            "peer_outputs",
            "peer_state",
            "sibling_findings",
            "sibling_outputs",
            "other_tacticians",
            "peer_candidates",
        }
        leaked = param_names & forbidden
        assert not leaked, (
            f"execute_tactician must not accept peer-state params (section 7.2). "
            f"Found: {leaked}. "
            f"See docs/intelligence/three-tier-brain-architecture.md section 7.2"
        )


# ---------------------------------------------------------------------------
# Test: budget enforcement
# ---------------------------------------------------------------------------

class TestBudgetEnforcement:
    def test_budget_exhaustion_stops_specialist_calls(self):
        """Specialist calls stop when cumulative cost would exceed budget_ru ceiling.

        3 tasks x 3 RU each, budget=5 RU -> only 1 call fits (3 <= 5; 3+3=6 > 5).
        """
        phase = _make_phase("gather")
        tactics = {"hypothesis_first_search": _make_tactic("hypothesis_first_search")}
        techniques = {"web_search": _make_technique()}

        expensive_tasks = [
            _task_call("web_search", budget_ru=3),
            _task_call("web_search", budget_ru=3),
            _task_call("web_search", budget_ru=3),
        ]

        result = _run(execute_tactician(
            phase=phase,
            unit_of_work={"objective": "test", "briefing": "", "forbidden_candidates": []},
            slot_idx=1,
            tactics_catalog=tactics,
            techniques_catalog=techniques,
            specialist_fn=lambda t, tech, mcp: _finding("SomeCandidate"),
            mcp_invoke_fn=_noop_mcp,
            capability_tier="general",
            budget_ru=5,
            tactic_runner_fn=lambda p, m: expensive_tasks,
        ))

        assert result.specialist_calls == 1
        assert result.metadata["ru_spent"] == 3


# ---------------------------------------------------------------------------
# Test: no compatible tactic
# ---------------------------------------------------------------------------

class TestNoCompatibleTactic:
    def test_no_tactic_for_phase_returns_empty_output_with_metadata_flag(self):
        """When no tactic is compatible with phase.id, return empty TacticianOutput.

        metadata["no_tactic_for_phase"] must be True so the strategist can
        detect the gap and decide whether to replan or terminate.
        tactic_runner_fn and specialist_fn must NOT be called.
        """
        phase = _make_phase("synthesize")
        # Tactics only cover "gather", not "synthesize"
        tactics = {
            "hypothesis_first_search": _make_tactic("hypothesis_first_search", ["gather"]),
        }
        techniques = {"web_search": _make_technique()}

        runner_mock = MagicMock(return_value=[])
        specialist_mock = MagicMock()

        result = _run(execute_tactician(
            phase=phase,
            unit_of_work={"objective": "rank", "briefing": "", "forbidden_candidates": []},
            slot_idx=0,
            tactics_catalog=tactics,
            techniques_catalog=techniques,
            specialist_fn=specialist_mock,
            mcp_invoke_fn=_noop_mcp,
            capability_tier="general",
            budget_ru=10,
            tactic_runner_fn=runner_mock,
        ))

        assert result.metadata.get("no_tactic_for_phase") is True
        assert result.candidate_names == []
        assert result.findings == []
        assert result.specialist_calls == 0
        runner_mock.assert_not_called()
        specialist_mock.assert_not_called()
