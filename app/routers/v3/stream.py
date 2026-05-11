from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)
router = APIRouter(tags=["v3-stream"])

# In-process event bus: user_id → set of queues
_queues: dict[str, set[asyncio.Queue]] = defaultdict(set)


async def push_event(user_id: str, event: dict) -> None:
    """Push a JSON event to all WebSocket connections for this user."""
    dead = set()
    for q in list(_queues.get(user_id, [])):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.add(q)
    for q in dead:
        _queues[user_id].discard(q)


@router.websocket("/v3/stream")
async def stream(websocket: WebSocket):
    await websocket.accept()

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    try:
        import os
        from jose import JWTError, jwt
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "change-me-in-production"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id or payload.get("type") != "access":
            await websocket.close(code=4001, reason="Invalid token")
            return
    except JWTError:
        await websocket.close(code=4001, reason="Invalid token")
        return

    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _queues[user_id].add(queue)
    log.info("WebSocket connected: user=%s", user_id)

    # Replay any pending confirmation gates so the user sees them after reconnect
    try:
        from app.routers.v3.agent import _CONFIRM_PENDING
        for run_id, pending in list(_CONFIRM_PENDING.items()):
            if run_id.startswith("rejected:") or not isinstance(pending, dict):
                continue
            if pending.get("uid") == user_id:
                result = pending.get("result", {})
                top = (result.get("findings") or [{}])[0]
                queue.put_nowait({
                    "type": "brain.confirm",
                    "run_id": run_id,
                    "job_id": run_id,
                    "candidate": top.get("title", ""),
                    "candidate_desc": (top.get("content") or "")[:120],
                    "confidence": top.get("confidence", 0),
                    "alternatives": result.get("considered_alternatives", [])[:3],
                    "replayed": True,
                })
                log.info("Replayed brain.confirm for run=%s user=%s", run_id, user_id)
    except Exception as exc:
        log.warning("brain.confirm replay failed: %s", exc)

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30)
                await websocket.send_text(json.dumps(event))
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        log.info("WebSocket disconnected: user=%s", user_id)
    finally:
        _queues[user_id].discard(queue)
