"""Export API — trigger and download research exports (PDF, CSV, Excel)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import fetch_one

router = APIRouter(prefix="/v3/exports", tags=["v3-exports"])
log = logging.getLogger(__name__)

_EXPORTS_DIR = "/tmp/exports"

_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class ExportRequest(BaseModel):
    format: str = "pdf"  # "pdf" | "csv" | "xlsx"
    include_analysis: bool = True


@router.post("/research/{run_id}")
def trigger_export(
    run_id: str,
    body: ExportRequest,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Generate an export file for a research trail run and return its download URL."""
    fmt = body.format.lower()
    if fmt not in _MEDIA_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt!r}. Use pdf, csv, or xlsx.")

    # Fetch research trail by run_id
    row = fetch_one(
        "SELECT query, findings, analysis FROM research_trails WHERE run_id = %s",
        (run_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Research trail not found for run_id={run_id!r}")

    findings = row.get("findings") or []
    if isinstance(findings, str):
        findings = json.loads(findings)

    analysis = row.get("analysis")
    if isinstance(analysis, str):
        analysis = json.loads(analysis)

    query = row.get("query", "Research Report")

    os.makedirs(_EXPORTS_DIR, exist_ok=True)
    output_path = f"{_EXPORTS_DIR}/{run_id}.{fmt}"

    try:
        if fmt == "pdf":
            _generate_pdf(run_id, query, findings, analysis if body.include_analysis else None, output_path)
        elif fmt == "csv":
            _generate_csv(findings, output_path)
        elif fmt == "xlsx":
            _generate_excel(findings, analysis if body.include_analysis else None, output_path)
    except Exception as exc:
        log.error("Export generation failed for run_id=%s fmt=%s: %s", run_id, fmt, exc)
        raise HTTPException(status_code=500, detail=f"Export generation failed: {exc}")

    filename = f"{run_id}.{fmt}"
    return {"filename": filename, "url": f"/v3/exports/files/{filename}"}


@router.get("/files/{filename}")
def download_export(filename: str) -> FileResponse:
    """Serve an export file. No auth required — files are ephemeral and URL is the token."""
    # Prevent path traversal
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = f"{_EXPORTS_DIR}/{safe_name}"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Export file not found")

    ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    media_type = _MEDIA_TYPES.get(ext, "application/octet-stream")

    return FileResponse(path=file_path, media_type=media_type, filename=safe_name)


# ---------------------------------------------------------------------------
# Internal generators (same logic as the pipeline nodes, but callable directly)
# ---------------------------------------------------------------------------

def _generate_pdf(run_id: str, query: str, findings: list[dict], analysis: dict | None, output_path: str) -> None:
    from fpdf import FPDF
    from datetime import datetime

    date_str = datetime.now().strftime("%Y-%m-%d")

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_left_margin(10)
    pdf.set_right_margin(10)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Research Report", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, f"Query: {_trunc(query, 100)}", ln=True)
    pdf.cell(0, 7, f"Date: {date_str}", ln=True)
    pdf.cell(0, 7, f"Run ID: {run_id}", ln=True)
    pdf.ln(5)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 9, "FINDINGS", ln=True)
    pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
    pdf.ln(3)

    if not findings:
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, "No findings.", ln=True)
    else:
        for i, f in enumerate(findings, 1):
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 7, f"{i}. {_trunc(f.get('title', f'Finding {i}'), 80)}", ln=True)
            pdf.set_font("Helvetica", "", 9)
            parts = []
            if f.get("source"):
                parts.append(f"Source: {f['source']}")
            if f.get("confidence") is not None:
                parts.append(f"Confidence: {f['confidence']}%")
            if parts:
                pdf.set_text_color(120, 120, 120)
                pdf.cell(0, 6, "   " + " | ".join(parts), ln=True)
                pdf.set_text_color(0, 0, 0)
            if f.get("content"):
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 5, "   " + _trunc(f["content"], 200))
            if f.get("url"):
                pdf.set_font("Helvetica", "I", 8)
                pdf.set_text_color(60, 100, 180)
                pdf.cell(0, 5, "   " + _trunc(f["url"], 100), ln=True)
                pdf.set_text_color(0, 0, 0)
            pdf.ln(2)

    if analysis:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 9, "ANALYSIS", ln=True)
        pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
        pdf.ln(3)

        for ent in analysis.get("entities", []):
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 8, "Entities", ln=True)
            pdf.set_font("Helvetica", "", 9)
            name = ent.get("name", "")
            etype = ent.get("type", "")
            pdf.cell(0, 6, _safe(f"  - {name}" + (f" ({etype})" if etype else "")), ln=True)
            break

        for ent in analysis.get("entities", [])[1:]:
            name = ent.get("name", "")
            etype = ent.get("type", "")
            pdf.set_font("Helvetica", "", 9)
            pdf.cell(0, 6, _safe(f"  - {name}" + (f" ({etype})" if etype else "")), ln=True)

        if analysis.get("relationships"):
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 8, "Relationships", ln=True)
            pdf.set_font("Helvetica", "", 9)
            for rel in analysis["relationships"]:
                frm = rel.get("from", rel.get("from_entity", ""))
                to = rel.get("to", rel.get("to_entity", ""))
                rtype = rel.get("type", rel.get("relationship_type", ""))
                pdf.cell(0, 6, _safe(f"  - {frm} --[{rtype}]--> {to}"), ln=True)

        insights = analysis.get("insights", analysis.get("key_insights", []))
        if insights:
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 8, "Insights", ln=True)
            pdf.set_font("Helvetica", "", 9)
            for ins in insights:
                text = ins if isinstance(ins, str) else ins.get("text", ins.get("insight", str(ins)))
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 5, f"  - {_trunc(text, 300)}")

        recs = analysis.get("recommendations", [])
        if recs:
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 8, "Recommendations", ln=True)
            pdf.set_font("Helvetica", "", 9)
            for rec in recs:
                text = rec if isinstance(rec, str) else rec.get("text", rec.get("recommendation", str(rec)))
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 5, f"  - {_trunc(text, 300)}")

    pdf.output(output_path)


