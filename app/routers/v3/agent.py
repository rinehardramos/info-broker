from __future__ import annotations

import json
import logging
import os
import uuid

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one
from app.routers.v3.tenancy import user_org_id
from app.routers.v3.models import AgentMessageIn, AgentMessageOut, AgentPipelineOut
from app.services.session_service import (
    classify_turn,
    build_session_context,
    build_conversational_reply,
    update_session_after_run,
)

router = APIRouter(prefix="/v3/agent", tags=["v3-agent"])

import os as _os
IS_USE_TEMPORAL = _os.getenv("IS_USE_TEMPORAL", "false").lower() == "true"


def _fast_thorough_enabled() -> bool:
    """Return True if fast+thorough parallel mode is enabled (default True)."""
    try:
        row = fetch_one("SELECT value FROM core_settings WHERE key = 'fast_thorough_mode'", ())
        return (row or {}).get("value", "true").lower() != "false"
    except Exception:
        return True

# PreFlight pending state — keyed by run_id.
# When PreFlight blocks a query, we store the pending research here and
# wait for the user to answer the clarification question via /brain-answer.
# Only then is the brain actually launched with the enriched query.
_PREFLIGHT_PENDING: dict[str, dict] = {}

# Per-session slot cache — stores the last successful SlotResult for each session so that
# PreFlight can skip re-asking questions already answered in a prior turn.
_SESSION_SLOTS: dict[str, "SlotResult"] = {}  # type: ignore[name-defined]

# Identification confirmation state — keyed by run_id.
# When the pipeline-layer confirmation gate fires, we hold the result here and
# wait for the user's Yes/No/Not sure response via /brain-answer.
_CONFIRM_PENDING: dict[str, dict] = {}

def _parse_identification_signals(query: str) -> dict:
    """Parse PRIMARY/SUPPORTING/CONTEXT labels from an enriched identification query."""
    signals = {"primary": "", "supporting": "", "context": ""}
    for line in query.splitlines():
        line = line.strip()
        if line.startswith("PRIMARY (subject to identify):"):
            signals["primary"] = line.split(":", 1)[-1].strip()
        elif line.startswith("SUPPORTING (scene details):"):
            signals["supporting"] = line.split(":", 1)[-1].strip()
        elif line.startswith("CONTEXT (franchise/platform constraints):"):
            signals["context"] = line.split(":", 1)[-1].strip()
    return signals

log = logging.getLogger(__name__)

SYSTEM_PIPELINE_ID = "00000000-0000-4000-8000-000000000001"


# ---------------------------------------------------------------------------
# Agent pipeline preference
# ---------------------------------------------------------------------------

def _get_active_pipeline(user_id: str) -> dict:
    """Return active pipeline row for this user (preference -> system default)."""
    prefs = fetch_one(
        "SELECT agent_pipeline_id FROM ui_preferences WHERE user_id = %s",
        (user_id,),
    )
    preferred_id = prefs["agent_pipeline_id"] if prefs else None

    if preferred_id:
        row = fetch_one(
            "SELECT id, name, is_system FROM pipelines WHERE id = %s AND (user_id = %s OR is_system = true)",
            (str(preferred_id), user_id),
        )
        if row:
            return row

    row = fetch_one(
        "SELECT id, name, is_system FROM pipelines WHERE id = %s",
        (SYSTEM_PIPELINE_ID,),
    )
    if not row:
        raise HTTPException(status_code=503, detail="No agent pipeline configured")
    return row


def _create_or_fetch_session(session_id: str | None, user_id: str, org_id: str, message: str) -> tuple[str, dict | None]:
    """Return (session_id, session_row). Creates session if session_id is None."""
    if not session_id:
        row = fetch_one(
            """INSERT INTO agent_sessions (id, user_id, org_id, genesis_query)
               VALUES (%s, %s, %s, %s) RETURNING *""",
            (str(uuid.uuid4()), user_id, org_id, message),
        )
        return str(row["id"]), dict(row) if row else None
    row = fetch_one(
        "SELECT * FROM agent_sessions WHERE id = %s AND user_id = %s AND org_id = %s",
        (session_id, user_id, org_id),
    )
    return session_id, dict(row) if row else None


