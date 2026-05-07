"""PDF export node — generates a PDF report from research findings."""

from __future__ import annotations

import logging
import os
from datetime import datetime

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)


class ExportPdfNode:
    node_type = "export_pdf"
    display_name = "Export PDF"
    category = "destination"
    config_schema = {
        "type": "object",
        "properties": {
            "include_analysis": {
                "type": "boolean",
                "title": "Include Analysis",
                "default": True,
                "description": "Include analysis data (entities, relationships, insights) if present",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        from fpdf import FPDF

        os.makedirs("/tmp/exports", exist_ok=True)

        include_analysis = config.get("include_analysis", True)
        run_id = context.run_id
        output_path = f"/tmp/exports/{run_id}.pdf"

        # Separate findings from analysis items
        findings = [item for item in inputs if item.get("source") != "analyzer"]
        analysis_items = [item for item in inputs if item.get("source") == "analyzer"]
        analysis = analysis_items[0] if analysis_items else None

        # Determine query from context or first finding
        query = getattr(context, "query", None) or (findings[0].get("query", "") if findings else "Research Report")
        date_str = datetime.now().strftime("%Y-%m-%d")

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # --- Title ---
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, "Research Report", ln=True)
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 7, f"Query: {_truncate(query, 100)}", ln=True)
        pdf.cell(0, 7, f"Date: {date_str}", ln=True)
        pdf.cell(0, 7, f"Run ID: {run_id}", ln=True)
        pdf.ln(5)

        # --- Findings section ---
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 9, "FINDINGS", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
        pdf.ln(3)

        if not findings:
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 7, "No findings.", ln=True)
        else:
            for i, f in enumerate(findings, 1):
                pdf.set_font("Helvetica", "B", 10)
                title = _truncate(f.get("title", f"Finding {i}"), 80)
                pdf.cell(0, 7, f"{i}. {title}", ln=True)

                pdf.set_font("Helvetica", "", 9)
                source = f.get("source", "")
                confidence = f.get("confidence", "")
                meta_parts = []
                if source:
                    meta_parts.append(f"Source: {source}")
                if confidence != "":
                    meta_parts.append(f"Confidence: {confidence}%")
                if meta_parts:
                    pdf.set_text_color(120, 120, 120)
                    pdf.cell(0, 6, "   " + " | ".join(meta_parts), ln=True)
                    pdf.set_text_color(0, 0, 0)

                content = f.get("content", "")
                if content:
                    excerpt = _safe_latin1(_truncate(content, 200))
                    pdf.set_font("Helvetica", "", 9)
                    pdf.set_x(pdf.l_margin)
                    pdf.multi_cell(0, 5, "   " + excerpt)

                url = f.get("url", "")
                if url:
                    pdf.set_font("Helvetica", "I", 8)
                    pdf.set_text_color(60, 100, 180)
                    pdf.cell(0, 5, "   " + _truncate(url, 100), ln=True)
                    pdf.set_text_color(0, 0, 0)

                pdf.ln(2)

        # --- Analysis section ---
        if include_analysis and analysis:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 13)
            pdf.cell(0, 9, "ANALYSIS", ln=True)
            pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
            pdf.ln(3)

            # Entities
            entities = analysis.get("entities", [])
            if entities:
                pdf.set_font("Helvetica", "B", 11)
                pdf.cell(0, 8, "Entities", ln=True)
                pdf.set_font("Helvetica", "", 9)
                for ent in entities:
                    name = ent.get("name", "")
                    etype = ent.get("type", "")
                    pdf.cell(0, 6, f"  - {name}" + (f" ({etype})" if etype else ""), ln=True)
                pdf.ln(3)

            # Relationships
            relationships = analysis.get("relationships", [])
            if relationships:
                pdf.set_font("Helvetica", "B", 11)
                pdf.cell(0, 8, "Relationships", ln=True)
                pdf.set_font("Helvetica", "", 9)
                for rel in relationships:
                    frm = rel.get("from", rel.get("from_entity", ""))
                    to = rel.get("to", rel.get("to_entity", ""))
                    rtype = rel.get("type", rel.get("relationship_type", ""))
                    pdf.cell(0, 6, f"  - {frm} --[{rtype}]--> {to}", ln=True)
                pdf.ln(3)

            # Insights
            insights = analysis.get("insights", analysis.get("key_insights", []))
            if insights:
                pdf.set_font("Helvetica", "B", 11)
                pdf.cell(0, 8, "Insights", ln=True)
                pdf.set_font("Helvetica", "", 9)
                for ins in insights:
                    text = ins if isinstance(ins, str) else ins.get("text", ins.get("insight", str(ins)))
                    safe_text = _safe_latin1(_truncate(text, 300))
                    pdf.set_x(pdf.l_margin)
                    pdf.multi_cell(0, 5, f"  - {safe_text}")
                pdf.ln(3)

            # Recommendations
            recs = analysis.get("recommendations", [])
            if recs:
                pdf.set_font("Helvetica", "B", 11)
                pdf.cell(0, 8, "Recommendations", ln=True)
                pdf.set_font("Helvetica", "", 9)
                for rec in recs:
                    text = rec if isinstance(rec, str) else rec.get("text", rec.get("recommendation", str(rec)))
                    safe_text = _safe_latin1(_truncate(text, 300))
                    pdf.set_x(pdf.l_margin)
                    pdf.multi_cell(0, 5, f"  - {safe_text}")
                pdf.ln(3)

        try:
            pdf.output(output_path)
            log.info("ExportPdfNode: wrote %s", output_path)
        except Exception as exc:
            log.error("ExportPdfNode: failed to write PDF: %s", exc)
            raise

        return [{
            "source": "export_pdf",
            "title": "PDF Report",
            "url": f"/v3/exports/files/{run_id}.pdf",
            "format": "pdf",
        }]


def _truncate(text: str, max_len: int) -> str:
    text = str(text)
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text


def _safe_latin1(text: str) -> str:
    """Encode text to latin-1, replacing unmappable characters, for fpdf2 Helvetica."""
    return text.encode("latin-1", errors="replace").decode("latin-1")
