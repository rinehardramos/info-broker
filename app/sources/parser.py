"""File parser module for TXT, CSV, Excel, PDF, and DOCX uploads.

Converts raw file content into structured findings compatible with the
research_sources schema (source="file_upload").
"""

from __future__ import annotations

import os

import pandas as pd


def _df_to_markdown(df: pd.DataFrame) -> str:
    """Render a DataFrame as a Markdown table without the tabulate dependency."""
    if df.empty:
        if df.columns.empty:
            return ""
        header = " | ".join(str(c) for c in df.columns)
        separator = " | ".join("---" for _ in df.columns)
        return f"| {header} |\n| {separator} |"

    cols = [str(c) for c in df.columns]
    rows = [[str(v) for v in row] for row in df.itertuples(index=False)]

    # Column widths
    widths = [len(c) for c in cols]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: list[str]) -> str:
        padded = [cell.ljust(widths[i]) for i, cell in enumerate(cells)]
        return "| " + " | ".join(padded) + " |"

    separator = "| " + " | ".join("-" * w for w in widths) + " |"
    lines = [fmt_row(cols), separator] + [fmt_row(r) for r in rows]
    return "\n".join(lines)

_CHUNK_MAX_CHARS = 2000  # ~500 tokens at 4 chars/token


def estimate_tokens(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 characters."""
    return len(text) // 4


def parse_txt(content: str, filename: str) -> list[dict]:
    """Parse plain-text content into chunked findings.

    Splits on double newlines (paragraphs), groups into ~500-token chunks,
    and returns one finding per chunk.

    Args:
        content: Full text content of the file.
        filename: Original filename (used in titles and content prefixes).

    Returns:
        List of finding dicts, or [] if content is empty/whitespace.
    """
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if current_parts and current_len + para_len + 2 > _CHUNK_MAX_CHARS:
            chunks.append("\n\n".join(current_parts))
            current_parts = [para]
            current_len = para_len
        else:
            current_parts.append(para)
            current_len += para_len + (2 if len(current_parts) > 1 else 0)

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    findings: list[dict] = []
    for n, chunk_text in enumerate(chunks, start=1):
        findings.append(
            {
                "title": f"{filename} - chunk {n}",
                "content": f"[File: {filename} | Chunk {n}]\n{chunk_text}",
                "source": "file_upload",
                "confidence": 85,
            }
        )

    return findings


def parse_csv(file_path: str, filename: str) -> list[dict]:
    """Parse a CSV file into structured findings.

    Produces:
      - Finding 0: schema summary (columns, types, row count, first 5 rows as
        Markdown table). confidence=95.
      - Findings 1-N: groups of 20 rows as Markdown tables. confidence=85.

    Args:
        file_path: Absolute path to the CSV file on disk.
        filename: Original filename (used in titles and content prefixes).

    Returns:
        List of finding dicts (always at least the schema finding).
    """
    df = pd.read_csv(file_path)
    row_count = len(df)

    # --- Schema summary ---
    col_lines = [f"- **{col}**: {dtype}" for col, dtype in df.dtypes.items()]
    schema_body = "\n".join(col_lines)

    preview = _df_to_markdown(df.head(5))

    schema_content = (
        f"[File: {filename} | Schema]\n"
        f"**Columns ({len(df.columns)}):**\n{schema_body}\n\n"
        f"**Row count:** {row_count}\n\n"
        f"**Preview (first 5 rows):**\n{preview}"
    )

    findings: list[dict] = [
        {
            "title": f"{filename} - Schema",
            "content": schema_content,
            "source": "file_upload",
            "confidence": 95,
        }
    ]

    # --- Row group findings ---
    chunk_size = 20
    for start_idx in range(0, row_count, chunk_size):
        end_idx = min(start_idx + chunk_size, row_count)
        chunk_df = df.iloc[start_idx:end_idx]
        start_label = start_idx + 1
        end_label = end_idx
        context = f"rows {start_label}-{end_label}"
        table = _df_to_markdown(chunk_df)
        findings.append(
            {
                "title": f"{filename} - {context}",
                "content": f"[File: {filename} | {context}]\n{table}",
                "source": "file_upload",
                "confidence": 85,
            }
        )

    return findings


def parse_excel(file_path: str, filename: str) -> list[dict]:
    """Parse an Excel file (.xlsx/.xls) into structured findings.

    For each sheet produces the same output as parse_csv:
      - A schema summary finding (confidence=95)
      - Row-group findings in batches of 20 (confidence=85)

    Sheet name is embedded in every title:
      Schema finding: "{filename} - {sheet_name} Schema"
      Row findings:   "{filename} - {sheet_name} rows {start}-{end}"

    Args:
        file_path: Absolute path to the Excel file on disk.
        filename: Original filename (used in titles and content prefixes).

    Returns:
        List of finding dicts across all sheets.
    """
    sheets: dict[str, pd.DataFrame] = pd.read_excel(file_path, sheet_name=None)
    findings: list[dict] = []

    for sheet_name, df in sheets.items():
        row_count = len(df)

        # --- Schema summary ---
        col_lines = [f"- **{col}**: {dtype}" for col, dtype in df.dtypes.items()]
        schema_body = "\n".join(col_lines)
        preview = _df_to_markdown(df.head(5))

        schema_content = (
            f"[File: {filename} | {sheet_name} Schema]\n"
            f"**Columns ({len(df.columns)}):**\n{schema_body}\n\n"
            f"**Row count:** {row_count}\n\n"
            f"**Preview (first 5 rows):**\n{preview}"
        )
        findings.append(
            {
                "title": f"{filename} - {sheet_name} Schema",
                "content": schema_content,
                "source": "file_upload",
                "confidence": 95,
            }
        )

        # --- Row group findings ---
        chunk_size = 20
        for start_idx in range(0, row_count, chunk_size):
            end_idx = min(start_idx + chunk_size, row_count)
            chunk_df = df.iloc[start_idx:end_idx]
            start_label = start_idx + 1
            end_label = end_idx
            context = f"rows {start_label}-{end_label}"
            table = _df_to_markdown(chunk_df)
            findings.append(
                {
                    "title": f"{filename} - {sheet_name} {context}",
                    "content": f"[File: {filename} | {sheet_name} {context}]\n{table}",
                    "source": "file_upload",
                    "confidence": 85,
                }
            )

    return findings


def parse_pdf(file_path: str, filename: str) -> list[dict]:
    """Parse a PDF file into per-page findings.

    Each non-empty page becomes one finding. If the page contains tables,
    they are appended as Markdown after the page text.

    Title format:   "{filename} - Page {N}"
    Content prefix: "[File: {filename} | Page {N}]"

    Args:
        file_path: Absolute path to the PDF file on disk.
        filename: Original filename (used in titles and content prefixes).

    Returns:
        List of finding dicts; empty pages are skipped.
    """
    import pdfplumber

    findings: list[dict] = []

    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""

            # Append any tables as Markdown
            tables = page.extract_tables()
            table_md_parts: list[str] = []
            for table in tables:
                if not table:
                    continue
                # table is a list of rows (list of lists)
                headers = [str(cell) if cell is not None else "" for cell in table[0]]
                rows = [
                    [str(cell) if cell is not None else "" for cell in row]
                    for row in table[1:]
                ]
                df = pd.DataFrame(rows, columns=headers)
                table_md_parts.append(_df_to_markdown(df))

            full_text = page_text
            if table_md_parts:
                full_text = full_text + "\n\n" + "\n\n".join(table_md_parts)

            if not full_text.strip():
                continue

            findings.append(
                {
                    "title": f"{filename} - Page {page_num}",
                    "content": f"[File: {filename} | Page {page_num}]\n{full_text}",
                    "source": "file_upload",
                    "confidence": 85,
                }
            )

    return findings


def parse_docx(file_path: str, filename: str) -> list[dict]:
    """Parse a DOCX file into section-based findings.

    Paragraphs are grouped by Heading 1 (or any heading style). When a
    heading is encountered, the accumulated paragraphs from the previous
    section are flushed as a finding.  Sections with no body text are
    skipped.  If the document has no headings at all, all content is
    treated as a single section titled "{filename} - Section 1".

    Title format:   heading text  (or "{filename} - Section {N}" if headless)
    Content prefix: "[File: {filename} | Section: {heading}]"

    Args:
        file_path: Absolute path to the DOCX file on disk.
        filename: Original filename (used in titles and content prefixes).

    Returns:
        List of finding dicts; empty sections are skipped.
    """
    import docx

    document = docx.Document(file_path)
    findings: list[dict] = []

    current_heading: str | None = None
    current_paragraphs: list[str] = []
    section_counter = 0

    def _flush(heading: str | None, paragraphs: list[str]) -> None:
        nonlocal section_counter
        body = "\n".join(p for p in paragraphs if p.strip())
        if not body.strip():
            return
        if heading:
            title = heading
        else:
            section_counter += 1
            title = f"{filename} - Section {section_counter}"
        findings.append(
            {
                "title": title,
                "content": f"[File: {filename} | Section: {title}]\n{body}",
                "source": "file_upload",
                "confidence": 85,
            }
        )

    for para in document.paragraphs:
        is_heading = para.style.name.startswith("Heading")
        if is_heading:
            _flush(current_heading, current_paragraphs)
            current_heading = para.text.strip()
            current_paragraphs = []
        else:
            if para.text.strip():
                current_paragraphs.append(para.text.strip())

    # Flush remaining content
    _flush(current_heading, current_paragraphs)

    return findings


def parse_file(file_path: str, filename: str) -> list[dict]:
    """Dispatch to the appropriate parser based on file extension.

    Supported extensions: .csv, .xlsx, .xls, .pdf, .docx, .doc, .txt

    Args:
        file_path: Absolute path to the file on disk.
        filename: Original filename (used to determine extension and in output).

    Returns:
        List of finding dicts from the appropriate parser.

    Raises:
        ValueError: If the file extension is not supported.
    """
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".csv":
        return parse_csv(file_path, filename)
    elif ext in {".xlsx", ".xls"}:
        return parse_excel(file_path, filename)
    elif ext == ".pdf":
        return parse_pdf(file_path, filename)
    elif ext in {".docx", ".doc"}:
        return parse_docx(file_path, filename)
    elif ext == ".txt":
        with open(file_path, encoding="utf-8") as fh:
            content = fh.read()
        return parse_txt(content, filename)
    else:
        raise ValueError(f"Unsupported file extension: {ext!r}")
