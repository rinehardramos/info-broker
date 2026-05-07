from __future__ import annotations

from app.llm_models import general_model
from app.pipeline.nodes.base import RunContext


class AiScoringNode:
    node_type = "ai_scoring"
    display_name = "AI Scoring"
    category = "score"
    config_schema = {
        "type": "object",
        "properties": {
            "criteria": {
                "type": "string",
                "title": "Scoring Criteria",
                "description": "Describe what makes an item high-quality (used as LLM prompt).",
            },
            "score_field": {
                "type": "string",
                "title": "Output Field",
                "default": "ai_score",
                "description": "Field name written to each item with the 0–100 score.",
            },
            "model": {
                "type": "string",
                "title": "Model",
                "default": "claude-haiku-4-5-20251001",
                "enum": [
                    "claude-haiku-4-5-20251001",
                    "claude-sonnet-4-6",
                    "claude-opus-4-7",
                ],
            },
            "threshold": {
                "type": "integer",
                "title": "Pass Threshold (0–100)",
                "default": 50,
                "minimum": 0,
                "maximum": 100,
                "description": "Items scoring below this value are marked failing but not dropped.",
            },
        },
        "required": ["criteria"],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        import anthropic
        import json

        criteria = config.get("criteria", "")
        score_field = config.get("score_field", "ai_score")
        model = config.get("model") or general_model()
        threshold = int(config.get("threshold", 50))

        if not inputs:
            return []

        client = anthropic.Anthropic()
        results = []
        for item in inputs:
            snippet = str(item.get("snippet") or item.get("title") or item)[:1000]
            prompt = (
                f"Score the following item from 0 to 100 based on this criteria: {criteria}\n\n"
                f"Item: {snippet}\n\n"
                "Reply with a JSON object: {\"score\": <integer 0-100>, \"reason\": \"<one sentence>\"}. "
                "No other text."
            )
            try:
                message = client.messages.create(
                    model=model,
                    max_tokens=128,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = message.content[0].text.strip()
                parsed = json.loads(raw)
                score = int(parsed.get("score", 0))
                reason = parsed.get("reason", "")
            except Exception:
                score = 0
                reason = "scoring failed"

            results.append({
                **item,
                score_field: score,
                f"{score_field}_reason": reason,
                f"{score_field}_pass": score >= threshold,
            })

        return results
