"""Sources REST API — file upload, listing, and async parsing into research_memory."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one

router = APIRouter(prefix="/v3/sources", tags=["v3-sources"])
log = logging.getLogger(__name__)

_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB
_ACCEPTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".pdf", ".doc", ".docx", ".txt"}


# ---------------------------------------------------------------------------
# Background processing
# ---------------------------------------------------------------------------

async def _process_source(source_id: str, user_id: str, file_path: str, filename: str) -> None:
    from app.sources.parser import estimate_tokens, parse_file
    from app.memory.writer import index_research_findings
    from app.routers.v3.stream import push_event

    try:
        findings = parse_file(file_path, filename)
        total_text = " ".join(f.get("content", "") for f in findings)
        token_count = estimate_tokens(total_text)

        await index_research_findings(source_id, filename, findings)

        manifest = {
            "findings_count": len(findings),
            "token_count": token_count,
            "filename": filename,
        }

        execute(
            "UPDATE research_sources SET status='indexed', findings_count=%s, token_count=%s, manifest=%s WHERE id=%s",
            (len(findings), token_count, json.dumps(manifest), source_id),
        )

        await push_event(
            user_id,
            {
                "type": "source.indexed",
                "source_id": source_id,
                "filename": filename,
                "findings_count": len(findings),
            },
        )

    except Exception as exc:
        log.error("_process_source failed source_id=%s: %s", source_id, exc)
        execute("UPDATE research_sources SET status='failed' WHERE id=%s", (source_id,))
        try:
            from app.routers.v3.stream import push_event
            await push_event(
                user_id,
                {
                    "type": "source.failed",
                    "source_id": source_id,
                    "filename": filename,
                    "error": str(exc)[:200],
                },
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_source(
    file: UploadFile = File(...),
    run_id: str = Form(None),
    user: dict = Depends(get_current_user),
) -> dict:
    """Upload a file, persist metadata, and kick off async parsing."""
    # Validate extension
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ACCEPTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type {suffix!r}. Accepted: {', '.join(sorted(_ACCEPTED_EXTENSIONS))}",
        )

    # Read content and validate size
    content = await file.read()
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit")

    user_id = str(user["id"])
    source_id = str(uuid.uuid4())
    filename = file.filename or f"upload{suffix}"
    file_type = suffix.lstrip(".")

    # Persist to /tmp/uploads/{user_id}/{source_id}/{filename}
    upload_dir = f"/tmp/uploads/{user_id}/{source_id}"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = f"{upload_dir}/{filename}"
    with open(file_path, "wb") as fh:
        fh.write(content)

    # Insert research_sources row
    execute(
        """
        INSERT INTO research_sources (id, user_id, run_id, filename, file_type, file_size_bytes, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'processing')
        """,
        (source_id, user_id, run_id or None, filename, file_type, len(content)),
    )

    # Launch background processing
    asyncio.create_task(_process_source(source_id, user_id, file_path, filename))

    return {
        "source_id": source_id,
        "filename": filename,
        "file_type": file_type,
        "file_size_bytes": len(content),
        "status": "processing",
    }


@router.get("/")
def list_sources(user: dict = Depends(get_current_user)) -> list[dict]:
    """List all sources for the authenticated user."""
    rows = fetch_all(
        "SELECT * FROM research_sources WHERE user_id = %s ORDER BY created_at DESC",
        (str(user["id"]),),
    )
    return rows


@router.get("/{source_id}")
def get_source(source_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Fetch a single source by ID."""
    row = fetch_one(
        "SELECT * FROM research_sources WHERE id = %s AND user_id = %s",
        (source_id, str(user["id"])),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    return row


@router.delete("/{source_id}")
def delete_source(source_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Delete a source metadata row."""
    row = fetch_one(
        "SELECT id FROM research_sources WHERE id = %s AND user_id = %s",
        (source_id, str(user["id"])),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    execute(
        "DELETE FROM research_sources WHERE id = %s AND user_id = %s",
        (source_id, str(user["id"])),
    )
    return {"deleted": source_id}
