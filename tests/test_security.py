from __future__ import annotations
import pytest


def test_sanitize_strips_script_tag():
    from app.security import sanitize_user_input
    out = sanitize_user_input("<script>x</script>hi")
    assert "<script>" not in out
    assert "</script>" not in out


def test_sanitize_strips_img_onerror():
    from app.security import sanitize_user_input
    out = sanitize_user_input("<img src=x onerror=alert(1)>foo")
    assert "<img" not in out
    assert "onerror" not in out
    assert "foo" in out


def test_sanitize_truncates_to_max_length():
    from app.security import sanitize_user_input
    out = sanitize_user_input("a" * 9000, max_length=4000)
    assert len(out) == 4000


def test_sanitize_handles_none():
    from app.security import sanitize_user_input
    assert sanitize_user_input(None) == ""


def test_sanitize_idempotent():
    from app.security import sanitize_user_input
    once = sanitize_user_input("<b>hello</b>")
    twice = sanitize_user_input(once)
    assert once == twice


def test_agent_message_in_strips_html():
    from app.routers.v3.models import AgentMessageIn
    m = AgentMessageIn(message="<img src=x onerror=alert(1)>hello")
    assert "<img" not in m.message
    assert "hello" in m.message


def test_agent_message_in_max_length_8000():
    from pydantic import ValidationError
    from app.routers.v3.models import AgentMessageIn
    with pytest.raises(ValidationError):
        AgentMessageIn(message="x" * 8001)


def test_pipeline_in_strips_html():
    from app.routers.v3.models import PipelineIn
    p = PipelineIn(name="<script>alert(1)</script>My Pipeline")
    assert "<script>" not in p.name
    assert "My Pipeline" in p.name


def test_pipeline_in_name_max_length():
    from pydantic import ValidationError
    from app.routers.v3.models import PipelineIn
    with pytest.raises(ValidationError):
        PipelineIn(name="x" * 256)