def _generate_csv(findings: list[dict], output_path: str) -> None:
    import pandas as pd

    rows = [
        {
            "title": f.get("title", ""),
            "source": f.get("source", ""),
            "url": f.get("url", ""),
            "confidence": f.get("confidence", ""),
            "content": f.get("content", ""),
        }
        for f in findings
    ]
    df = pd.DataFrame(rows, columns=["title", "source", "url", "confidence", "content"])
    df.to_csv(output_path, index=False)


def _generate_excel(findings: list[dict], analysis: dict | None, output_path: str) -> None:
    import pandas as pd

    findings_rows = [
        {
            "title": f.get("title", ""),
            "source": f.get("source", ""),
            "url": f.get("url", ""),
            "confidence": f.get("confidence", ""),
            "content": f.get("content", ""),
        }
        for f in findings
    ]
    df_findings = pd.DataFrame(findings_rows, columns=["title", "source", "url", "confidence", "content"])

    entities = analysis.get("entities", []) if analysis else []
    entity_rows = [
        {
            "name": e.get("name", ""),
            "type": e.get("type", e.get("entity_type", "")),
            "attributes": str(e.get("attributes", e.get("properties", ""))),
        }
        for e in entities
    ]
    df_entities = pd.DataFrame(entity_rows, columns=["name", "type", "attributes"])

    relationships = analysis.get("relationships", []) if analysis else []
    rel_rows = [
        {
            "from": r.get("from", r.get("from_entity", "")),
            "to": r.get("to", r.get("to_entity", "")),
            "type": r.get("type", r.get("relationship_type", "")),
            "evidence": r.get("evidence", r.get("description", "")),
        }
        for r in relationships
    ]
    df_relationships = pd.DataFrame(rel_rows, columns=["from", "to", "type", "evidence"])

    insights = analysis.get("insights", analysis.get("key_insights", [])) if analysis else []
    recs = analysis.get("recommendations", []) if analysis else []
    insight_rows = [
        {"type": "insight", "text": ins if isinstance(ins, str) else ins.get("text", ins.get("insight", str(ins)))}
        for ins in insights
    ] + [
        {"type": "recommendation", "text": rec if isinstance(rec, str) else rec.get("text", rec.get("recommendation", str(rec)))}
        for rec in recs
    ]
    df_insights = pd.DataFrame(insight_rows, columns=["type", "text"])

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_findings.to_excel(writer, sheet_name="Findings", index=False)
        df_entities.to_excel(writer, sheet_name="Entities", index=False)
        df_relationships.to_excel(writer, sheet_name="Relationships", index=False)
        df_insights.to_excel(writer, sheet_name="Insights", index=False)


def _safe(text: str) -> str:
    """Replace non-latin1 chars for fpdf2 Helvetica."""
    return str(text).encode("latin-1", errors="replace").decode("latin-1")


def _trunc(text: str, max_len: int) -> str:
    text = _safe(str(text))
    return text[:max_len - 3] + "..." if len(text) > max_len else text
