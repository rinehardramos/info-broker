"""Tests for messaging platform check node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.messaging_check import MessagingCheckNode, _check_telegram, _check_platforms
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = MessagingCheckNode()
    assert node.node_type == "messaging_check"
    assert node.category == "enrich"

def test_check_telegram_found():
    resp = MagicMock(status_code=200)
    resp.text = '<div class="tgme_page_title">John Doe</div>'
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        result = _check_telegram("johndoe")
    assert result["exists"] is True
    assert result["platform"] == "telegram"

def test_check_telegram_not_found():
    resp = MagicMock(status_code=200)
    resp.text = "If you have <strong>Telegram</strong>, you can contact"  # no tgme_page_title
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        result = _check_telegram("nonexist_user_xyz")
    assert result["exists"] is False

def test_execute_checks_platforms():
    with patch("app.pipeline.nodes.messaging_check._check_platforms") as m:
        m.return_value = {
            "telegram": {"exists": True, "username": "johndoe"},
            "whatsapp": {"exists": None, "note": "requires phone number"},
            "signal": {"exists": None, "note": "requires phone number"},
        }
        results = _arun(MessagingCheckNode().execute(
            {"phone": "+1234", "username": "johndoe"}, [], CTX))
    assert len(results) == 1
    assert results[0]["telegram"]["exists"] is True

def test_execute_from_inputs():
    with patch("app.pipeline.nodes.messaging_check._check_platforms") as m:
        m.return_value = {"telegram": {"exists": False}, "whatsapp": {"exists": None}, "signal": {"exists": None}}
        results = _arun(MessagingCheckNode().execute({}, [{"username": "test"}], CTX))
    assert len(results) == 1

def test_execute_no_input_error():
    results = _arun(MessagingCheckNode().execute({}, [], CTX))
    assert results[0].get("error")