async def _update_session_conversational(
    session_id: str, user_message: str, reply: str, uid: str
) -> None:
    """Lightweight session update for conversational replies."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        update_session_after_run,
        session_id, user_message, reply, None, [], "conversational", False,
    )


@router.get("/pipeline", response_model=AgentPipelineOut)
def get_agent_pipeline(user: dict = Depends(get_current_user)):
    row = _get_active_pipeline(str(user["id"]))
    return AgentPipelineOut(
        pipeline_id=str(row["id"]),
        pipeline_name=row["name"],
        is_system=row["is_system"],
    )


class AgentPipelineIn(BaseModel):
    pipeline_id: str


@router.put("/pipeline", response_model=AgentPipelineOut)
def set_agent_pipeline(body: AgentPipelineIn, user: dict = Depends(get_current_user)):
    from app.pipeline.nodes import NodeRegistry
    NodeRegistry.auto_discover()

    uid = str(user["id"])
    pipeline = fetch_one(
        "SELECT * FROM pipelines WHERE id = %s AND (user_id = %s OR is_system = true)",
        (body.pipeline_id, uid),
    )
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    nodes = fetch_all(
        "SELECT node_type, position_y FROM pipeline_nodes WHERE pipeline_id = %s",
        (body.pipeline_id,),
    )
    node_meta = {n.node_type: n.category for n in NodeRegistry.all()}
    sources = [n for n in nodes if node_meta.get(n["node_type"]) == "source" and n["node_type"] != "aggregator"]

    if len(sources) != 1:
        raise HTTPException(status_code=422, detail="Agent pipeline must have exactly one source node")
    if sources[0]["node_type"] != "agent_input":
        raise HTTPException(status_code=422, detail="Agent pipeline source must be agent_input")
    if sources[0]["position_y"] != 0:
        raise HTTPException(status_code=422, detail="agent_input must be the first node (position_y=0)")

    execute(
        """
        INSERT INTO ui_preferences (user_id, agent_pipeline_id)
        VALUES (%s, %s)
        ON CONFLICT (user_id) DO UPDATE SET agent_pipeline_id = EXCLUDED.agent_pipeline_id, updated_at = now()
        """,
        (uid, body.pipeline_id),
    )
    return AgentPipelineOut(
        pipeline_id=body.pipeline_id,
        pipeline_name=pipeline["name"],
        is_system=pipeline["is_system"],
    )


# ---------------------------------------------------------------------------
# Intelligent search — Claude Code brain (no Temporal, no pipeline nodes)
# ---------------------------------------------------------------------------


@router.get("/confirm/pending")
async def get_pending_confirmations(user: dict = Depends(get_current_user)):
    """Return any identification results held pending user confirmation for this user.

    Checks both in-memory _CONFIRM_PENDING (fast path) and DB confirm_pending rows
    (recovery path after restart). On restart, DB rows are reloaded into memory by
    the lifespan hook, so this DB fallback is an extra safety net.
    """
    uid = str(user["id"])
    pending = []

    # Primary: in-memory state
    seen_run_ids: set[str] = set()
    for run_id, state in list(_CONFIRM_PENDING.items()):
        # Skip rejected-list entries (keyed as "rejected:{run_id}", value is a list not a dict)
        if run_id.startswith("rejected:") or not isinstance(state, dict):
            continue
        if state.get("uid") != uid:
            continue
        result  = state.get("result", {})
        top     = (result.get("findings") or [{}])[0]
        pending.append({
            "run_id":         run_id,
            "candidate":      top.get("title", ""),
            "candidate_desc": top.get("content") or "",
            "candidate_url": top.get("url") or "",
            "candidate_image": top.get("image_url") or top.get("thumbnail_url") or top.get("poster_url") or "",
            "confidence":     top.get("confidence", 0),
            "alternatives":   result.get("considered_alternatives", [])[:3],
        })
        seen_run_ids.add(run_id)

    # Fallback: DB rows not yet in memory (e.g. between restart and lifespan hook)
    try:
        db_rows = fetch_all(
            "SELECT id, confirmation_data FROM pipeline_runs WHERE status = 'confirm_pending' AND user_id = %s AND org_id = %s",
            (uid, user_org_id(user)),
        )
        for row in db_rows:
            run_id = str(row["id"])
            if run_id in seen_run_ids:
                continue
            data = row.get("confirmation_data") or {}
            # Reload into memory so future WS replay works
            if isinstance(data, dict) and data.get("uid"):
                _CONFIRM_PENDING[run_id] = data
            result  = data.get("result", {})
            top     = (result.get("findings") or [{}])[0]
            pending.append({
                "run_id":         run_id,
                "candidate":      top.get("title", ""),
                "candidate_desc": top.get("content") or "",
                "candidate_url": top.get("url") or "",
                "candidate_image": top.get("image_url") or top.get("thumbnail_url") or top.get("poster_url") or "",
                "confidence":     top.get("confidence", 0),
                "alternatives":   result.get("considered_alternatives", [])[:3],
            })
    except Exception as exc:
        log.warning("confirm/pending DB fallback failed (non-fatal): %s", exc)

    return {"pending": pending}


@router.get("/brain/status")
async def get_brain_status(user: dict = Depends(get_current_user)):
    """Check if the IS brain (Claude Code) is authenticated and ready."""
    from app.is_brain import check_auth

    auth = await check_auth()
    has_api_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    return {
        "ready": auth.get("loggedIn", False) or has_api_key,
        "auth_method": "api_key" if has_api_key else auth.get("authMethod", "none"),
        "logged_in": auth.get("loggedIn", False),
        "has_api_key": has_api_key,
        "email": auth.get("email"),
        "error": auth.get("error"),
    }


# ---------------------------------------------------------------------------
# IS brain synchronous endpoint — for MCP / Claude Code direct access
# ---------------------------------------------------------------------------


@router.post("/research/sync")
async def run_research_sync(
    body: dict,
    user: dict = Depends(get_current_user),
):
    """Run the IS brain synchronously and return the full result.

    Intended for MCP tool use (run_intelligent_search) so Claude Code and
    other MCP clients can invoke the full investigation loop directly.
    Times out after 280s (MCP transport limit).
    """
    import asyncio
    from app.is_brain import run_research as _run_research
    from app.pipeline.strategies.orchestrator import classify_query, classify_complexity
    from app.pipeline.strategies.compiler import compile_strategy
    from app.pipeline.techniques import format_techniques_for_prompt

    uid = str(user["id"])
    query = (body.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}

    max_depth = int(body.get("max_depth", 3))
    max_branches = int(body.get("max_branches", 12))

    research_category = classify_query(query)
    _, complexity_score = classify_complexity(query)
    if complexity_score >= 5:
        max_depth = max(max_depth, 5)
        max_branches = max(max_branches, 40)
    elif complexity_score >= 3:
        max_depth = max(max_depth, 4)
        max_branches = max(max_branches, 30)

    try:
        from app.pipeline.strategies.orchestrator import classify_substrategy
        substrategy = await classify_substrategy(research_category, query)
    except Exception:
        substrategy = "none"

    entity_strategy = await compile_strategy(research_category, substrategy=substrategy)
    techniques_section = format_techniques_for_prompt()

    strategies_section = ""
    try:
        from app.pipeline.strategies.orchestrator import build_strategies_section
        strategies_section = await build_strategies_section(query)
    except Exception:
        pass

    meta_strategies_section = ""
    try:
        from app.pipeline.strategies.meta.compiler import build_meta_strategies_section
        meta_strategies_section = build_meta_strategies_section(query=query, entity_type=research_category)
    except Exception:
        pass

    healthy_nodes = []
    try:
        from app.pipeline.nodes import NodeRegistry
        NodeRegistry.auto_discover()
        healthy_nodes = [{"node_type": n.node_type, "display_name": n.display_name} for n in NodeRegistry.all()]
    except Exception:
        pass

    try:
        result = await asyncio.wait_for(
            _run_research(
                query=query,
                user_id=uid,
                max_depth=max_depth,
                max_branches=max_branches,
                available_nodes=healthy_nodes,
                strategies_section=strategies_section,
                entity_strategy=entity_strategy,
                techniques_section=techniques_section,
                meta_strategies_section=meta_strategies_section,
            ),
            timeout=280.0,
        )
    except asyncio.TimeoutError:
        return {"error": "Research timed out after 280s", "query": query, "summary": "Timed out — try a narrower query or increase max_depth"}
    except Exception as exc:
        log.error("run_research_sync failed: %s", exc)
        return {"error": str(exc), "query": query}

    return result


# ---------------------------------------------------------------------------
# Agent message — triggers pipeline run via Temporal
# ---------------------------------------------------------------------------

async def _run_is_research(
    run_id: str, uid: str, pipeline_id: str, query: str,
    past_research: list[dict] | None = None,
    session_id: str | None = None,
    session_context: str = "",
    preflight_result=None,
) -> None:
    """Background task: run IS brain and push WS events."""
    from app.routers.v3.stream import push_event

    started_at = datetime.now(timezone.utc)

    await push_event(uid, {
        "type": "job.update", "job_id": run_id, "status": "running",
        "run_id": run_id, "message": query,
    })

    # Update DB status to running so pipeline_runs reflects the active state
    try:
        execute(
            "UPDATE pipeline_runs SET status = 'running' WHERE id = %s",
            (run_id,),
        )
    except Exception:
        pass

    try:
        from app.is_brain import run_research

        async def _on_tool_event(ev: dict) -> None:
            # Strip MCP prefix: mcp__info-broker-mcp__run_ddg_search -> run_ddg_search
            raw_tool = ev.get("tool", "") or ""
            clean_tool = raw_tool.split("__")[-1] if "__" in raw_tool else raw_tool

            if ev.get("type") == "tool_result":
                await push_event(uid, {
                    "type": "is.tool_result",
                    "job_id": run_id, "run_id": run_id,
                    "call_id": ev.get("tool_use_id", ""),
                    "preview": ev.get("preview", ""),
                })
            elif clean_tool == "log_cycle":
                inp = ev.get("input", {}) or {}
                hyps = inp.get("hypotheses", [])
                if isinstance(hyps, str):
                    hyps = [h.strip() for h in hyps.split("\n") if h.strip()]
                await push_event(uid, {
                    "type": "is.cycle",
                    "job_id": run_id, "run_id": run_id,
                    "call_id": ev.get("id", ""),
                    "pir": inp.get("pir", ""),
                    "hypotheses": hyps,
                    "cycle_id": inp.get("cycle_id", "cycle_1"),
                    "parent_cycle_id": inp.get("parent_cycle_id", ""),
                })
            else:
                inp = ev.get("input", {}) or {}
                query_preview = str(
                    inp.get("query") or
                    inp.get("url") or
                    inp.get("name") or
                    inp.get("company_name") or
                    inp.get("feed_url") or
                    inp.get("title") or
                    inp.get("search_query") or
                    inp.get("pattern") or
                    inp.get("keyword") or
                    inp.get("term") or
                    inp.get("q") or
                    ""
                )[:120]
                await push_event(uid, {
                    "type": "is.tool_call",
                    "job_id": run_id, "run_id": run_id,
                    "tool": clean_tool,
                    "status": ev.get("status", ""),
                    "call_id": ev.get("id", ""),
                    "query_preview": query_preview,
                })

        # Only advertise healthy+enabled tools to the brain
        from app.routers.v3.pipelines import get_healthy_nodes
        healthy_nodes = await get_healthy_nodes()

        # Get matching procedural skills for SUGGESTED STRATEGIES
        strategies_section = ""
        try:
            from app.memory.skills import get_matching_skills, format_skills_for_prompt
            matching_skills = await get_matching_skills(query, limit=3)
            strategies_section = format_skills_for_prompt(matching_skills)
            # Track suggestion count
            for s in matching_skills:
                execute("UPDATE research_skills SET times_suggested = times_suggested + 1, last_suggested_at = now() WHERE id = %s", (str(s["id"]),))
        except Exception as exc:
            log.debug("Skill retrieval failed (non-fatal): %s", exc)

        # Load entity investigation strategy — auto-classify query to strategy
        from app.pipeline.strategies.orchestrator import classify_query, classify_complexity
        from app.pipeline.strategies.compiler import compile_strategy
        from app.pipeline.strategies.planner import format_plan_for_prompt, format_clarification_for_prompt  # noqa: F401
        research_category = classify_query(query)

        # Classify sub-strategy
        substrategy = "none"
        try:
            from app.pipeline.strategies.orchestrator import classify_substrategy
            substrategy = await classify_substrategy(research_category, query)
            log.info("IS Brain: substrategy=%s for category=%s", substrategy, research_category)
        except Exception as exc:
            log.warning("Sub-strategy classification failed: %s", exc)

        entity_strategy = await compile_strategy(research_category, substrategy=substrategy)

        # Load technique catalog
        from app.pipeline.techniques import format_techniques_for_prompt
        techniques_section = format_techniques_for_prompt()

        # Classify complexity so the IS brain can decide whether to clarify
        complexity_type, complexity_score = classify_complexity(query)
        log.info("IS Brain: complexity=%s score=%d for query: %s", complexity_type, complexity_score, query[:80])

        # Suggest starting depth based on complexity (no hard cap — brain goes deeper when needed)
        if complexity_score >= 5:
            max_depth, max_branches = 5, 40
        elif complexity_score >= 3:
            max_depth, max_branches = 4, 30
        else:
            max_depth, max_branches = 3, 20

        # Build user_sources context from uploaded files
        user_sources = ""
        try:
            source_rows = fetch_all(
                "SELECT filename, file_type, token_count, findings_count, manifest FROM research_sources WHERE user_id = %s AND status = 'indexed' ORDER BY created_at DESC",
                (uid,),
            )
            if source_rows:
                parts = ["## USER-PROVIDED SOURCES\n"]
                for src in source_rows:
                    manifest = src.get("manifest") or {}
                    tokens = src.get("token_count") or 0
                    fname = src["filename"]
                    ftype = src["file_type"]
                    fcount = src.get("findings_count", 0)

                    if tokens < 2000:
                        # Small file: include manifest + note that content is indexed
                        parts.append(f"[File: {fname} | {ftype} | {fcount} findings | {tokens} tokens]")
                        summary = manifest.get("summary", "")
                        if summary:
                            parts.append(f"Summary: {summary}")
                        parts.append("Content indexed in research memory — use query_uploaded_data to search it.\n")
                    else:
                        # Large file: manifest only
                        parts.append(f"[File: {fname} | {ftype} | {fcount} findings | {tokens} tokens]")
                        summary = manifest.get("summary", "")
                        if summary:
                            parts.append(f"Summary: {summary}")
                        columns = manifest.get("columns")
                        if columns:
                            parts.append(f"Columns: {', '.join(columns[:15])}")
                        parts.append("This file has been indexed in your research memory. Use query_uploaded_data to search specific rows, values, or keywords.\n")

                user_sources = "\n".join(parts)
        except Exception as exc:
            log.warning("Failed to load user sources: %s", exc)

        # Build meta-strategies section
        try:
            from app.pipeline.strategies.meta.compiler import build_meta_strategies_section
            meta_strategies_section = build_meta_strategies_section(
                query=query,
                entity_type=research_category,
            )
        except Exception as exc:
            log.warning("Meta-strategy compilation failed (non-fatal): %s", exc)
            meta_strategies_section = ""

        # Prepend PreFlight section to session_context so the brain sees it first
        if preflight_result is not None:
            if preflight_result.blocking:
                preflight_section = (
                    f"[PREFLIGHT: CLARIFICATION REQUIRED]\n"
                    f"Before any research, call ask_user() with this exact question:\n"
                    f"Question: {preflight_result.first_question}\n"
                    f"Options: {preflight_result.first_question_options}\n"
                    f"This is your FIRST and ONLY action. Do not search. Do not hypothesize.\n"
                    f"After the user answers, fold the answer into your research context and proceed."
                )
            elif preflight_result.tier == 3:
                preflight_section = (
                    f"[PREFLIGHT: LOW CONFIDENCE INTERPRETATION]\n"
                    f"Interpretation: {preflight_result.slots.raw_interpretation}\n"
                    f"Confidence: {preflight_result.confidence:.0%}\n"
                    f"Prepend to your summary: '{preflight_result.disclaimer}'\n"
                    f"Then proceed with research."
                )
            else:
                preflight_section = (
                    f"[PREFLIGHT: VALIDATED]\n"
                    f"Query interpreted as: {preflight_result.slots.raw_interpretation}\n"
                    f"Proceed directly to BROADEN — skip STEP 0 decomposition (already done)."
                )
            session_context = (
                preflight_section + "\n\n" + session_context
            ).strip()

        from app.pipeline.fusion.merger import merge_research_results as _merge

        if _fast_thorough_enabled():
            # Spawn fast (shallow preview) and thorough (full) in parallel
            fast_task = asyncio.create_task(run_research(
                query=query, user_id=uid, past_research=past_research,
                max_depth=1, max_branches=5,
                on_event=_on_tool_event,
                available_nodes=healthy_nodes,
                strategies_section="",
                entity_strategy="",
                techniques_section="",
                meta_strategies_section="",
                user_sources=user_sources,
                session_context=session_context,
            ))
            thorough_task = asyncio.create_task(run_research(
                query=query, user_id=uid, past_research=past_research,
                max_depth=max_depth, max_branches=max_branches,
                on_event=_on_tool_event,
                available_nodes=healthy_nodes,
                strategies_section=strategies_section,
                entity_strategy=entity_strategy,
                techniques_section=techniques_section,
                meta_strategies_section=meta_strategies_section,
                user_sources=user_sources,
                session_context=session_context,
            ))

            await push_event(uid, {"type": "research.fast.started", "run_id": run_id, "job_id": run_id})
            await push_event(uid, {"type": "research.thorough.started", "run_id": run_id, "job_id": run_id})

            fast_result, thorough_result = await asyncio.gather(fast_task, thorough_task)

            await push_event(uid, {
                "type": "research.fast.completed", "run_id": run_id, "job_id": run_id,
                "findings": fast_result.get("findings", []),
                "count": len(fast_result.get("findings", [])),
            })

            result = _merge(fast_result, thorough_result, query)

            await push_event(uid, {
                "type": "research.thorough.completed", "run_id": run_id, "job_id": run_id,
                "confirmed_count": result.get("confirmed_count", 0),
                "merged_count": result.get("merged_count", 0),
            })
        else:
            # Original single-run path
            result = await run_research(
                query=query, user_id=uid, past_research=past_research,
                max_depth=max_depth, max_branches=max_branches,
                on_event=_on_tool_event,
                available_nodes=healthy_nodes,
                strategies_section=strategies_section,
                entity_strategy=entity_strategy,
                techniques_section=techniques_section,
                meta_strategies_section=meta_strategies_section,
                user_sources=user_sources,
                session_context=session_context,
            )

        # Check if IS brain returned an error result (no findings, error summary)
        is_error = (
            not result.get("findings")
            and result.get("summary", "").startswith("Research failed:")
        )
        if is_error:
            raise RuntimeError(result["summary"])

        # ── Pipeline-layer identification confirmation gate ────────────────
        # The brain cannot reliably self-police this gate at high confidence,
        # so the orchestrator enforces it deterministically.
        is_identification = query.startswith("[IDENTIFICATION TASK")
        if is_identification:
            top_finding = (result.get("findings") or [{}])[0]
            top_confidence = top_finding.get("confidence", 0)
            alternatives = result.get("considered_alternatives") or []
            rejected = _CONFIRM_PENDING.get(f"rejected:{run_id}", [])
            rejection_count = len(rejected)

            should_confirm = (
                top_confidence < 98
                and (len(alternatives) >= 1 or top_confidence < 85)
                and rejection_count < 2
            )

            candidate_name = top_finding.get("title", "this result")
            candidate_desc = top_finding.get("content") or ""
            candidate_url = top_finding.get("url") or ""
            candidate_image = (
                top_finding.get("image_url")
                or top_finding.get("thumbnail_url")
                or top_finding.get("poster_url")
                or ""
            )

            if should_confirm:
                state = {
                    "uid": uid,
                    "result": result,
                    "run_id": run_id,
                    "pipeline_id": pipeline_id,
                    "query": query,
                    "session_id": session_id,
                    "session_context": session_context,
                    "past_research": past_research,
                    "rejected": rejected + [candidate_name],
                }
                # Persist to DB so the state survives server restarts
                execute(
                    "UPDATE pipeline_runs SET status = 'confirm_pending', confirmation_data = %s WHERE id = %s",
                    (json.dumps(state), run_id),
                )
                _CONFIRM_PENDING[run_id] = state
                from app.routers.v3.stream import push_event as _push_confirm
                await _push_confirm(uid, {
                    "type": "brain.confirm",
                    "run_id": run_id,
                    "job_id": run_id,
                    "candidate": candidate_name,
                    "candidate_desc": candidate_desc,
                    "candidate_url": candidate_url,
                    "candidate_image": candidate_image,
                    "confidence": top_confidence,
                    "alternatives": alternatives[:3],
                })
                # Don't store trail or push success yet — wait for confirmation
                return
        # ─────────────────────────────────────────────────────────────────

        # Update session after investigation run
        if session_id:
            try:
                findings = result.get("findings") or []
                summary = result.get("summary") or ""
                entity_type = result.get("entity_type") or "unknown"
                update_session_after_run(
                    session_id=session_id,
                    user_message=query,
                    agent_summary=summary,
                    run_id=run_id,
                    findings=findings,
                    entity_type=entity_type,
                    is_investigation=True,
                )
                execute(
                    "UPDATE pipeline_runs SET session_id = %s WHERE id = %s",
                    (session_id, run_id),
                )
            except Exception as exc:
                log.warning("Session update after run failed: %s", exc)

        # Verify findings quality
        from app.pipeline.strategies.verifier import verify_findings
        verification = verify_findings(result.get("findings", []))
        log.info("IS Brain: verification status=%s issues=%d", verification["status"], len(verification.get("issues", [])))

        suggested_pipeline = result.get("pipeline")
        # Delete any prior trail for this run_id (re-run scenario — same run_id, new result)
        execute("DELETE FROM research_trails WHERE run_id = %s", (run_id,))
        trail_id = str(uuid.uuid4())
        execute(
            """INSERT INTO research_trails
                (id, user_id, run_id, query, entity_type, trail, findings, tool_calls, suggested_pipeline)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (trail_id, uid, run_id, query,
             result.get("entity_type", "unknown"),
             json.dumps(result.get("tree", {})),
             json.dumps(result.get("findings", [])),
             result.get("tree", {}).get("total_branches", 0),
             json.dumps(suggested_pipeline) if suggested_pipeline else None),
        )
        execute(
            "UPDATE research_trails SET verification_status = %s WHERE run_id = %s",
            (verification["status"], run_id),
        )

        # Index findings to research_memory for multi-signal retrieval
        try:
            from app.memory.writer import index_research_findings
            await index_research_findings(run_id, query, result.get("findings", []))
        except Exception as exc:
            log.warning("Memory indexing failed (non-fatal): %s", exc)

        # Intelligence Fusion: extract selectors + write to KG
        try:
            from app.pipeline.fusion.selectors import extract_selectors_from_findings
            from app.pipeline.fusion.writer import write_entities_to_kg, write_relationships_to_kg

            # Extract selectors as lightweight entity observations
            selectors = extract_selectors_from_findings(result.get("findings", []))
            if selectors:
                # Convert selectors to entity format for KG
                selector_entities = [
                    {"name": s["value"], "type": s["type"], "attributes": {"selector_type": s["type"]}}
                    for s in selectors
                ]
                await write_entities_to_kg(run_id, selector_entities, "intelligent_search")

            # If analyzer-extracted entities exist, write those too
            for finding in result.get("findings", []):
                if finding.get("source") == "analyzer" and finding.get("entities"):
                    await write_entities_to_kg(run_id, finding["entities"], "analyzer")
                if finding.get("source") == "analyzer" and finding.get("relationships"):
                    await write_relationships_to_kg(run_id, finding["relationships"], "analyzer")
        except Exception as exc:
            log.warning("Fusion layer failed (non-fatal): %s", exc)

        # Completeness assessment + deception detection
        try:
            from app.pipeline.fusion.completeness import assess_completeness
            from app.pipeline.fusion.deception import detect_deception

            entity_type = result.get("entity_type", "person")
            completeness = assess_completeness(
                result.get("findings", []),
                selectors if 'selectors' in dir() else [],
                entity_type,
            )
            deception_results = detect_deception(result.get("findings", []))
            deception_flagged = [d for d in deception_results if d.get("deception_risk", 0) > 0.3]

            # Log coverage summary
            log.info(
                "Investigation completeness: %.0f%% coverage, %d gaps, %d deception flags",
                completeness.get("coverage_pct", 0) * 100,
                len(completeness.get("gaps", [])),
                len(deception_flagged),
            )
        except Exception as exc:
            log.warning("Completeness/deception analysis failed (non-fatal): %s", exc)

        # Corroboration tracking + temporal decay + ACH conflict resolution + PIR coverage
        try:
            from app.pipeline.fusion.classification import track_corroboration
            from app.pipeline.fusion.decay import apply_decay_to_findings
            from app.pipeline.fusion.ach import detect_conflicts, build_ach_matrix, evaluate_hypotheses
            from app.pipeline.fusion.pir import decompose_query_to_pirs, map_findings_to_pirs, generate_coverage_report

            raw_findings = result.get("findings", [])
            entity_type = result.get("entity_type", "person")

            # Corroboration: enrich findings with cross-source confirmation
            corroborated = track_corroboration(raw_findings)
            multi_source = [f for f in corroborated if f.get("corroboration_level") == "multi_source"]

            # Decay: apply temporal confidence degradation
            decayed = apply_decay_to_findings(raw_findings)

            # ACH: detect and resolve conflicting findings
            conflicts = detect_conflicts(raw_findings)
            ach_results = []
            for conflict in conflicts[:3]:  # Max 3 conflicts to analyze
                matrix = build_ach_matrix(conflict["hypotheses"], conflict["evidence"])
                ach_result = evaluate_hypotheses(matrix)
                ach_results.append({
                    "dimension": conflict["dimension"],
                    "winner": ach_result.winner,
                    "confidence": ach_result.confidence,
                })

            # PIR: decompose query into intelligence requirements and assess coverage
            pirs = decompose_query_to_pirs(query, entity_type)
            mapped_pirs = map_findings_to_pirs(pirs, raw_findings)
            pir_report = generate_coverage_report(mapped_pirs)

            log.info(
                "Intelligence analysis: %d multi-source findings, %d conflicts resolved, PIR coverage %.0f%%",
                len(multi_source),
                len(ach_results),
                pir_report.get("overall_coverage", 0) * 100,
            )
        except Exception as exc:
            log.warning("Intelligence analysis failed (non-fatal): %s", exc)

        # Build strategy scorecard
        try:
            from app.pipeline.fusion.scorecard import build_scorecard
            scorecard = build_scorecard(
                trail=result.get("tree", {}),
                findings=result.get("findings", []),
                completeness_pct=completeness.get("coverage_pct", 0.0) if 'completeness' in dir() else 0.0,
                entity_type=result.get("entity_type", "person"),
            )
            # Persist scorecard to research_trails
            from app.routers.v3.db import execute as db_exec
            db_exec(
                "UPDATE research_trails SET scorecard = %s WHERE run_id = %s",
                (json.dumps(scorecard), run_id),
            )
            log.info("Scorecard: strategy=%s, %d tactics", scorecard["strategy"]["auto_grade"], len(scorecard["tactics"]))
        except Exception as exc:
            log.warning("Scorecard build failed (non-fatal): %s", exc)

        # Create procedural memory skill
        try:
            from app.memory.skills import create_skill_from_run
            duration = int((datetime.now(timezone.utc) - started_at).total_seconds()) if started_at else 0
            await create_skill_from_run(run_id, query, result, duration_seconds=duration)
        except Exception as exc:
            log.warning("Skill creation failed (non-fatal): %s", exc)

        # Analyze pivot patterns for strategy overlay learning
        try:
            from app.pipeline.strategies.analyzer import analyze_run_pivots
            await analyze_run_pivots(run_id, query, result, entity_type=research_category)
        except Exception as exc:
            log.warning("Pivot analysis failed (non-fatal): %s", exc)

        # Deduplicate plugin suggestions against existing nodes
        from app.pipeline.nodes import NodeRegistry
        NodeRegistry.auto_discover()
        existing_types = {n.node_type for n in NodeRegistry.all()}

        for plugin in result.get("suggested_plugins", []):
            pname = (plugin.get("name") or "").lower().replace("-", "_").replace(" ", "_")
            reason = plugin.get("reason", "")
            is_enhancement = reason.startswith("ENHANCE:") or pname in existing_types
            if not is_enhancement:
                for et in existing_types:
                    if pname in et or et in pname:
                        is_enhancement = True
                        plugin["reason"] = f"ENHANCE ({et}): {reason}"
                        break
            plugin["is_enhancement"] = is_enhancement
            status = "enhancement" if is_enhancement else "pending"
            execute(
                "INSERT INTO plugin_requests (id, user_id, spec, status) VALUES (%s, %s, %s, %s)",
                (str(uuid.uuid4()), uid, json.dumps(plugin), status),
            )

        # Track auto-created plugins that produced results
        try:
            from app.pipeline.auto_create import is_auto_create_enabled
            if is_auto_create_enabled():
                finding_sources = {f.get("source", "") for f in result.get("findings", [])}
                for plugin in result.get("suggested_plugins", []):
                    pname = (plugin.get("name") or "").lower().replace("-", "_").replace(" ", "_")
                    if pname in finding_sources:
                        execute(
                            "UPDATE plugin_requests SET status = 'auto_implemented', reviewed_at = now() WHERE spec->>'name' = %s AND status = 'pending'",
                            (pname,),
                        )
        except Exception as exc:
            log.warning("Auto-create tracking failed (non-fatal): %s", exc)

        execute(
            "UPDATE pipeline_runs SET status = 'succeeded', finished_at = now() WHERE id = %s",
            (run_id,),
        )

        summary = result.get("summary", "Research complete.")
        findings_count = len(result.get("findings", []))
        await push_event(uid, {
            "type": "job.completed", "job_id": run_id, "status": "succeeded",
            "run_id": run_id,
            "message": f"{summary[:200]}{'...' if len(summary) > 200 else ''} ({findings_count} findings)",
            "verification_status": verification["status"],
        })
        # Also notify Live panel's pipeline section
        await push_event(uid, {
            "type": "pipeline.run.complete", "run_id": run_id, "status": "succeeded",
        })
        # Fire webhook if callback_url is set
        try:
            _run_row = fetch_one("SELECT callback_url FROM pipeline_runs WHERE id = %s", (run_id,))
            if _run_row and _run_row.get("callback_url"):
                from app.services.webhook import deliver_webhook
                asyncio.create_task(deliver_webhook(
                    run_id=run_id,
                    payload={"run_id": run_id, "status": "succeeded", "job_id": run_id},
                    callback_url=_run_row["callback_url"],
                ))
        except Exception as exc:
            log.warning("Webhook dispatch failed (non-fatal): %s", exc)
    except Exception as exc:
        error_msg = str(exc)[:1000]
        log.error("IS Brain failed: %s", error_msg)
        execute(
            "UPDATE pipeline_runs SET status = 'failed', finished_at = now(), error_message = %s WHERE id = %s",
            (error_msg, run_id),
        )
        await push_event(uid, {
            "type": "job.failed", "job_id": run_id, "status": "failed",
            "run_id": run_id,
            "message": f"Research failed: {error_msg[:200]}",
            "error": error_msg,
        })
        await push_event(uid, {
            "type": "pipeline.run.complete", "run_id": run_id, "status": "failed",
            "error": error_msg,
        })
        # Fire webhook if callback_url is set
        try:
            _run_row = fetch_one("SELECT callback_url FROM pipeline_runs WHERE id = %s", (run_id,))
            if _run_row and _run_row.get("callback_url"):
                from app.services.webhook import deliver_webhook
                asyncio.create_task(deliver_webhook(
                    run_id=run_id,
                    payload={"run_id": run_id, "status": "failed", "job_id": run_id, "error": error_msg[:200]},
                    callback_url=_run_row["callback_url"],
                ))
        except Exception as exc:
            log.warning("Webhook dispatch failed (non-fatal): %s", exc)


