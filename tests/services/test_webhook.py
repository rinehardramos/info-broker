"""Tests for signed webhook delivery service."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_sign_payload_is_deterministic():
    from app.services.webhook import _sign_payload
    with patch.dict("os.environ", {"WEBHOOK_SECRET": "test-secret"}):
        sig1 = _sign_payload("run-1", "succeeded", 1234567890)
        sig2 = _sign_payload("run-1", "succeeded", 1234567890)
    assert sig1 == sig2
    assert len(sig1) == 64  # SHA256 hex


def test_sign_payload_differs_on_different_inputs():
    from app.services.webhook import _sign_payload
    with patch.dict("os.environ", {"WEBHOOK_SECRET": "test-secret"}):
        sig1 = _sign_payload("run-1", "succeeded", 1000)
        sig2 = _sign_payload("run-1", "failed", 1000)
    assert sig1 != sig2


@pytest.mark.anyio
async def test_deliver_with_retry_success_on_first_attempt():
    from app.services.webhook import _deliver_with_retry
    mock_resp = MagicMock(status_code=200)
    with patch("app.services.webhook.execute"), \
         patch("app.services.webhook.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client
        await _deliver_with_retry("run-1", {"status": "succeeded"}, "https://example.com/cb")
    mock_client.post.assert_called_once()


@pytest.mark.anyio
async def test_deliver_with_retry_retries_on_connection_error():
    from app.services.webhook import _deliver_with_retry
    call_count = 0

    async def flaky_post(*a, **kw):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("timeout")
        return MagicMock(status_code=200)

    with patch("app.services.webhook.execute"), \
         patch("app.services.webhook.asyncio.sleep", new_callable=AsyncMock), \
         patch("app.services.webhook.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = flaky_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client
        await _deliver_with_retry("run-1", {"status": "succeeded"}, "https://example.com/cb")
    assert call_count == 3  # succeeded on third attempt
