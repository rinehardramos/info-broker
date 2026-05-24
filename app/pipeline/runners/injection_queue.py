"""injection_queue.py — in-memory per-run instruction injection queue.

Thread-safe store that bridges POST /v3/runs/{run_id}/inject → the running
Strategist phase loop.

IMPORTANT LIMITATIONS:
- In-memory, per-process only.  Entries are lost on API-process restart.
- Bridges inject_node → engine exclusively because agent-triggered runs execute
  in the SAME API process (asyncio.create_task in agent.py).  This does NOT
  work for out-of-process Temporal workers; if the Temporal path is ever
  activated, a durable queue (Redis, DB table) must replace this module.
"""
from __future__ import annotations

import threading
from typing import Dict, List

_lock: threading.Lock = threading.Lock()
_QUEUES: Dict[str, List[str]] = {}


def enqueue(run_id: str, instruction: str) -> None:
    """Append *instruction* to the pending queue for *run_id*."""
    with _lock:
        if run_id not in _QUEUES:
            _QUEUES[run_id] = []
        _QUEUES[run_id].append(instruction)


def drain(run_id: str) -> List[str]:
    """Return and clear all pending instructions for *run_id*.

    Returns an empty list if there are no pending instructions.
    """
    with _lock:
        instructions = _QUEUES.pop(run_id, [])
    return instructions


def pending_count(run_id: str) -> int:
    """Return the number of pending instructions for *run_id* (non-destructive)."""
    with _lock:
        return len(_QUEUES.get(run_id, []))
