"""Pre-research conflict-detection gate (Tier 1 priority #2).

Single LLM call (Gemini Flash if available) BEFORE research starts. Asks:
"Does this query refer unambiguously to one entity/situation, or are there
multiple plausible referents that would change the answer?" If ambiguous,
returns a clarification question the workflow uses to block on the user
before any research budget is spent.

Fail-open: if no LLM key is available or the call errors out, returns
not-ambiguous so the run proceeds normally.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field

from temporalio import activity

log = logging.getLogger(__name__)


@dataclass
class ConflictCheckInput:
    query: str


@dataclass
class ConflictCheckResult:
    ambiguous: bool
    ambiguity_kind: str = ""        # "entity" | "scope_temporal" | "scope_geo" | "composite"
    clarification_question: str = ""
    options: list[str] = field(default_factory=list)
    raw_reasoning: str = ""


_PROMPT = """You are screening a research question for AMBIGUITY before a research \
agent spends time and budget on it.

The agent will commit to ONE entity, ONE time window, and ONE situation. If the \
query plausibly refers to multiple distinct things (different companies sharing a \
name; different time periods; different geographic scopes; or genuinely composite \
subjects), the agent will waste turns researching the wrong one.

QUERY: {query}

Return JSON only. No prose, no markdown fences.

If the query is unambiguous (one clear referent for the entity, time window, scope):
{{"ambiguous": false}}

If ambiguous:
{{
  "ambiguous": true,
  "ambiguity_kind": "entity" | "scope_temporal" | "scope_geo" | "composite",
  "clarification_question": "<one short question to resolve the ambiguity>",
  "options": ["<option 1>", "<option 2>", ...]
}}

Notes:
- Multi-part questions about one subject (\"what did X do AND why\") are NOT ambiguous.
- Comparisons (\"X vs Y\") are NOT ambiguous — they're explicit comparisons.
- A subject name shared by multiple known entities IS ambiguous (\"Acme\" → which Acme?).
- A time window with no anchor (\"recent\" with no year) IS ambiguous if multiple periods make different answers.
"""


def _get_gemini_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one("SELECT value FROM core_settings WHERE key = 'gemini_api_key'", ())
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return ""


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    return raw


def _extract_json_object(raw: str) -> dict | None:
    """Try strict JSON first, then fenced extraction, then first-{ to last-}.

    Gemini frequently wraps JSON in prose or trailing explanations despite the
    'JSON only' instruction. This makes the parse forgiving rather than
    fail-open every time the model misbehaves.
    """
    raw = _strip_fences(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None


@activity.defn(name="conflict_check")
async def conflict_check(inp: ConflictCheckInput) -> ConflictCheckResult:
    """Run a single Gemini Flash call to flag query ambiguity. Fail-open."""
    gemini_key = _get_gemini_key()
    if not gemini_key:
        log.info("conflict_check: no Gemini key, skipping (fail-open)")
        return ConflictCheckResult(ambiguous=False, raw_reasoning="no_llm_available")

    prompt = _PROMPT.format(query=inp.query)
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=gemini_key,
        )
        resp = client.chat.completions.create(
            model="gemini-2.5-flash",
            max_tokens=1500,   # Gemini sometimes spends tokens on reasoning before output
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.choices[0].message.content or ""
    except Exception as exc:
        log.warning("conflict_check LLM call failed (non-fatal, fail-open): %s", exc)
        return ConflictCheckResult(ambiguous=False, raw_reasoning=f"error:{exc}")

    data = _extract_json_object(raw)
    if data is None:
        log.warning("conflict_check: could not parse JSON from LLM (fail-open). raw head=%r", raw[:200])
        return ConflictCheckResult(ambiguous=False, raw_reasoning=f"parse_failed:{raw[:120]}")

    if not isinstance(data, dict) or not data.get("ambiguous"):
        log.info("conflict_check: query is unambiguous")
        return ConflictCheckResult(ambiguous=False, raw_reasoning=raw[:200])

    log.info("conflict_check: query IS ambiguous (kind=%s): %s",
             data.get("ambiguity_kind", ""), data.get("clarification_question", "")[:120])
    return ConflictCheckResult(
        ambiguous=True,
        ambiguity_kind=str(data.get("ambiguity_kind", "")),
        clarification_question=str(data.get("clarification_question", "") or "")[:500],
        options=[str(o) for o in (data.get("options") or [])][:6],
        raw_reasoning=raw[:200],
    )
