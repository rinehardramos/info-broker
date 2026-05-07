"""Excel export node — generates a multi-sheet XLSX from research findings and analysis."""

from __future__ import annotations

import logging
import os

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)


class ExportExcelNode:
    node_type = "export_excel"
    display_name = "Export Excel"
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
        output_path = f"/tmp/exports/{run_id}.xlsx"

        # Separate findings from analysis
        findings = [item for item in inputs if item.get("source") != "analyzer"]
        analysis_items = [item for item in inputs if item.get("source") == "analyzer"]
        analysis = analysis_items[0] if analysis_items else None

        # Sheet 1: Findings
        findings_rows = []
        for f in findings:
            findings_rows.append({
                "title": f.get("title", ""),
                "source": f.get("source", ""),
                "url": f.get("url", ""),
                "confidence": f.get("confidence", ""),
                "content": f.get("content", ""),
            })
        df_findings = pd.DataFrame(
            findings_rows,
            columns=["title", "source", "url", "confidence", "content"],
        )

        # Sheet 2: Entities
        entities = analysis.get("entities", []) if analysis else []
        entity_rows = []
        for ent in entities:
            attrs = ent.get("attributes", ent.get("properties", {}))
            entity_rows.append({
                "name": ent.get("name", ""),
                "type": ent.get("type", ent.get("entity_type", "")),
                "attributes": str(attrs) if attrs else "",
            })
        df_entities = pd.DataFrame(
            entity_rows,
            columns=["name", "type", "attributes"],
        )

        # Sheet 3: Relationships
        relationships = analysis.get("relationships", []) if analysis else []
        rel_rows = []
        for rel in relationships:
            rel_rows.append({
                "from": rel.get("from", rel.get("from_entity", "")),
                "to": rel.get("to", rel.get("to_entity", "")),
                "type": rel.get("type", rel.get("relationship_type", "")),
                "evidence": rel.get("evidence", rel.get("description", "")),
            })
        df_relationships = pd.DataFrame(
            rel_rows,
            columns=["from", "to", "type", "evidence"],
        )

        # Sheet 4: Insights & Recommendations
        insights = analysis.get("insights", analysis.get("key_insights", [])) if analysis else []
        recs = analysis.get("recommendations", []) if analysis else []

        insight_rows = []
        for ins in insights:
            text = ins if isinstance(ins, str) else ins.get("text", ins.get("insight", str(ins)))
            insight_rows.append({"type": "insight", "text": text})
        for rec in recs:
            text = rec if isinstance(rec, str) else rec.get("text", rec.get("recommendation", str(rec)))
            insight_rows.append({"type": "recommendation", "text": text})
        df_insights = pd.DataFrame(
            insight_rows,
            columns=["type", "text"],
        )

        try:
            with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
                df_findings.to_excel(writer, sheet_name="Findings", index=False)
                df_entities.to_excel(writer, sheet_name="Entities", index=False)
                df_relationships.to_excel(writer, sheet_name="Relationships", index=False)
                df_insights.to_excel(writer, sheet_name="Insights", index=False)
            log.info("ExportExcelNode: wrote %s (%d findings)", output_path, len(df_findings))
        except Exception as exc:
            log.error("ExportExcelNode: failed to write Excel: %s", exc)
            raise

        return [{
            "source": "export_excel",
            "title": "Excel Report",
            "url": f"/v3/exports/files/{run_id}.xlsx",
            "format": "xlsx",
        }]
