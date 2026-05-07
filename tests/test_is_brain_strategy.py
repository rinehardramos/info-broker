"""Test that entity_strategy flows through run_research to build_prompt."""
from unittest.mock import patch, AsyncMock, MagicMock
import asyncio


def _arun(coro): return asyncio.run(coro)


def test_run_research_passes_entity_strategy():
    """entity_strategy kwarg reaches build_prompt."""

    # Minimal fake process so run_research doesn't actually spawn Claude Code
    fake_proc = MagicMock()
    fake_proc.stdout = MagicMock()
    fake_proc.stderr = MagicMock()
    fake_proc.returncode = 0
    fake_proc.wait = AsyncMock(return_value=0)
    fake_proc.terminate = MagicMock()
    fake_proc.kill = MagicMock()

    # async iterator that yields nothing (empty stdout)
    async def _empty_aiter():
        return
        yield  # makes it an async generator

    fake_proc.stdout.__aiter__ = lambda self: _empty_aiter()

    async def _fake_exec(*args, **kwargs):
        return fake_proc

    with (
        patch("app.is_brain.build_prompt") as mock_build,
        patch("asyncio.create_subprocess_exec", new=_fake_exec),
    ):
        mock_build.return_value = "dummy prompt"

        from app.is_brain import run_research
        try:
            _arun(run_research(
                query="test",
                user_id="u1",
                entity_strategy="=== TEST STRATEGY ===",
            ))
        except Exception:
            pass  # We only care that build_prompt was called correctly

        assert mock_build.called, "build_prompt was never called"
        call_kwargs = mock_build.call_args.kwargs
        assert "entity_strategy" in call_kwargs, \
            f"entity_strategy not in build_prompt kwargs: {call_kwargs}"
        assert call_kwargs["entity_strategy"] == "=== TEST STRATEGY ==="
