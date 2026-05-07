"""CSV export node — generates a CSV file from research findings."""

from __future__ import annotations

import logging
import os

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)


class ExportCsvNode:
    node_type = "export_csv"
    display_name = "Export CSV"
    category = "destination"
    config_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        import pandas as pd

        os.makedirs("/tmp/exports", exist_ok=True)

        run_id = context.run_id
        output_path = f"/tmp/exports/{run_id}.csv"

        # Build rows from inputs — exclude internal analyzer items
        findings = [item for item in inputs if item.get("source") != "analyzer"]

        rows = []
        for f in findings:
            rows.append({
                "title": f.get("title", ""),
                "source": f.get("source", ""),
                "url": f.get("url", ""),
                "confidence": f.get("confidence", ""),
                "content": f.get("content", ""),
            })

        df = pd.DataFrame(rows, columns=["title", "source", "url", "confidence", "content"])

        try:
            df.to_csv(output_path, index=False)
            log.info("ExportCsvNode: wrote %s (%d rows)", output_path, len(df))
        except Exception as exc:
            log.error("ExportCsvNode: failed to write CSV: %s", exc)
            raise

        return [{
            "source": "export_csv",
            "title": "CSV Report",
            "url": f"/v3/exports/files/{run_id}.csv",
            "format": "csv",
        }]
