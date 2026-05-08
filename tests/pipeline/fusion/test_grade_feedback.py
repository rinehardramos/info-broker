"""Tests for grade → overlay feedback loop."""
from unittest.mock import patch
from app.pipeline.fusion.grade_feedback import grade_to_overlay_action, apply_grade_feedback


def test_grade_a_reinforces():
    action = grade_to_overlay_action("A")
    assert action["overlay_type"] == "reinforce"
    assert action["confidence"] >= 0.9


def test_grade_b_reinforces():
    action = grade_to_overlay_action("B")
    assert action["overlay_type"] == "reinforce"


def test_grade_c_neutral():
    action = grade_to_overlay_action("C")
    assert action is None  # No overlay change


def test_grade_d_prunes():
    action = grade_to_overlay_action("D")
    assert action["overlay_type"] == "prune"


def test_grade_f_prunes_and_flags():
    action = grade_to_overlay_action("F")
    assert action["overlay_type"] == "prune"
    assert action["confidence"] >= 0.9
    assert action.get("flagged") is True


def test_apply_grade_feedback_calls_upsert():
    with patch("app.pipeline.fusion.grade_feedback._upsert_overlay") as mock:
        apply_grade_feedback(
            entity_type="person",
            selector_type="email",
            tool_name="run_hibp_lookup",
            grade="A",
        )
    assert mock.called
    call_args = mock.call_args[0][0]
    assert call_args["overlay_type"] == "reinforce"
    assert call_args["entity_type"] == "person"
    assert "hibp_lookup" in call_args["pivot_pattern"]


def test_apply_grade_feedback_neutral_skips_upsert():
    with patch("app.pipeline.fusion.grade_feedback._upsert_overlay") as mock:
        apply_grade_feedback(
            entity_type="person",
            selector_type="email",
            tool_name="run_smtp_verifier",
            grade="C",
        )
    assert not mock.called  # Neutral grade = no overlay change
