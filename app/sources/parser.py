"""File parser module for TXT and CSV uploads.

Converts raw file content into structured findings compatible with the
research_sources schema (source="file_upload").
"""

from __future__ import annotations

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
