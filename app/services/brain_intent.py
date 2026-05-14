from __future__ import annotations
import asyncio
import json
import re
import shutil
from dataclasses import dataclass
from typing import Literal

IntentKind = Literal["list", "lookup", "comparison", "deep", "monitoring"]

INTENT_PROMPT = """Classify this user query for a research pipeline. Return ONLY a JSON object:
{
  "intent": one of "list"|"lookup"|"comparison"|"deep"|"monitoring",
  "confidence": float 0-1,
  "rationale": one sentence,
  "enriched_query": improved version of the query or null
}

Intent taxonomy:
- list: "list X", "who are all", "what are all" → wide breadth, parallel sources
- lookup: "what is", "find", "look up" → single authoritative source
- comparison: "X vs Y", "differences between" → parallel lookups + diff
- deep: "investigate", "research thoroughly" → full IS cycle
- monitoring: "track", "alert when", "watch" → baseline + recurring check

Query: {query}

Return JSON only."""

_CLAUDE_BIN: str = shutil.which("claude") or "claude"


@dataclass
class IntentResult:
    intent: IntentKind
    confidence: float
    rationale: str
    enriched_query: str | None = None


async def classify_intent_async(query: str) -> IntentResult:
    """Classify user query intent using Claude Code subprocess."""
    prompt = INTENT_PROMPT.replace("{query}", query)

    proc = await asyncio.create_subprocess_exec(
        _CLAUDE_BIN, "-p", prompt, "--output-format", "json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
    except asyncio.TimeoutError:
        proc.kill()
        return IntentResult(intent="deep", confidence=0.5, rationale="Timeout — defaulting to deep")

    text = stdout.decode(errors="replace").strip()
    # Claude Code json output wraps in {"result": "...", ...}
    try:
        outer = json.loads(text)
        inner_text = outer.get("result", text)
    except json.JSONDecodeError:
        inner_text = text

    # Strip markdown fences
    inner_text = re.sub(r"^```(?:json)?\n?", "", inner_text.strip())
    inner_text = re.sub(r"\n?```$", "", inner_text)

    try:
        data = json.loads(inner_text)
        return IntentResult(
            intent=data.get("intent", "deep"),
            confidence=float(data.get("confidence", 0.7)),
            rationale=data.get("rationale", ""),
            enriched_query=data.get("enriched_query"),
        )
    except (json.JSONDecodeError, KeyError):
        return IntentResult(intent="deep", confidence=0.5, rationale="Parse error — defaulting to deep")


def classify_intent(query: str) -> IntentResult:
    """Sync wrapper — runs the async classifier in a new event loop."""
    return asyncio.run(classify_intent_async(query))
