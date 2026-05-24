"""Post-processing activity — scorecard, KG, session, webhook."""
from __future__ import annotations
import json
import logging
import uuid
from dataclasses import dataclass, field
from temporalio import activity

log = logging.getLogger(__name__)


@dataclass
class PostProcessInput:
    run_id: str
    user_id: str
    session_id: str | None
    brain_result: dict
    callback_url: str | None = None


@activity.defn(name="post_process")
async def post_process(inp: PostProcessInput) -> None:
    """Run post-processing. Idempotent — skips if run already succeeded."""
    from app.routers.v3.db import execute, fetch_one
    from app.routers.v3.stream import push_event
    import asyncio

    # Idempotency check
    row = fetch_one("SELECT status FROM pipeline_runs WHERE id = %s", (inp.run_id,))
    if row and row.get("status") == "succeeded":
        return

    result = inp.brain_result
    findings = result.get("findings", [])
    summary = result.get("summary", "")

    # Annotate findings
    try:
        from app.pipeline.fusion.pyramid_scoring import annotate_findings
        from app.pipeline.fusion.topic_clustering import cluster_findings
        findings = annotate_findings(findings)
        cluster_findings(findings)  # returns cluster labels; findings are annotated in-place
    except Exception as exc:
        log.warning("Annotation failed (non-fatal): %s", exc)

    # Index findings into research_memory (Qdrant) so future runs can retrieve
    # them via fused_retrieve. Best-effort; never fails the run.
    try:
        from app.memory.writer import index_research_findings
        if findings:
            indexed = await index_research_findings(
                inp.run_id, result.get("query", ""), findings,
            )
            log.info("post_process: indexed %d findings to research_memory", indexed)
    except Exception as exc:
        log.warning("research_memory indexing failed (non-fatal): %s", exc)

    # PIR coverage: for queries that look like investigations (person /
    # company), decompose into Priority Intelligence Requirements and report
    # which Essential Elements of Information are still un-resolved. Non-fatal.
    try:
        from app.pipeline.fusion.pir import (
            infer_entity_type, decompose_query_to_pirs,
            map_findings_to_pirs, generate_coverage_report,
        )
        query_text = (result.get("query") or "")
        entity_type = result.get("entity_type") or "unknown"
        if entity_type == "unknown" or not entity_type:
            entity_type = infer_entity_type(query_text)
        pirs = decompose_query_to_pirs(query_text, entity_type)
        pirs = map_findings_to_pirs(pirs, findings or [])
        report = generate_coverage_report(pirs)
        # Stash on result so it propagates to WS event listeners + downstream.
        result.setdefault("_loop_meta", {})
        result["_loop_meta"]["pir"] = {
            "entity_type": entity_type,
            "overall_coverage": report["overall_coverage"],
            "resolved_eeis": report["resolved_eeis"],
            "total_eeis": report["total_eeis"],
            "gaps": report["gaps"][:8],   # cap for prompt/UI sanity
            "pir_summaries": [
                {"name": p["name"], "coverage": p["coverage"],
                 "confidence": p["confidence"]}
                for p in report["pirs"]
            ],
        }
        log.info(
            "post_process: PIR entity=%s coverage=%.0f%% resolved=%d/%d gaps=%d",
            entity_type, report["overall_coverage"] * 100,
            report["resolved_eeis"], report["total_eeis"], len(report["gaps"]),
        )
    except Exception as exc:
        log.warning("PIR coverage failed (non-fatal): %s", exc)

    # Persist research_trails row. The workflow now builds an engine_v2-shaped
    # trail via WorkingMemory.to_engine_v2_trail() and stashes it under
    # _engine_v2_trail / _engine_v2_findings so /v3/runs/{id}/replay returns
    # populated phases / cards / candidates for IS-loop runs. Falls back to
    # the legacy `tree` shape if those keys are absent (e.g. ISRunWorkflow
    # Path A, which doesn't yet build a v2 trail).
    try:
        execute("DELETE FROM research_trails WHERE run_id = %s", (inp.run_id,))
        trail_id = str(uuid.uuid4())
        v2_trail = result.get("_engine_v2_trail")
        v2_findings = result.get("_engine_v2_findings")
        if isinstance(v2_trail, dict) and isinstance(v2_findings, list):
            trail_blob = v2_trail
            findings_blob = v2_findings
            tool_calls_count = len(v2_trail.get("branches") or [])
        else:
            trail_blob = result.get("tree") or {}
            findings_blob = findings
            tool_calls_count = (result.get("tree") or {}).get("total_branches", 0)
        execute(
            """INSERT INTO research_trails
                (id, user_id, run_id, query, entity_type, trail, findings, tool_calls, suggested_pipeline)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                trail_id,
                inp.user_id,
                inp.run_id,
                result.get("query", ""),
                result.get("entity_type", "unknown"),
                json.dumps(trail_blob),
                json.dumps(findings_blob),
                tool_calls_count,
                json.dumps(result.get("pipeline")) if result.get("pipeline") else None,
            ),
        )
    except Exception as exc:
        log.warning("research_trails persistence failed (non-fatal): %s", exc)

    # Mark succeeded
    execute(
        """UPDATE pipeline_runs
           SET status = 'succeeded', finished_at = now(),
               error_message = NULL
           WHERE id = %s""",
        (inp.run_id,),
    )

    # Push completion event
    asyncio.create_task(push_event(inp.user_id, {
        "type": "job.completed", "job_id": inp.run_id, "run_id": inp.run_id,
        "status": "succeeded", "result": result,
    }))

    # Push is.run_complete so the v3 UI's CandidateComparison + ACHMatrix
    # populate live without waiting for the user to navigate away and back
    # to trigger a replay-hydrate. Mirrors engine_v2.py's emission.
    _v2 = result.get("_engine_v2_trail") or {}
    if isinstance(_v2, dict):
        asyncio.create_task(push_event(inp.user_id, {
            "type": "is.run_complete",
            "job_id": inp.run_id, "run_id": inp.run_id,
            "status": _v2.get("status") or "succeeded",
            "ranked_candidates": _v2.get("ranked_candidates") or [],
            "ach_matrix": _v2.get("ach_matrix"),
        }))

    # Session update
    if inp.session_id:
        try:
            from app.services.session_service import update_session_after_run
            update_session_after_run(
                session_id=inp.session_id,
                user_message=result.get("query", ""),
                agent_summary=summary,
                run_id=inp.run_id,
                findings=findings,
                entity_type=result.get("entity_type", "unknown"),
                is_investigation=True,
                result=result,
            )
        except Exception as exc:
            log.warning("Session update failed (non-fatal): %s", exc)

    # Webhook delivery
    if inp.callback_url:
        try:
            from app.services.webhook import deliver_webhook
            asyncio.create_task(deliver_webhook(
                inp.run_id,
                {"run_id": inp.run_id, "status": "succeeded"},
                inp.callback_url,
            ))
        except Exception:
            pass
