from __future__ import annotations

from app.pipeline.nodes.base import RunContext


class ManualScoringNode:
    node_type = "manual_scoring"
    display_name = "Manual Scoring"
    category = "score"
    config_schema = {
        "type": "object",
        "properties": {
            "score_field": {
                "type": "string",
                "title": "Output Field",
                "default": "manual_score",
                "description": "Field name written to each item.",
            },
            "default_score": {
                "type": "integer",
                "title": "Default Score (0–100)",
                "default": 50,
                "minimum": 0,
                "maximum": 100,
                "description": "Score assigned to every item — intended as a placeholder until a human reviews.",
            },
            "label": {
                "type": "string",
                "title": "Review Label",
                "default": "needs_review",
                "description": "Tag added to each item to signal it awaits human grading.",
            },
        },
        "required": [],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        score_field = config.get("score_field", "manual_score")
        default_score = int(config.get("default_score", 50))
        label = config.get("label", "needs_review")

        return [
            {
                **item,
                score_field: default_score,
                "review_label": label,
                "review_run_id": context.run_id,
            }
            for item in inputs
        ]
