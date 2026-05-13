"""Sources REST API — upload, ingest, and query research source files."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.deps import require_api_key
from app.routers.v3.auth import get_current_user
from app.routers.v3.tenancy import require_analyst_user
from app.routers.v3.db import execute, fetch_all, fetch_one
from app.routers.v3.tenancy import user_org_id

router = APIRouter(prefix="/v3/sources", tags=["v3-sources"])
log = logging.getLogger(__name__)

_MAX_FILE_BYTES = int(os.getenv("SOURCE_MAX_FILE_BYTES", str(2 * 1024 * 1024 * 1024)))
_UPLOAD_CHUNK_BYTES = 1024 * 1024
_ACCEPTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".parquet", ".pdf", ".doc", ".docx", ".txt"}


# ---------------------------------------------------------------------------
# Background processing
# ---------------------------------------------------------------------------

async def _process_source(source_id: str, user_id: str, file_path: str, filename: str) -> None:
    from app.sources.parser import estimate_tokens, parse_file
    from app.sources.datastore import ingest_tabular_source, is_tabular_file, tabular_manifest_findings
    from app.memory.writer import index_research_findings
    from app.routers.v3.stream import push_event

    try:
        if is_tabular_file(filename):
            manifest = ingest_tabular_source(source_id, user_id, file_path, filename)
            findings = tabular_manifest_findings(filename, manifest)
        else:
            findings = parse_file(file_path, filename)
            # Build enhanced manifest with schema info extracted from findings
            manifest = {
                "storage": "memory_index",
                "findings_count": len(findings),
                "filename": filename,
            }
        total_text = " ".join(f.get("content", "") for f in findings)
        token_count = estimate_tokens(total_text)

        await index_research_findings(source_id, filename, findings)

        manifest["findings_count"] = len(findings)
        manifest["token_count"] = token_count
        manifest["filename"] = filename

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
    user: dict = Depends(require_analyst_user),
) -> dict:
    """Upload a file, persist metadata, and kick off async parsing."""
    # Validate extension
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ACCEPTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type {suffix!r}. Accepted: {', '.join(sorted(_ACCEPTED_EXTENSIONS))}",
        )

    user_id = str(user["id"])
    org = user_org_id(user)
    source_id = str(uuid.uuid4())
    filename = file.filename or f"upload{suffix}"
    file_type = suffix.lstrip(".")

    # Persist to /tmp/uploads/{user_id}/{source_id}/{filename}
    upload_dir = f"/tmp/uploads/{user_id}/{source_id}"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = f"{upload_dir}/{filename}"
    file_size_bytes = 0
    with open(file_path, "wb") as fh:
        while chunk := await file.read(_UPLOAD_CHUNK_BYTES):
            file_size_bytes += len(chunk)
            if file_size_bytes > _MAX_FILE_BYTES:
                try:
                    os.unlink(file_path)
                except OSError:
                    pass
                raise HTTPException(status_code=413, detail="File exceeds configured source upload limit")
            fh.write(chunk)

    # Insert research_sources row
    execute(
        """
        INSERT INTO research_sources (id, user_id, org_id, run_id, filename, file_type, file_size_bytes, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'processing')
        """,
        (source_id, user_id, org, run_id or None, filename, file_type, file_size_bytes),
    )

    # Launch background processing
    asyncio.create_task(_process_source(source_id, user_id, file_path, filename))

    return {
        "source_id": source_id,
        "filename": filename,
        "file_type": file_type,
        "file_size_bytes": file_size_bytes,
        "status": "processing",
    }


@router.get("")
def list_sources(user: dict = Depends(get_current_user)) -> list[dict]:
    """List all sources for the authenticated user."""
    rows = fetch_all(
        "SELECT * FROM research_sources WHERE user_id = %s AND org_id = %s ORDER BY created_at DESC",
        (str(user["id"]), user_org_id(user)),
    )
    return rows


@router.get("/{source_id}")
def get_source(source_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Fetch a single source by ID."""
    row = fetch_one(
        "SELECT * FROM research_sources WHERE id = %s AND user_id = %s AND org_id = %s",
        (source_id, str(user["id"]), user_org_id(user)),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    return row


@router.post("/query")
async def query_all_sources(body: dict, _key: str = Depends(require_api_key)) -> list[dict]:
    """Search uploaded sources.

    Body params:
        query: search text (required)
        filename: filter to findings from this file (substring match on title)
        source_id: filter to findings from this upload source (exact match on run_id)
        limit: max results (default 20, max 50)
    """
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchText
    from llm_providers import embed_text

    query = body.get("query", "")
    limit = min(body.get("limit", 20), 50)
    filename = body.get("filename", "")
    source_id = body.get("source_id", "")

    if not query:
        return []

    row_results = _query_data_plane_rows(
        query=query,
        filename=filename,
        source_id=source_id,
        limit=limit,
    )
    if row_results:
        return row_results

    client = QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )

    vector = embed_text(query)

    # Filter to file_upload source only
    must_conditions = [FieldCondition(key="source_tool", match=MatchValue(value="file_upload"))]
    # Scope to a specific file by source_id (= run_id in Qdrant payload)
    if source_id:
        must_conditions.append(FieldCondition(key="run_id", match=MatchValue(value=source_id)))
    # Or scope by filename substring in title
    elif filename:
        must_conditions.append(FieldCondition(key="title", match=MatchText(text=filename)))

    hits = client.query_points(
        collection_name="research_memory",
        query=vector,
        query_filter=Filter(must=must_conditions),
        limit=limit,
        with_payload=True,
    ).points

    return [
        {
            "title": (h.payload or {}).get("title", ""),
            "content": (h.payload or {}).get("content", "")[:2000],
            "score": round(h.score, 4),
            "source_tool": (h.payload or {}).get("source_tool", ""),
            "run_id": (h.payload or {}).get("run_id", ""),
        }
        for h in hits
    ]


