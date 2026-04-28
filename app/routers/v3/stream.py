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
