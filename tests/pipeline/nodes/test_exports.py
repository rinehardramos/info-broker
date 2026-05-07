"""Unit tests for the export pipeline nodes (PDF, CSV, Excel)."""

from __future__ import annotations

import asyncio
import csv as csv_lib
import os

import pytest

from app.pipeline.nodes.base import RunContext
from app.pipeline.nodes.export_csv import ExportCsvNode
from app.pipeline.nodes.export_excel import ExportExcelNode
from app.pipeline.nodes.export_pdf import ExportPdfNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(run_id: str = "test-run-123") -> RunContext:
    return RunContext(user_id="u1", run_id=run_id, node_id="n1")


def _arun(coro):
    return asyncio.run(coro)


_MOCK_FINDINGS = [
    {
        "title": "Test Finding One",
        "source": "ddg_search",
        "url": "https://example.com/1",
        "confidence": 85,
        "content": "This is content for finding one with plenty of text to test truncation.",
    },
    {
        "title": "Test Finding Two",
        "source": "web_crawl",
        "url": "https://example.com/2",
        "confidence": 60,
        "content": "Content for finding two.",
    },
]

_MOCK_ANALYSIS = {
    "source": "analyzer",
    "entities": [
        {"name": "Acme Corp", "type": "organization"},
        {"name": "John Doe", "type": "person"},
    ],
    "relationships": [
        {"from": "John Doe", "to": "Acme Corp", "type": "works_at", "evidence": "Mentioned in article"},
    ],
    "insights": ["Acme Corp is expanding rapidly.", "Key person is John Doe."],
    "recommendations": ["Verify John Doe's role.", "Check SEC filings for Acme Corp."],
}


def _patch_pdf_output(tmp_path, run_id):
    """Context manager-style helper that redirects FPDF.output to tmp_path."""
    from fpdf import FPDF
    original = FPDF.output

    written: list[str] = []

    def fake_output(self_fpdf, name="", dest=""):
        actual = str(tmp_path / f"{run_id}.pdf")
        written.append(actual)
        return original(self_fpdf, actual)

    return FPDF, original, fake_output, written


# ---------------------------------------------------------------------------
# PDF tests
# ---------------------------------------------------------------------------

class TestExportPdfNode:
    def test_export_pdf_creates_file(self, tmp_path):
        """Pass mock findings; verify PDF file is created."""
        run_id = "pdf-test-run"
        node = ExportPdfNode()
        ctx = _ctx(run_id)

        import app.pipeline.nodes.export_pdf as pdf_mod
        from fpdf import FPDF

        original_makedirs = pdf_mod.os.makedirs
        original_output = FPDF.output
        written: list[str] = []

        pdf_mod.os.makedirs = lambda *a, **kw: None

        def fake_output(self_fpdf, name="", dest=""):
            actual = str(tmp_path / f"{run_id}.pdf")
            written.append(actual)
            return original_output(self_fpdf, actual)

        FPDF.output = fake_output  # type: ignore[method-assign]
        try:
            results = _arun(node.execute({}, _MOCK_FINDINGS, ctx))
        finally:
            pdf_mod.os.makedirs = original_makedirs
            FPDF.output = original_output  # type: ignore[method-assign]

        assert len(results) == 1
        assert results[0]["source"] == "export_pdf"
        assert results[0]["format"] == "pdf"
        assert f"{run_id}.pdf" in results[0]["url"]
        assert written, "FPDF.output was never called"
        assert os.path.exists(written[0])
        assert os.path.getsize(written[0]) > 0

    def test_export_pdf_with_analysis(self, tmp_path):
        """Pass findings + analysis; verify PDF is written and includes analysis content."""
        run_id = "pdf-analysis-test"
        node = ExportPdfNode()
        ctx = _ctx(run_id)

        import app.pipeline.nodes.export_pdf as pdf_mod
        from fpdf import FPDF

        original_makedirs = pdf_mod.os.makedirs
        original_output = FPDF.output
        written: list[str] = []

        pdf_mod.os.makedirs = lambda *a, **kw: None

        def fake_output(self_fpdf, name="", dest=""):
            actual = str(tmp_path / f"{run_id}.pdf")
            written.append(actual)
            return original_output(self_fpdf, actual)

        FPDF.output = fake_output  # type: ignore[method-assign]
        try:
            results = _arun(node.execute({}, _MOCK_FINDINGS + [_MOCK_ANALYSIS], ctx))
        finally:
            pdf_mod.os.makedirs = original_makedirs
            FPDF.output = original_output  # type: ignore[method-assign]

        assert results[0]["format"] == "pdf"
        assert written, "FPDF.output was never called"
        assert os.path.exists(written[0])
        assert os.path.getsize(written[0]) > 100