def _query_data_plane_rows(
    query: str,
    filename: str = "",
    source_id: str = "",
    limit: int = 20,
) -> list[dict]:
    """Query normalized tabular artifacts from the data plane."""
    from app.sources.datastore import query_tabular_source

    if not source_id and not filename:
        return []

    source = _find_data_plane_source(filename=filename, source_id=source_id)
    if not source:
        return []
    return query_tabular_source(source, query, limit=limit)


def _find_data_plane_source(filename: str = "", source_id: str = "") -> dict | None:
    if source_id:
        return fetch_one(
            "SELECT * FROM research_sources WHERE id = %s AND manifest->>'storage' = %s",
            (source_id, "data_plane"),
        )
    if filename:
        return fetch_one(
            """
            SELECT * FROM research_sources
             WHERE filename ILIKE %s AND manifest->>'storage' = %s
             ORDER BY created_at DESC
             LIMIT 1
            """,
            (f"%{filename}%", "data_plane"),
        )
    return None


@router.post("/{source_id}/query")
async def query_source_data(
    source_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
) -> list[dict]:
    """Search within an uploaded file's indexed content."""
    row = fetch_one(
        "SELECT id FROM research_sources WHERE id = %s AND user_id = %s AND org_id = %s",
        (source_id, str(user["id"]), user_org_id(user)),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")

    from app.memory.retriever import fused_retrieve

    query = body.get("query", "")
    limit = int(body.get("limit", 20))

    source = fetch_one(
        "SELECT * FROM research_sources WHERE id = %s AND user_id = %s AND org_id = %s",
        (source_id, str(user["id"]), user_org_id(user)),
    )
    if source and (source.get("manifest") or {}).get("storage") == "data_plane":
        from app.sources.datastore import query_tabular_source
        return query_tabular_source(source, query, limit=limit)

    results = await fused_retrieve(query, limit=limit * 3)
    filtered = [r for r in results if r.run_id == source_id]

    return [
        {
            "title": r.title,
            "content": r.content[:2000],
            "score": r.score,
            "source_tool": r.source_tool,
        }
        for r in filtered[:limit]
    ]


@router.delete("/{source_id}")
def delete_source(source_id: str, user: dict = Depends(require_analyst_user)) -> dict:
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
