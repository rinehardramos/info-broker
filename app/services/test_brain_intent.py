from unittest.mock import AsyncMock, MagicMock, patch
from app.services.brain_intent import classify_intent_async
import asyncio
import json


def _mock_proc(stdout_text: str):
    proc = MagicMock()
    proc.communicate = AsyncMock(
        return_value=(stdout_text.encode(), b"")
    )
    return proc


def test_classify_list_intent():
    payload = json.dumps({
        "result": json.dumps({
            "intent": "list",
            "confidence": 0.95,
            "rationale": "Query starts with list",
            "enriched_query": None,
        })
    })
    with patch("app.services.brain_intent.asyncio.create_subprocess_exec", return_value=_mock_proc(payload)):
        result = asyncio.run(classify_intent_async("list all anime in 2026"))
    assert result.intent == "list"
    assert result.confidence == 0.95


def test_classify_timeout_returns_deep():
    import asyncio as _asyncio

    async def _timeout(*a, **kw):
        raise _asyncio.TimeoutError()

    with patch("app.services.brain_intent.asyncio.create_subprocess_exec") as mock_exec:
        proc = MagicMock()
        proc.kill = MagicMock()
        proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_exec.return_value = proc
        with patch("app.services.brain_intent.asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            result = asyncio.run(classify_intent_async("what is this"))
    assert result.intent == "deep"
