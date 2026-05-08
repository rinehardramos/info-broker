"""Brain question/answer queue — manages the clarification loop between IS brain and user."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.routers.v3.auth import get_current_user

router = APIRouter(prefix="/v3/agent", tags=["v3-agent-brain"])
log = logging.getLogger(__name__)

# In-memory state keyed by run_id
_pending_events: dict[str, asyncio.Event] = {}
_pending_answers: dict[str, str] = {}

_ANSWER_TIMEOUT = 300  # 5 minutes


class BrainQuestionIn(BaseModel):
    run_id: str
    question: str
    options: list[str] = []
    uid: str = ""


class BrainAnswerIn(BaseModel):
    run_id: str
    answer: str


@router.post("/brain-question")
async def brain_question(body: BrainQuestionIn):
    """Called by the MCP ask_user tool. Pushes a WS event and waits for the user's answer."""
    from app.routers.v3.stream import push_event

    run_id = body.run_id
    uid = body.uid

    # Push question to frontend via WebSocket
    await push_event(uid, {
        "type": "brain.question",
        "run_id": run_id,
        "question": body.question,
        "options": body.options,
    })

    # Create event and wait for answer
    event = asyncio.Event()
    _pending_events[run_id] = event
    _pending_answers.pop(run_id, None)  # clear any stale answer

    try:
        await asyncio.wait_for(event.wait(), timeout=_ANSWER_TIMEOUT)
    except asyncio.TimeoutError:
        _pending_events.pop(run_id, None)
        raise HTTPException(status_code=408, detail="User did not answer in time")

    answer = _pending_answers.pop(run_id, "")
    _pending_events.pop(run_id, None)

    log.info("Brain Q&A for %s: Q=%s A=%s", run_id, body.question[:50], answer[:50])
    return {"answer": answer}


@router.post("/brain-answer")
async def brain_answer(body: BrainAnswerIn, user: dict = Depends(get_current_user)):
    """Called by the frontend when the user answers a brain question."""
    run_id = body.run_id

    event = _pending_events.get(run_id)
    if not event:
        raise HTTPException(status_code=404, detail="No pending question for this run")

    _pending_answers[run_id] = body.answer
    event.set()

    return {"status": "ok"}
