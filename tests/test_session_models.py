from app.routers.v3.models import AgentMessageIn, AgentMessageOut, AgentSessionOut
import pytest


def test_agent_message_in_accepts_session_id():
    msg = AgentMessageIn(message="hello", session_id="abc-123")
    assert msg.session_id == "abc-123"


def test_agent_message_in_session_id_optional():
    msg = AgentMessageIn(message="hello")
    assert msg.session_id is None


def test_agent_message_out_has_session_id():
    out = AgentMessageOut(job_id="j1", session_id="s1", status="pending", mode="investigation")
    assert out.session_id == "s1"
    assert out.mode == "investigation"
    assert out.reply is None


def test_agent_message_out_conversational():
    out = AgentMessageOut(job_id=None, session_id="s1", status="done",
                          mode="conversational", reply="Here is what I found.")
    assert out.job_id is None
    assert out.reply == "Here is what I found."


def test_agent_session_out():
    import datetime
    session = AgentSessionOut(
        id="s1", user_id="u1", genesis_query="what is MemGPT?",
        status="active", created_at=datetime.datetime.now(),
        run_count=2, turn_count=3, accumulated_summary="MemGPT is...",
        conversation_thread=[], key_findings=[], entity_type="concept"
    )
    assert session.genesis_query == "what is MemGPT?"
