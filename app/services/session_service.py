"""Session service — manage investigation sessions for agent chat."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

_CLASSIFIER_PROMPT = """\
You are classifying a follow-up message in an ongoing investigation session.

Session genesis query: {genesis_query}
Conversation thread (last 5 turns):
{thread_excerpt}
Accumulated session summary: {summary}

Latest user message: {message}

Classify the latest message as ONE of:
- "investigation": requires fetching new data the session does not yet have \
(new entity, new angle, scope change, cannot be answered from existing findings)
- "conversational": can be answered from existing session findings plus at most \
one targeted tool call (narrowing, filtering, clarifying what was found)

Respond with valid JSON only: {{"mode": "investigation"|"conversational", "reasoning": "brief reason"}}
"""


def _call_classifier(
    message: str, genesis_query: str, thread: list[dict], summary: str
) -> str:
    """Call Haiku to classify the turn. Returns 'investigation' or 'conversational'."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
        thread_excerpt = "\n".join(
            f"[{t.get('role','?')}]: {str(t.get('content',''))[:200]}"
            for t in (thread or [])[-5:]
        )
        prompt = _CLASSIFIER_PROMPT.format(
            genesis_query=genesis_query or message,
            thread_excerpt=thread_excerpt or "(none)",
            summary=summary[:500] if summary else "(none)",
            message=message,
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        data = json.loads(text)
        mode = data.get("mode", "investigation")
        return mode if mode in ("investigation", "conversational") else "investigation"
    except Exception as exc:
        log.warning("Classifier failed (%s) — defaulting to investigation", exc)
        return "investigation"


def classify_turn(
    message: str,
    conversation_thread: list[dict] | None,
    accumulated_summary: str | None,
    genesis_query: str = "",
) -> str:
    """Return 'investigation' or 'conversational' for this turn."""
    if not conversation_thread:
        return "investigation"
    return _call_classifier(
        message=message,
        genesis_query=genesis_query or message,
        thread=conversation_thread or [],
        summary=accumulated_summary or "",
    )


def build_session_context(session: dict | None, current_message: str) -> str:
    """Build the session_context string for IS brain prompt injection."""
    if not session:
        return ""

    genesis = session.get("genesis_query", "")
    thread = session.get("conversation_thread") or []
    summary = session.get("accumulated_summary") or ""
    key_findings = session.get("key_findings") or []
    turn_count = session.get("turn_count", 0)

    thread_lines = []
    for t in thread[-5:]:
        role = t.get("role", "?")
        content = str(t.get("content", ""))[:300]
        thread_lines.append(f"[{role}]: {content}")
    thread_excerpt = "\n".join(thread_lines) if thread_lines else "(no prior turns)"

    findings_lines = []
    for f in key_findings[:5]:
        title = f.get("title", "?")
        conf = f.get("confidence", "?")
        findings_lines.append(f"  - [{conf}%] {title}")
    findings_text = "\n".join(findings_lines) if findings_lines else "  (none yet)"

    return f"""## SESSION CONTEXT
This is turn {turn_count + 1} of an ongoing investigation session.

Genesis query (the original question anchoring this session):
  "{genesis}"

Conversation thread (how the investigation has evolved):
{thread_excerpt}

What has been found so far:
{summary or "(nothing yet)"}

Key confirmed findings from prior turns:
{findings_text}

Current message (the latest refinement/direction):
  "{current_message}"

INSTRUCTIONS: The current message evolves the session — it may widen, narrow,
redirect, or add constraints to the genesis query. Your strategy, tactics, and
investigation scope should reflect the FULL session intent, not just the latest
message in isolation. Do not re-investigate what was already confirmed in prior
turns. Build on what exists.
"""


def distil_summary(findings: list[dict], current_summary: str) -> str:
    """Distil a compact running summary from findings. Returns empty string on failure."""
    if not findings:
        return current_summary or ""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
        findings_text = "\n".join(
            f"- [{f.get('confidence','?')}%] {f.get('title','?')}: {str(f.get('content',''))[:200]}"
            for f in findings[:20]
        )
        prompt = (
            f"Prior summary:\n{current_summary or '(none)'}\n\n"
            f"New findings:\n{findings_text}\n\n"
            "Write a compact (≤200 word) updated summary integrating the new findings with the prior summary. "
            "Preserve confirmed facts. Drop speculative or low-confidence items. Plain text only."
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        log.warning("distil_summary failed: %s", exc)
        return current_summary or ""


def build_conversational_reply(
    message: str, session: dict, tool_result: str = ""
) -> str:
    """Build a conversational reply using session context + optional tool result."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
        ctx = build_session_context(session, message)
        content = ctx
        if tool_result:
            content += f"\n\nAdditional data from targeted lookup:\n{tool_result[:2000]}"
        content += f"\n\nUser question: {message}\n\nProvide a concise, direct answer based on the session context above."
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": content}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        log.warning("build_conversational_reply failed: %s", exc)
        return "I couldn't generate a reply from the session context. Please try again."


def update_session_after_run(
    session_id: str,
    user_message: str,
    agent_summary: str,
    run_id: str | None,
    findings: list[dict],
    entity_type: str,
    is_investigation: bool,
) -> None:
    """Update session thread, summary, key_findings after a run completes."""
    try:
        from app.routers.v3.db import fetch_one, execute
        session = fetch_one(
            "SELECT * FROM agent_sessions WHERE id = %s", (session_id,)
        )
        if not session:
            return

        thread = list(session.get("conversation_thread") or [])
        now = datetime.now(timezone.utc).isoformat()
        thread.append({"role": "user", "content": user_message, "ts": now})
        thread.append({
            "role": "agent",
            "content": agent_summary[:500],
            "run_id": run_id,
            "ts": now,
        })

        existing = list(session.get("key_findings") or [])
        all_findings = existing + (findings or [])
        seen_titles: set[str] = set()
        unique: list[dict] = []
        for f in sorted(all_findings, key=lambda x: x.get("confidence", 0), reverse=True):
            t = f.get("title", "")
            if t and t not in seen_titles:
                seen_titles.add(t)
                unique.append(f)
        key_findings = unique[:5]

        new_summary = distil_summary(findings, session.get("accumulated_summary") or "")

        execute(
            """UPDATE agent_sessions SET
                conversation_thread = %s,
                accumulated_summary = %s,
                key_findings = %s,
                entity_type = %s,
                turn_count = turn_count + 1,
                run_count = run_count + %s
            WHERE id = %s""",
            (
                json.dumps(thread),
                new_summary,
                json.dumps(key_findings),
                entity_type or "unknown",
                1 if is_investigation else 0,
                session_id,
            ),
        )
    except Exception as exc:
        log.warning("update_session_after_run failed: %s", exc)
