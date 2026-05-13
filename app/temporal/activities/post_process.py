"""Post-processing activity — scorecard, KG, session, webhook."""
from __future__ import annotations
import logging
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
