"""LLM-assisted KG curation — Memory Phase 5.

Three main operations:
- resolve_contradictions_batch: batch-resolve 'needs_review' contradictions via LLM.
- find_duplicate_entities: detect candidate duplicate entity refs via substring matching.
- generate_curation_suggestions: produce actionable suggestions from stale/low-conf/contradiction data.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil

from app.routers.v3.db import execute, fetch_all, fetch_one

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM helper (Claude Code CLI primary, Anthropic API fallback)
# ---------------------------------------------------------------------------


async def _call_llm(prompt: str) -> str:
    """Call Claude via Claude Code CLI (subscription).  Falls back to API."""
    from app.llm_models import general_model

    model = general_model()

    # Primary: Claude Code CLI
    claude_bin = shutil.which("claude") or "/usr/local/bin/claude"
    if os.path.isfile(claude_bin):
        try:
            spawn_env = {**os.environ, "CLAUDE_CODE_HEADLESS": "1"}
            fresh_key = ""
            try:
                _row = fetch_one(
                    "SELECT value FROM core_settings WHERE key = 'anthropic_api_key'", ()
                )
                if _row and _row["value"] and _row["value"].startswith("sk-ant-api"):
                    fresh_key = _row["value"]
            except Exception:
                pass
            if not fresh_key:
                env_key = os.getenv("ANTHROPIC_API_KEY", "")
                if env_key.startswith("sk-ant-api"):
                    fresh_key = env_key
            if fresh_key:
                spawn_env["ANTHROPIC_API_KEY"] = fresh_key
            else:
                spawn_env.pop("ANTHROPIC_API_KEY", None)

            cmd_args = [
                claude_bin,
                "--output-format", "text",
                "--model", model,
                "--max-turns", "1",
            ]
            if fresh_key:
                cmd_args.append("--bare")

            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                env=spawn_env,
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(input=prompt.encode()), timeout=120
            )
            if proc.returncode == 0 and stdout:
                return stdout.decode().strip()
            log.warning("llm_curator: Claude Code exit %s, falling back to API", proc.returncode)
        except asyncio.TimeoutError:
            log.warning("llm_curator: Claude Code timed out, falling back to API")
        except Exception as exc:
            log.warning("llm_curator: Claude Code failed (%s), falling back to API", exc)

    # Fallback: Anthropic SDK
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        try:
            row = fetch_one(
                "SELECT value FROM core_settings WHERE key = 'anthropic_api_key'", ()
            )
            if row:
                api_key = row["value"]
        except Exception:
            pass

    if not api_key:
        log.warning("llm_curator: no Claude Code and no API key")
        return "[]"

    loop = asyncio.get_running_loop()
    client = anthropic.Anthropic(api_key=api_key, max_retries=0)
    try:
        response = await loop.run_in_executor(
            None,
            lambda: client.messages.create(
                model=model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            ),
        )
        return response.content[0].text
    except Exception as exc:
        log.error("llm_curator: API call failed: %s", exc)
        return "[]"


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


async def resolve_contradictions_batch(limit: int = 10) -> dict:
    """Fetch up to *limit* needs_review contradictions and resolve via LLM.

    Returns {"resolved": N, "failed": N}.
    """
    rows = fetch_all(
        """
        SELECT id, entity_ref, attribute, value_a, value_b,
               confidence_a, confidence_b
        FROM kg_contradictions
        WHERE status = 'needs_review'
        ORDER BY created_at ASC
        LIMIT %s
        """,
        (limit,),
    )

    if not rows:
        return {"resolved": 0, "failed": 0}

    # Build a single batched prompt
    items_text = "\n".join(
        f"{i + 1}. entity={r['entity_ref']}, attribute={r['attribute']}, "
        f"value_a={r['value_a']} (conf {r['confidence_a']}), "
        f"value_b={r['value_b']} (conf {r['confidence_b']})"
        for i, r in enumerate(rows)
    )

    prompt = (
        "You are a knowledge graph curator. For each contradiction below, "
        "decide which value is more likely correct. "
        "Respond ONLY with a JSON array, one object per item, in the same order. "
        'Each object: {"index": <1-based>, "winner": "<value_a or value_b text>", '
        '"reason": "<one sentence>"}\n\n'
        f"Contradictions:\n{items_text}\n\n"
        "JSON array:"
    )

    raw = await _call_llm(prompt)

    # Parse response
    resolved = 0
    failed = 0
    try:
        # Strip markdown fences if present
        clean = raw.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.splitlines()[1:])
            if clean.endswith("```"):
                clean = clean[: clean.rfind("```")]
        decisions = json.loads(clean)
        if not isinstance(decisions, list):
            raise ValueError("Expected JSON array")
    except Exception as exc:
        log.error("llm_curator: failed to parse LLM response: %s — raw: %.200s", exc, raw)
        return {"resolved": 0, "failed": len(rows)}

    for decision in decisions:
        idx = decision.get("index")
        winner = decision.get("winner")
        if idx is None or not winner:
            failed += 1
            continue
        try:
            row = rows[int(idx) - 1]
        except (IndexError, TypeError, ValueError):
            failed += 1
            continue
        try:
            execute(
                """
                UPDATE kg_contradictions
                   SET status = 'llm_resolved',
                       winner = %s,
                       resolved_by = 'llm',
                       resolved_at = now()
                 WHERE id = %s
                """,
                (str(winner), str(row["id"])),
            )
            resolved += 1
        except Exception as exc:
            log.error("llm_curator: DB update failed for id %s: %s", row["id"], exc)
            failed += 1

    return {"resolved": resolved, "failed": failed}


def find_duplicate_entities(limit: int = 20) -> list[dict]:
    """Detect candidate duplicate entity refs via substring/ILIKE matching.

    Returns a list of candidate pairs: [{"ref_a": ..., "ref_b": ..., "shared_attribute": ..., "shared_value": ...}]
    """
    # Find entity refs that share the same attribute value (case-insensitive)
    # but have different refs — these are candidate duplicates.
    rows = fetch_all(
        """
        SELECT a.entity_ref AS ref_a,
               b.entity_ref AS ref_b,
               a.attribute  AS shared_attribute,
               a.value      AS shared_value
        FROM entity_observations a
        JOIN entity_observations b
          ON a.attribute = b.attribute
         AND a.entity_ref < b.entity_ref
         AND lower(a.value) = lower(b.value)
         AND length(a.value) > 3
        GROUP BY a.entity_ref, b.entity_ref, a.attribute, a.value
        ORDER BY a.entity_ref, b.entity_ref
        LIMIT %s
        """,
        (limit,),
    )
    return [dict(r) for r in rows]


async def generate_curation_suggestions(limit: int = 20) -> dict:
    """Generate curation suggestions from stale flags, low-confidence observations,
    and contradiction patterns.  Inserts into kg_curation_suggestions.

    Returns {"suggestions_created": N}.
    """
    suggestions: list[dict] = []

    # 1. Stale entities — collect up to limit/3 stale flags
    stale_rows = fetch_all(
        """
        SELECT entity_ref, attribute, current_value
        FROM kg_stale_flags
        WHERE status = 'stale'
        ORDER BY flagged_at ASC
        LIMIT %s
        """,
        (limit // 3 + 1,),
    )
    for row in stale_rows:
        suggestions.append(
            {
                "entity_ref": row["entity_ref"],
                "suggestion_type": "re_research",
                "suggestion": (
                    f"Re-research '{row['entity_ref']}': "
                    f"attribute '{row['attribute']}' (value: {row['current_value']}) is stale."
                ),
                "priority": "medium",
            }
        )

    # 2. Low-confidence observations — entities with mean confidence < 40
    low_conf_rows = fetch_all(
        """
        SELECT entity_ref, AVG(confidence) AS avg_conf, COUNT(*) AS n
        FROM entity_observations
        GROUP BY entity_ref
        HAVING AVG(confidence) < 40
        ORDER BY avg_conf ASC
        LIMIT %s
        """,
        (limit // 3 + 1,),
    )
    for row in low_conf_rows:
        suggestions.append(
            {
                "entity_ref": row["entity_ref"],
                "suggestion_type": "verify_confidence",
                "suggestion": (
                    f"Verify data for '{row['entity_ref']}': "
                    f"average confidence is {row['avg_conf']:.0f} across {row['n']} observations."
                ),
                "priority": "high",
            }
        )

    # 3. Contradiction hot-spots — entities with multiple needs_review contradictions
    contradiction_rows = fetch_all(
        """
        SELECT entity_ref, COUNT(*) AS n
        FROM kg_contradictions
        WHERE status = 'needs_review'
        GROUP BY entity_ref
        HAVING COUNT(*) >= 2
        ORDER BY n DESC
        LIMIT %s
        """,
        (limit // 3 + 1,),
    )
    for row in contradiction_rows:
        suggestions.append(
            {
                "entity_ref": row["entity_ref"],
                "suggestion_type": "resolve_contradictions",
                "suggestion": (
                    f"Resolve {row['n']} open contradictions for '{row['entity_ref']}'."
                ),
                "priority": "high",
            }
        )

    if not suggestions:
        return {"suggestions_created": 0}

    # Deduplicate by (entity_ref, suggestion_type) — skip if already pending
    created = 0
    for s in suggestions[:limit]:
        existing = fetch_one(
            """
            SELECT id FROM kg_curation_suggestions
            WHERE entity_ref = %s AND suggestion_type = %s AND status = 'pending'
            """,
            (s["entity_ref"], s["suggestion_type"]),
        )
        if existing:
            continue
        execute(
            """
            INSERT INTO kg_curation_suggestions
                (entity_ref, suggestion_type, suggestion, priority, status)
            VALUES (%s, %s, %s, %s, 'pending')
            """,
            (s["entity_ref"], s["suggestion_type"], s["suggestion"], s["priority"]),
        )
        created += 1

    return {"suggestions_created": created}
