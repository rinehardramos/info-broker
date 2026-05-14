from __future__ import annotations
import json
import re
from dataclasses import dataclass
from typing import Literal

import anthropic

IntentKind = Literal["list", "lookup", "comparison", "deep", "monitoring"]

INTENT_SYSTEM = """You are an intent classifier for a research pipeline.
Given a user query, return ONLY a JSON object with these fields:
{
  "intent": one of "list"|"lookup"|"comparison"|"deep"|"monitoring",
  "confidence": float 0-1,
  "rationale": one sentence,
  "enriched_query": optional improved version of the query or null
}

Intent taxonomy:
- list: "list X", "who are all", "what are all" → wide breadth, parallel sources
- lookup: "what is", "find", "look up" → single authoritative source
- comparison: "X vs Y", "differences between" → parallel lookups + diff
- deep: "investigate", "research thoroughly", open-ended → full IS cycle
- monitoring: "track", "alert when", "watch" → baseline + recurring check

Reply with JSON only, no markdown fences."""


@dataclass
class IntentResult:
    intent: IntentKind
    confidence: float
    rationale: str
    enriched_query: str | None = None


_client = anthropic.Anthropic()


def classify_intent(query: str) -> IntentResult:
    """Classify user query intent. Uses Haiku for speed."""
    response = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system=INTENT_SYSTEM,
        messages=[{"role": "user", "content": query}],
    )
    text = response.content[0].text.strip()
    text = re.sub(r"^```(?:json)?\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    data = json.loads(text)
    return IntentResult(
        intent=data["intent"],
        confidence=float(data.get("confidence", 0.8)),
        rationale=data.get("rationale", ""),
        enriched_query=data.get("enriched_query"),
    )
