"""Tests for app/sources/parser.py — TDD suite written before implementation."""

import csv
import os
import tempfile

import pytest

from app.sources.parser import estimate_tokens, parse_csv, parse_txt


# ---------------------------------------------------------------------------
# estimate_tokens
# ---------------------------------------------------------------------------


def test_estimate_tokens_basic():
    # "hello world" has len 11 → 11 // 4 = 2
    result = estimate_tokens("hello world")
    assert result == 2


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0


def test_estimate_tokens_longer():
    text = "a" * 100
    assert estimate_tokens(text) == 25


# ---------------------------------------------------------------------------
# parse_txt
# ---------------------------------------------------------------------------


def test_parse_txt_empty_returns_empty_list():
    assert parse_txt("", "test.txt") == []


def test_parse_txt_whitespace_only_returns_empty_list():
    assert parse_txt("   \n\n   ", "test.txt") == []


def test_parse_txt_three_short_paragraphs_titles():
    content = "Para one.\n\nPara two.\n\nPara three."
    findings = parse_txt(content, "report.txt")
    assert len(findings) >= 1
    for finding in findings:
        assert finding["title"].startswith("report.txt - chunk ")


def test_parse_txt_content_has_contextual_prefix():
    content = "Hello world paragraph."
    findings = parse_txt(content, "notes.txt")
    assert len(findings) == 1
    assert findings[0]["content"].startswith("[File: notes.txt |")


def test_parse_txt_finding_fields():
    content = "Some content here."
    findings = parse_txt(content, "data.txt")
    assert len(findings) == 1
    f = findings[0]
    assert f["source"] == "file_upload"
    assert f["confidence"] == 85
    assert "title" in f
    assert "content" in f


def test_parse_txt_chunk_numbering():
    # Build content that will definitely exceed 2000 chars to force multiple chunks.
    paragraph = "word " * 120  # ~600 chars each
    content = "\n\n".join([paragraph] * 5)
    findings = parse_txt(content, "big.txt")
    assert len(findings) >= 2
    titles = [f["title"] for f in findings]
    assert "big.txt - chunk 1" in titles
    assert "big.txt - chunk 2" in titles


def test_parse_txt_chunk_content_includes_chunk_tag():
    paragraph = "word " * 120
    content = "\n\n".join([paragraph] * 5)
    findings = parse_txt(content, "big.txt")
    for i, f in enumerate(findings, start=1):
        assert f"[File: big.txt | Chunk {i}]" in f["content"]


def test_parse_txt_all_findings_have_file_upload_source():
    paragraph = "word " * 120
    content = "\n\n".join([paragraph] * 5)
    findings = parse_txt(content, "big.txt")
    assert all(f["source"] == "file_upload" for f in findings)


# ---------------------------------------------------------------------------
# parse_csv
# ---------------------------------------------------------------------------


def _write_csv(rows: list[dict], fieldnames: list[str] | None = None) -> str:
    """Write rows to a temp CSV file and return the path."""
    fh = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    )
    if fieldnames is None and rows:
        fieldnames = list(rows[0].keys())
    writer = csv.DictWriter(fh, fieldnames=fieldnames or [])
    writer.writeheader()
    writer.writerows(rows)
    fh.close()
    return fh.name


def test_parse_csv_schema_is_first_finding_with_confidence_95():
    path = _write_csv(
        [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
    )
    try:
        findings = parse_csv(path, "people.csv")
        assert findings[0]["confidence"] == 95
        assert findings[0]["title"] == "people.csv - Schema"
    finally:
        os.unlink(path)


def test_parse_csv_schema_contains_column_names():
    path = _write_csv([{"city": "NY", "pop": 8000000}])
    try:
        findings = parse_csv(path, "cities.csv")
        schema_content = findings[0]["content"]
        assert "city" in schema_content
        assert "pop" in schema_content
    finally:
        os.unlink(path)


def test_parse_csv_schema_contains_row_count():
    rows = [{"x": i} for i in range(7)]
    path = _write_csv(rows)
    try:
        findings = parse_csv(path, "numbers.csv")
        assert "7" in findings[0]["content"]
    finally:
        os.unlink(path)


def test_parse_csv_schema_content_has_contextual_prefix():
    path = _write_csv([{"a": 1}])
    try:
        findings = parse_csv(path, "sample.csv")
        assert findings[0]["content"].startswith("[File: sample.csv |")
    finally:
        os.unlink(path)


def test_parse_csv_five_rows_returns_schema_plus_one_row_finding():
    rows = [{"n": i} for i in range(5)]
    path = _write_csv(rows)
    try:
        findings = parse_csv(path, "five.csv")
        # schema + 1 row group (rows 1-5)
        assert len(findings) == 2
    finally:
        os.unlink(path)


def test_parse_csv_21_rows_returns_schema_plus_two_row_findings():
    rows = [{"n": i} for i in range(21)]
    path = _write_csv(rows)
    try:
        findings = parse_csv(path, "big.csv")
        # schema + group(1-20) + group(21-21)
        assert len(findings) == 3
    finally:
        os.unlink(path)


def test_parse_csv_row_findings_have_correct_titles():
    rows = [{"n": i} for i in range(25)]
    path = _write_csv(rows)
    try:
        findings = parse_csv(path, "data.csv")
        titles = [f["title"] for f in findings]
        assert "data.csv - rows 1-20" in titles
        assert "data.csv - rows 21-25" in titles
    finally:
        os.unlink(path)


def test_parse_csv_row_findings_confidence_is_85():
    rows = [{"n": i} for i in range(3)]
    path = _write_csv(rows)
    try:
        findings = parse_csv(path, "small.csv")
        row_findings = findings[1:]  # skip schema
        assert all(f["confidence"] == 85 for f in row_findings)
    finally:
        os.unlink(path)


def test_parse_csv_all_findings_have_file_upload_source():
    rows = [{"a": i, "b": i * 2} for i in range(5)]
    path = _write_csv(rows)
    try:
        findings = parse_csv(path, "ab.csv")
        assert all(f["source"] == "file_upload" for f in findings)
    finally:
        os.unlink(path)


def test_parse_csv_empty_file_returns_only_schema():
    path = _write_csv([], fieldnames=["col1", "col2"])
    try:
        findings = parse_csv(path, "empty.csv")
        assert len(findings) == 1
        assert findings[0]["title"] == "empty.csv - Schema"
        assert "0" in findings[0]["content"]
    finally:
        os.unlink(path)


def test_parse_csv_row_finding_content_has_contextual_prefix():
    rows = [{"x": i} for i in range(3)]
    path = _write_csv(rows)
    try:
        findings = parse_csv(path, "xy.csv")
        row_findings = findings[1:]
        for f in row_findings:
            assert f["content"].startswith("[File: xy.csv |")
    finally:
        os.unlink(path)