# ---------------------------------------------------------------------------
# CSV tests
# ---------------------------------------------------------------------------

class TestExportCsvNode:
    def test_export_csv_creates_file(self, tmp_path):
        """Pass mock findings; verify CSV file created with correct columns."""
        import pandas as pd
        import app.pipeline.nodes.export_csv as csv_mod

        run_id = "csv-test-run"
        node = ExportCsvNode()
        ctx = _ctx(run_id)

        original_makedirs = csv_mod.os.makedirs
        csv_mod.os.makedirs = lambda *a, **kw: None

        original_to_csv = pd.DataFrame.to_csv
        captured: list[str] = []

        def fake_to_csv(self_df, path_or_buf, **kwargs):
            actual = str(tmp_path / f"{run_id}.csv")
            captured.append(actual)
            return original_to_csv(self_df, actual, **kwargs)

        pd.DataFrame.to_csv = fake_to_csv  # type: ignore[method-assign]
        try:
            results = _arun(node.execute({}, _MOCK_FINDINGS, ctx))
        finally:
            csv_mod.os.makedirs = original_makedirs
            pd.DataFrame.to_csv = original_to_csv  # type: ignore[method-assign]

        assert results[0]["format"] == "csv"
        assert f"{run_id}.csv" in results[0]["url"]
        assert captured

        with open(captured[0]) as f:
            reader = csv_lib.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert set(rows[0].keys()) == {"title", "source", "url", "confidence", "content"}
        assert rows[0]["title"] == "Test Finding One"
        assert rows[0]["source"] == "ddg_search"

    def test_export_csv_handles_empty(self, tmp_path):
        """Empty inputs returns an empty CSV with headers only."""
        import pandas as pd
        import app.pipeline.nodes.export_csv as csv_mod

        run_id = "csv-empty-run"
        node = ExportCsvNode()
        ctx = _ctx(run_id)

        original_makedirs = csv_mod.os.makedirs
        csv_mod.os.makedirs = lambda *a, **kw: None

        original_to_csv = pd.DataFrame.to_csv
        captured: list[str] = []

        def fake_to_csv(self_df, path_or_buf, **kwargs):
            actual = str(tmp_path / f"{run_id}.csv")
            captured.append(actual)
            return original_to_csv(self_df, actual, **kwargs)

        pd.DataFrame.to_csv = fake_to_csv  # type: ignore[method-assign]
        try:
            results = _arun(node.execute({}, [], ctx))
        finally:
            csv_mod.os.makedirs = original_makedirs
            pd.DataFrame.to_csv = original_to_csv  # type: ignore[method-assign]

        assert results[0]["format"] == "csv"
        assert captured

        with open(captured[0]) as f:
            reader = csv_lib.DictReader(f)
            rows = list(reader)

        assert rows == []


# ---------------------------------------------------------------------------
# Excel tests
# ---------------------------------------------------------------------------

class TestExportExcelNode:
    def test_export_excel_creates_file(self, tmp_path):
        """Pass mock findings; verify XLSX file created with correct sheet names."""
        import pandas as pd
        import app.pipeline.nodes.export_excel as excel_mod

        run_id = "excel-test-run"
        node = ExportExcelNode()
        ctx = _ctx(run_id)

        original_makedirs = excel_mod.os.makedirs
        excel_mod.os.makedirs = lambda *a, **kw: None

        original_excel_writer = pd.ExcelWriter
        captured: list[str] = []

        class FakeExcelWriter:
            def __init__(self, path, **kwargs):
                actual = str(tmp_path / f"{run_id}.xlsx")
                captured.append(actual)
                self._writer = original_excel_writer(actual, **kwargs)

            def __enter__(self):
                self._writer.__enter__()
                return self._writer

            def __exit__(self, *args):
                return self._writer.__exit__(*args)

        pd.ExcelWriter = FakeExcelWriter  # type: ignore[assignment]
        try:
            results = _arun(node.execute({}, _MOCK_FINDINGS, ctx))
        finally:
            excel_mod.os.makedirs = original_makedirs
            pd.ExcelWriter = original_excel_writer  # type: ignore[assignment]

        assert results[0]["format"] == "xlsx"
        assert f"{run_id}.xlsx" in results[0]["url"]
        assert captured

        xl = pd.ExcelFile(captured[0])
        assert set(xl.sheet_names) == {"Findings", "Entities", "Relationships", "Insights"}

        df_findings = xl.parse("Findings")
        assert list(df_findings.columns) == ["title", "source", "url", "confidence", "content"]
        assert len(df_findings) == 2
