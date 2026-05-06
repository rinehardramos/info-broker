from __future__ import annotations

import json
import uuid

from app.routers.v3.db import execute

_SECRET_KEYS = {"api_key", "token", "password", "secret", "key", "auth", "credential"}


def _scrub_params(params: dict | None) -> dict:
    if params is None:
        return {}
    scrubbed: dict = {}
    for k, v in params.items():
        if any(s in k.lower() for s in _SECRET_KEYS):
            scrubbed[k] = "***"
        else:
            scrubbed[k] = v
    return scrubbed


class McpTracker:
    async def start_session(
        self,
        caller_identity: str,
        session_type: str,
        context: dict | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        sid = session_id or str(uuid.uuid4())
        ctx = json.dumps(context or {})
        execute(
            """
            INSERT INTO mcp_sessions
                (id, caller_identity, user_id, session_type, context, status, started_at)
            VALUES
                (%s, %s, %s, %s, %s::jsonb, 'active', now())
            """,
            (sid, caller_identity, user_id, session_type, ctx),
        )
        return sid

    async def log_call_start(
        self,
        session_id: str,
        tool_name: str,
        node_type: str,
        call_id: str,
        caller_identity: str,
        input_params: dict | None = None,
        parent_call_id: str | None = None,
        user_id: str | None = None,
    ) -> str:
        row_id = str(uuid.uuid4())
        scrubbed = _scrub_params(input_params)
        params_json = json.dumps(scrubbed)
        execute(
            """
            INSERT INTO mcp_tool_calls
                (id, session_id, caller_identity, user_id, tool_name, node_type,
                 call_id, parent_call_id, status, input_params, created_at, updated_at)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, 'executing', %s::jsonb, now(), now())
            """,
            (
                row_id,
                session_id,
                caller_identity,
                user_id,
                tool_name,
                node_type,
                call_id,
                parent_call_id,
                params_json,
            ),
        )
        execute(
            """
            UPDATE mcp_sessions
               SET tool_call_count = tool_call_count + 1
             WHERE id = %s
            """,
            (session_id,),
        )
        return row_id

    async def log_call_complete(
        self,
        call_id: str,
        status: str,
        result_preview: str | None = None,
        result_count: int | None = None,
        duration_ms: int | None = None,
        error_message: str | None = None,
    ) -> None:
        preview = result_preview[:500] if result_preview else None
        execute(
            """
            UPDATE mcp_tool_calls
               SET status         = %s,
                   result_preview = %s,
                   result_count   = %s,
                   duration_ms    = %s,
                   error_message  = %s,
                   updated_at     = now()
             WHERE call_id = %s
            """,
            (status, preview, result_count, duration_ms, error_message, call_id),
        )

    async def end_session(self, session_id: str, status: str = "completed") -> None:
        execute(
            """
            UPDATE mcp_sessions
               SET status      = %s,
                   finished_at = now()
             WHERE id = %s
            """,
            (status, session_id),
        )


tracker = McpTracker()
