"""Local Files datastore node — search local text/document files by content."""

from __future__ import annotations

import asyncio
import glob as globmod
import logging
import os
from pathlib import Path

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_MAX_FILE_SIZE = 512_000  # 512 KB per file
_MAX_SNIPPET = 500        # chars of context around match


class LocalFilesNode:
    node_type = "local_files"
    display_name = "Local Files"
    category = "datastore"
    config_schema = {
        "type": "object",
        "properties": {
            "base_path": {
                "type": "string",
                "title": "Base Directory",
                "description": "Absolute path to the directory to search",
            },
            "glob_pattern": {
                "type": "string",
                "title": "File Pattern",
                "default": "**/*.{md,txt}",
                "description": "Glob pattern for matching files",
            },
            "max_files": {
                "type": "integer",
                "title": "Max Files",
                "default": 50,
                "minimum": 1,
                "maximum": 200,
            },
        },
        "required": ["base_path"],
    }

    # -- PipelineNode interface ------------------------------------------------

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        return []

    # -- ToolCallable interface ------------------------------------------------

    def tool_schema(self) -> dict:
        return {
            "name": "search_files",
            "description": (
                "Search local text and document files by keyword. "
                "Returns matching file excerpts with surrounding context."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search keywords to look for in file contents",
                    },
                    "path_filter": {
                        "type": "string",
                        "description": "Optional sub-path or filename filter (e.g., 'notes/' or '*.md')",
                    },
                },
                "required": ["query"],
            },
        }

    async def tool_invoke(
        self, params: dict, context: RunContext
    ) -> list[dict]:
        query = params.get("query", "")
        if not query:
            return []

        config = getattr(self, "_active_config", {})
        base_path = config.get("base_path", "")
        pattern = config.get("glob_pattern", "**/*.{md,txt}")
        max_files = int(config.get("max_files", 50))
        path_filter = params.get("path_filter", "")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, _search_files, base_path, pattern, query, max_files, path_filter
        )


def _search_files(
    base_path: str,
    pattern: str,
    query: str,
    max_files: int,
    path_filter: str,
) -> list[dict]:
    """Synchronous file content search."""
    if not base_path or not os.path.isdir(base_path):
        return [{"error": f"Directory not found: {base_path}", "source": "local_files"}]

    # Expand brace patterns (glob doesn't support {md,txt} natively)
    patterns = _expand_braces(pattern)
    matched_paths: list[str] = []
    for pat in patterns:
        search_path = os.path.join(base_path, pat)
        matched_paths.extend(globmod.glob(search_path, recursive=True))

    # Apply optional path filter
    if path_filter:
        matched_paths = [p for p in matched_paths if path_filter in p]

    # Deduplicate and limit
    matched_paths = sorted(set(matched_paths))[:max_files * 3]

    results: list[dict] = []
    query_lower = query.lower()

    for fpath in matched_paths:
        if len(results) >= max_files:
            break
        try:
            size = os.path.getsize(fpath)
            if size > _MAX_FILE_SIZE or size == 0:
                continue
            with open(fpath, "r", errors="replace") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            continue

        idx = content.lower().find(query_lower)
        if idx == -1:
            continue

        # Extract snippet around match
        start = max(0, idx - _MAX_SNIPPET // 2)
        end = min(len(content), idx + len(query) + _MAX_SNIPPET // 2)
        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

        rel_path = os.path.relpath(fpath, base_path)
        results.append({
            "title": rel_path,
            "content": snippet,
            "file_path": fpath,
            "source": "local_files",
        })

    return results


def _expand_braces(pattern: str) -> list[str]:
    """Expand simple brace patterns like '**/*.{md,txt}' into multiple globs."""
    import re
    m = re.search(r"\{([^}]+)\}", pattern)
    if not m:
        return [pattern]
    alts = m.group(1).split(",")
    return [pattern[: m.start()] + alt.strip() + pattern[m.end() :] for alt in alts]
