"""Tests for the SMTP email verifier node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.smtp_verifier import SmtpVerifierNode, _check_smtp, _get_mx_host
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = SmtpVerifierNode()
    assert node.node_type == "smtp_verifier"
    assert node.category == "enrich"
    assert "email" in node.config_schema["properties"]

def test_get_mx_host_returns_host():
    with patch("app.pipeline.nodes.smtp_verifier.dns_resolver") as mock_dns:
        mock_record = MagicMock()
        mock_record.exchange.to_text.return_value = "mx.gmail.com."
        mock_record.preference = 10
        mock_answer = MagicMock()
        mock_answer.__iter__ = lambda self: iter([mock_record])
        mock_dns.resolve.return_value = mock_answer
        assert _get_mx_host("gmail.com") == "mx.gmail.com"

def test_get_mx_host_none_on_failure():
    with patch("app.pipeline.nodes.smtp_verifier.dns_resolver") as mock_dns:
        mock_dns.resolve.side_effect = Exception("NXDOMAIN")
        assert _get_mx_host("bad.invalid") is None

def test_check_smtp_true_on_250():
    srv = MagicMock()
    srv.__enter__ = MagicMock(return_value=srv)
    srv.__exit__ = MagicMock(return_value=False)
    srv.helo.return_value = (250, b"OK")
    srv.mail.return_value = (250, b"OK")
    srv.rcpt.return_value = (250, b"OK")
    with patch("smtplib.SMTP", return_value=srv):
        assert _check_smtp("a@b.com", "mx.b.com", 5) is True

def test_check_smtp_false_on_550():
    srv = MagicMock()
    srv.__enter__ = MagicMock(return_value=srv)
    srv.__exit__ = MagicMock(return_value=False)
    srv.helo.return_value = (250, b"OK")
    srv.mail.return_value = (250, b"OK")
    srv.rcpt.return_value = (550, b"No such user")
    with patch("smtplib.SMTP", return_value=srv):
        assert _check_smtp("a@b.com", "mx.b.com", 5) is False

def test_check_smtp_none_on_timeout():
    with patch("smtplib.SMTP", side_effect=TimeoutError):
        assert _check_smtp("a@b.com", "mx.b.com", 5) is None

def test_execute_verifies_email():
    with (
        patch("app.pipeline.nodes.smtp_verifier._get_mx_host", return_value="mx.x.com"),
        patch("app.pipeline.nodes.smtp_verifier._check_smtp", return_value=True),
    ):
        results = _arun(SmtpVerifierNode().execute({"email": "j@x.com"}, [], CTX))
    assert results[0]["exists"] is True
    assert results[0]["mx_host"] == "mx.x.com"

def test_execute_from_inputs():
    with (
        patch("app.pipeline.nodes.smtp_verifier._get_mx_host", return_value="mx.t.com"),
        patch("app.pipeline.nodes.smtp_verifier._check_smtp", return_value=False),
    ):
        results = _arun(SmtpVerifierNode().execute({}, [{"email": "a@t.com"}], CTX))
    assert results[0]["exists"] is False

def test_execute_no_mx_returns_null():
    with patch("app.pipeline.nodes.smtp_verifier._get_mx_host", return_value=None):
        results = _arun(SmtpVerifierNode().execute({"email": "a@bad.xyz"}, [], CTX))
    assert results[0]["exists"] is None