@router.post("/message", response_model=AgentMessageOut, status_code=202)
async def send_message(
    body: AgentMessageIn,
    user: dict = Depends(get_current_user),
):
    from app.pipeline.workflow import NodeSpec, EdgeSpec
    from app.pipeline.runner import launch_pipeline_run

    uid = str(user["id"])
    pipeline_row = _get_active_pipeline(uid)
    pipeline_id = str(pipeline_row["id"])

    run_id = str(uuid.uuid4())
    workflow_id = f"pipeline-{run_id}"

    if body.use_intelligent_search:
        # IS bypasses the pipeline entirely — runs Claude Code as a subprocess brain.
        # A pipeline_run record is created for UI tracking; research runs in background.

        # --- Session handling ---
        sid, session_row = _create_or_fetch_session(body.session_id, uid, user_org_id(user), body.message)

        # Classifier decides mode (first message always = investigation, no prior thread)
        thread = (session_row or {}).get("conversation_thread") or []
        summary = (session_row or {}).get("accumulated_summary") or ""
        genesis = (session_row or {}).get("genesis_query") or body.message
        mode = classify_turn(body.message, thread, summary, genesis) if thread else "investigation"

        # --- Conversational reply path ---
        if mode == "conversational" and session_row:
            reply_text = build_conversational_reply(body.message, session_row)
            asyncio.create_task(_update_session_conversational(
                sid, body.message, reply_text, uid
            ))
            return AgentMessageOut(
                job_id=None,
                session_id=sid,
                status="done",
                reply=reply_text,
                mode="conversational",
            )

        # --- Full investigation path ---
        session_context = build_session_context(session_row, body.message)

        # Budget reservation gate (Phase 2)
        from app.pipeline.budget import RunBudgetIn, plan_run_budget, reserve_budget, estimate_run_cost
        import json as _json
        _raw_budget = getattr(body, "run_budget", None) or {}
        _budget_in = RunBudgetIn(**_raw_budget) if isinstance(_raw_budget, dict) else RunBudgetIn()
        _budget_plan = plan_run_budget(_budget_in)
        _estimated_cost = estimate_run_cost(_budget_in)

        _reserved = reserve_budget(uid, user_org_id(user), _estimated_cost)
        if not _reserved:
            raise HTTPException(status_code=402, detail="Insufficient budget — top up your wallet to run research")

        fetch_one(
            """
            INSERT INTO pipeline_runs (id, pipeline_id, user_id, org_id, temporal_workflow_id, status, trigger_type, query, budget_status, run_budget, budget_plan)
            VALUES (%s, %s, %s, %s, %s, 'queued', 'agent_is', %s, 'reserved', %s, %s)
            RETURNING *
            """,
            (run_id, pipeline_id, uid, user_org_id(user), workflow_id, body.message,
             _json.dumps(_raw_budget), _json.dumps(_budget_plan.breakdown)),
        )

        # Grounding pass — always retrieve similar past findings before launching brain.
        # For explicit "Go Deeper" (parent_run_id set), use the parent trail directly.
        # For all other queries, run fused_retrieve to inject graded prior research.
        past_research = None
        if body.parent_run_id:
            parent_trail = fetch_one(
                "SELECT query, entity_type, findings, trail FROM research_trails WHERE run_id = %s",
                (body.parent_run_id,),
            )
            if parent_trail:
                trail_data = parent_trail["trail"] if isinstance(parent_trail["trail"], dict) else {}
                past_research = [{
                    "query": parent_trail["query"],
                    "entity_type": parent_trail["entity_type"],
                    "findings": parent_trail["findings"] if isinstance(parent_trail["findings"], list) else [],
                    "summary": "",
                    "deeper_leads": trail_data.get("deeper_leads", []),
                    "grade": "",
                }]
        else:
            # Automatic grounding — retrieve semantically similar past research from memory.
            # A-graded (user-verified) findings are injected as assertions the brain must
            # affirm or update with fresh evidence, not ignore.
            try:
                from app.memory.retriever import fused_retrieve
                grounded = await fused_retrieve(body.message, limit=12, user_id=uid)
                if grounded:
                    # Group by run_id to reconstruct per-run summaries
                    by_run: dict[str, list] = {}
                    for r in grounded:
                        key = r.run_id or r.ref
                        by_run.setdefault(key, []).append(r)

                    past_research = []
                    for run_key, results in list(by_run.items())[:4]:
                        top = results[0]
                        grade = ""
                        # Prefer results with positive user score (A/B graded)
                        scored = [r for r in results if r.user_score > 0]
                        if scored:
                            top = scored[0]
                            grade = "A"  # user-verified finding
                        past_research.append({
                            "query": body.message,
                            "entity_type": "unknown",
                            "findings": [
                                {"title": r.title, "content": r.content[:300], "source": r.source_tool or r.source}
                                for r in results[:5] if r.title
                            ],
                            "summary": top.content[:400] if top.content else "",
                            "deeper_leads": [],
                            "grade": grade,
                        })

                    if not past_research:
                        past_research = None
            except Exception as exc:
                log.warning("Grounding pass failed (non-fatal): %s", exc)
                past_research = None

        # PreFlight requirements validation — runs before brain launches.
        # If blocking, emit brain.question directly and hold the brain; do NOT launch yet.
        preflight_result = None
        try:
            from app.pipeline.preflight import validate as preflight_validate
            sid_for_slots = sid or ""
            prior_slots = _SESSION_SLOTS.get(sid_for_slots)
            preflight_result = preflight_validate(body.message, prior_slots=prior_slots)
            # Cache slots so the next turn in this session can skip already-answered questions.
            if preflight_result and preflight_result.slots._haiku_succeeded:
                _SESSION_SLOTS[sid_for_slots] = preflight_result.slots
        except Exception as exc:
            log.warning("PreFlight validation failed (non-fatal): %s", exc)

        if preflight_result and preflight_result.blocking:
            # Gate: return question inline in HTTP response (reliable) AND via WS (belt+suspenders).
            # The brain is NOT launched. Research resumes when the user answers
            # via POST /v3/agent/brain-answer with this run_id.
            # Mark run as awaiting_input so LIVE doesn't show it as an active research run.
            execute(
                "UPDATE pipeline_runs SET status = 'awaiting_input' WHERE id = %s",
                (run_id,),
            )
            from app.routers.v3.stream import push_event as _push_event
            asyncio.create_task(_push_event(uid, {
                "type": "brain.question",
                "run_id": run_id,
                "job_id": run_id,
                "question": preflight_result.first_question,
                "options": preflight_result.first_question_options or [],
                "preflight": True,
            }))
            _PREFLIGHT_PENDING[run_id] = {
                "uid": uid,
                "pipeline_id": pipeline_id,
                "original_query": body.message,
                "past_research": past_research,
                "session_id": sid,
                "session_context": session_context,
                "question": preflight_result.first_question,
            }
            return AgentMessageOut(
                job_id=run_id,
                session_id=sid,
                status="pending",
                mode="question",
                question=preflight_result.first_question,
                options=preflight_result.first_question_options or [],
            )

        # Fire and forget — research runs async, pushes WS events when done.
        if IS_USE_TEMPORAL:
            from app.temporal.workflows.is_run import ISRunWorkflow, ISRunInput
            from temporalio.client import Client
            _host = _os.getenv("TEMPORAL_HOST", "localhost")
            _port = int(_os.getenv("TEMPORAL_PORT", "7233"))
            _t_client = await Client.connect(f"{_host}:{_port}")
            await _t_client.start_workflow(
                ISRunWorkflow.run,
                ISRunInput(
                    run_id=run_id,
                    user_id=uid,
                    org_id=user_org_id(user),
                    query=body.message,
                    pipeline_id=pipeline_id,
                    session_id=sid,
                    session_context=session_context,
                    past_research=past_research or [],
                    budget=_raw_budget,
                    callback_url=getattr(body, "callback_url", None),
                    preflight_prior_slots=dict(_SESSION_SLOTS.get(sid or "", {}) or {}),
                ),
                id=f"is-run-{run_id}",
                task_queue="is-run-tasks",
            )
        else:
            task = asyncio.create_task(
                _run_is_research(
                    run_id, uid, pipeline_id, body.message,
                    past_research=past_research,
                    session_id=sid,
                    session_context=session_context,
                    preflight_result=preflight_result,
                )
            )
            task.add_done_callback(lambda t: log.error("IS research task failed: %s", t.exception()) if t.exception() else None)

        return AgentMessageOut(job_id=run_id, session_id=sid, status="pending", mode="investigation")

    else:
        nodes_rows = fetch_all(
            "SELECT * FROM pipeline_nodes WHERE pipeline_id = %s ORDER BY position_y, position_x",
            (pipeline_id,),
        )
        edges_rows = fetch_all(
            "SELECT * FROM pipeline_edges WHERE pipeline_id = %s",
            (pipeline_id,),
        )

        # Budget reservation gate (Phase 2)
        from app.pipeline.budget import RunBudgetIn, plan_run_budget, reserve_budget, estimate_run_cost
        import json as _json
        _raw_budget = getattr(body, "run_budget", None) or {}
        _budget_in = RunBudgetIn(**_raw_budget) if isinstance(_raw_budget, dict) else RunBudgetIn()
        _budget_plan = plan_run_budget(_budget_in)
        _estimated_cost = estimate_run_cost(_budget_in)

        _reserved = reserve_budget(uid, user_org_id(user), _estimated_cost)
        if not _reserved:
            raise HTTPException(status_code=402, detail="Insufficient budget — top up your wallet to run research")

        fetch_one(
            """
            INSERT INTO pipeline_runs (id, pipeline_id, user_id, org_id, temporal_workflow_id, status, trigger_type, budget_status, run_budget, budget_plan)
            VALUES (%s, %s, %s, %s, %s, 'queued', 'agent', 'reserved', %s, %s)
            RETURNING *
            """,
            (run_id, pipeline_id, uid, user_org_id(user), workflow_id,
             _json.dumps(_raw_budget), _json.dumps(_budget_plan.breakdown)),
        )
        for node in nodes_rows:
            execute(
                "INSERT INTO pipeline_step_runs (id, run_id, node_id, status) VALUES (%s, %s, %s, 'pending')",
                (str(uuid.uuid4()), run_id, str(node["id"])),
            )

        def _node_config(node: dict) -> dict:
            cfg = dict(node["config"] or {})
            if node["node_type"] == "agent_input":
                cfg["message"] = body.message
            return cfg

        nodes = [
            NodeSpec(
                node_id=str(n["id"]),
                node_type=n["node_type"],
                label=n["label"],
                config=_node_config(n),
            )
            for n in nodes_rows
        ]
        edges = [
            EdgeSpec(
                source_node_id=str(e["source_node_id"]),
                target_node_id=str(e["target_node_id"]),
                edge_type=e["edge_type"],
            )
            for e in edges_rows
        ]

    host = os.getenv("TEMPORAL_HOST", "localhost")
    port = int(os.getenv("TEMPORAL_PORT", "7233"))

    try:
        await launch_pipeline_run(
            run_id=run_id,
            user_id=uid,
            pipeline_id=pipeline_id,
            nodes=nodes,
            edges=edges,
            temporal_host=host,
            temporal_port=port,
        )
    except HTTPException:
        execute(
            "UPDATE pipeline_runs SET status = 'failed', finished_at = now() WHERE id = %s",
            (run_id,),
        )
        raise

    return AgentMessageOut(job_id=run_id)
