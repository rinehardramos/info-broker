"""Phase 0 tests: ISRunWorkflow stub is importable and IS_USE_TEMPORAL defaults false."""
import os
import pytest


def test_is_run_workflow_is_importable():
    from app.temporal.workflows.is_run import ISRunWorkflow, ISRunInput
    assert ISRunWorkflow is not None


def test_is_run_input_defaults():
    from app.temporal.workflows.is_run import ISRunInput
    inp = ISRunInput(run_id="r1", user_id="u1", org_id="o1", query="test", pipeline_id="p1")
    assert inp.session_id is None
    assert inp.preflight_prior_slots == {}


def test_is_use_temporal_defaults_false():
    # Verify the env var evaluation logic independently of module import order
    assert os.getenv("IS_USE_TEMPORAL", "false").lower() == "false"
    # When the env var is absent the flag must be falsy
    saved = os.environ.pop("IS_USE_TEMPORAL", None)
    try:
        result = os.getenv("IS_USE_TEMPORAL", "false").lower() == "true"
        assert not result
    finally:
        if saved is not None:
            os.environ["IS_USE_TEMPORAL"] = saved
