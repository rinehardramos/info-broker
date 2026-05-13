"""Brain question/answer queue — manages the clarification loop between IS brain and user."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.routers.v3.auth import get_current_user

router = APIRouter(prefix="/v3/agent", tags=["v3-agent-brain"])
log = logging.getLogger(__name__)

# In-memory state keyed by run_id
_pending_events: dict[str, asyncio.Event] = {}
_pending_answers: dict[str, str] = {}

# Stores answered PreFlight questions so the brain can retrieve prior answers
# instead of re-asking: {run_id: {question_text: answer}}
_CLARIFICATION_MANIFEST: dict[str, dict[str, str]] = {}


def _build_ad_celebrity_hint(clarifications: list[str], context_signal: str) -> str:
    """When the user saw a social-media or YouTube ad, inject a celebrity-identification hint.

    Ads aggregate content from multiple shows/franchises. A person described by their
    franchise role ("girl in spiderman") is likely a CELEBRITY being identified by their
    most-known role — not a character in that franchise's own new series.
    The brain must consider both interpretations and search for ACTRESS FROM franchise
    as well as CHARACTER IN franchise.
    """
    clari_lower = " ".join(clarifications).lower()
    is_ad = any(w in clari_lower for w in ("ad", "advertisement", "commercial"))
    is_social = any(w in clari_lower for w in ("youtube", "facebook", "instagram", "tiktok", "twitter"))
    has_franchise_context = context_signal and context_signal != "none"

    if not (is_ad and has_franchise_context):
        return ""

    platform = "YouTube" if "youtube" in clari_lower else "social media"
    return (
        f"CELEBRITY IDENTIFICATION ALERT:\n"
        f"Platform = {platform} ad + franchise CONTEXT = '{context_signal}' detected.\n"
        f"Ads on {platform} frequently feature celebrities who are known FROM a franchise\n"
        f"but are promoting a DIFFERENT show/product in that same ad.\n"
        f"\n"
        f"Two interpretations to evaluate in parallel:\n"
        f"  A) CHARACTER interpretation: a girl who IS Spider-Man in a new '{context_signal}' franchise show\n"
        f"  B) CELEBRITY interpretation: an actress/person known FROM '{context_signal}' movies/shows,\n"
        f"     now appearing in a {platform} ad for a DIFFERENT show on Amazon/Netflix/streaming\n"
        f"\n"
        f"For interpretation B, required searches:\n"
        f"  - 'most famous actress {context_signal} movie 2025 2026' → who is the primary female face of this franchise?\n"
        f"  - '[actress name] new series 2026 Amazon Prime streaming'\n"
        f"  - '[actress name] {platform} ad 2026'\n"
        f"  - '{context_signal} actress [year] ad Amazon Prime YouTube'\n"
        f"\n"
        f"The H_COMPOSITE hypothesis (ad shows TWO different things) is also valid:\n"
        f"  - PRIMARY: actress from '{context_signal}' franchise\n"
        f"  - SUPPORTING (man with shotgun): a DIFFERENT show in the same ad compilation\n"
        f"\n"
    )

_ANSWER_TIMEOUT = 300  # 5 minutes


class BrainQuestionIn(BaseModel):
    run_id: str
    question: str
    options: list[str] = []
    uid: str = ""


class BrainAnswerIn(BaseModel):
    run_id: str
    answer: str


@router.post("/brain-question")
async def brain_question(body: BrainQuestionIn):
    """Called by the MCP ask_user tool. Pushes a WS event and waits for the user's answer."""
    from app.routers.v3.stream import push_event

    run_id = body.run_id
    uid = body.uid

    # Short-circuit: if this question was already answered by PreFlight, return the prior answer
    # without sending any WS event. The brain gets its answer immediately, no duplicate UI card.
    prior = _CLARIFICATION_MANIFEST.get(run_id, {}).get(body.question)
    if prior is not None:
        log.info("Manifest short-circuit for %s: Q=%s → A=%s", run_id, body.question[:50], prior[:50])
        return {"answer": prior}

    # Push question to frontend via WebSocket
    await push_event(uid, {
        "type": "brain.question",
        "run_id": run_id,
        "question": body.question,
        "options": body.options,
    })

    # Create event and wait for answer
    event = asyncio.Event()
    _pending_events[run_id] = event
    _pending_answers.pop(run_id, None)  # clear any stale answer

    try:
        await asyncio.wait_for(event.wait(), timeout=_ANSWER_TIMEOUT)
    except asyncio.TimeoutError:
        _pending_events.pop(run_id, None)
        raise HTTPException(status_code=408, detail="User did not answer in time")

    answer = _pending_answers.pop(run_id, "")
    _pending_events.pop(run_id, None)

    log.info("Brain Q&A for %s: Q=%s A=%s", run_id, body.question[:50], answer[:50])
    return {"answer": answer}


@router.post("/brain-answer")
async def brain_answer(body: BrainAnswerIn, user: dict = Depends(get_current_user)):
    """Called by the frontend when the user answers a brain question.

    Handles two cases:
    1. PreFlight gate (blocking=True): no brain was launched; enrich query and launch now.
    2. In-flight brain question: signal the waiting brain subprocess with the answer.
    """
    run_id = body.run_id

    # Case 1: PreFlight gate answer — check for follow-up or launch brain
    from app.routers.v3.agent import _PREFLIGHT_PENDING
    pending = _PREFLIGHT_PENDING.pop(run_id, None)
    if pending:
        import asyncio as _asyncio
        original_query = pending["original_query"]
        clarifications = pending.get("clarifications", [])
        clarifications.append(body.answer)
        # Store this answered question in the manifest so brain re-asks are short-circuited
        _CLARIFICATION_MANIFEST.setdefault(run_id, {})[pending["question"]] = body.answer
        # Decompose original query into primary / supporting / context signals.
        # Strategy:
        #   1. Strip leading content-type words ("new series", "ad", "show", "movie") — they describe
        #      the FORMAT, not the subject being identified.
        #   2. Person/character descriptor words (girl, man, woman, boy, guy, character) anchor the primary.
        #   3. Franchise/IP names become context.
        #   4. Everything after "where" / "who" / prop-describing clauses is supporting.
        import re as _re
        _FRANCHISE_WORDS = {
            "spiderman", "spider-man", "marvel", "dc", "netflix", "disney",
            "amazon", "hbo", "hulu", "apple", "peacock", "paramount", "sony",
        }
        _CONTENT_TYPE = {
            "new", "series", "show", "movie", "film", "ad", "advertisement",
            "commercial", "trailer", "video", "clip", "episode",
        }
        _PERSON_WORDS = {
            "girl", "woman", "female", "lady", "boy", "man", "guy", "male",
            "person", "character", "actor", "actress", "hero", "villain",
        }
        q_lower = original_query.lower()
        words   = _re.findall(r'\b\w[\w-]*\b', q_lower)

        # Extract context (franchise/platform) from anywhere in the query
        context_tokens = [w for w in words if w in _FRANCHISE_WORDS]
        context_signal = " ".join(context_tokens) if context_tokens else "none"

        # Primary = first person/character descriptor + its modifiers
        # Look for patterns like "girl", "man", "woman" and collect surrounding descriptors
        primary_parts: list[str] = []
        supporting_parts: list[str] = []
        in_supporting = False
        for w in words:
            if w in _CONTENT_TYPE or w in _FRANCHISE_WORDS:
                continue  # skip content type and franchise words
            if w in ("where", "who") or w in {"shotgun", "gun", "weapon", "sword", "knife"}:
                in_supporting = True
            if in_supporting:
                supporting_parts.append(w)
            elif w in _PERSON_WORDS or primary_parts:
                primary_parts.append(w)

        # Strip trailing prepositions from primary (e.g. "girl in" → "girl")
        _TRAILING_PREPS = {"in", "on", "at", "with", "of", "for", "to", "from"}
        while primary_parts and primary_parts[-1] in _TRAILING_PREPS:
            primary_parts.pop()
        primary_signal   = " ".join(primary_parts) if primary_parts else original_query
        supporting_signal = " ".join(supporting_parts) if supporting_parts else "none"

        clarification_lines = "\n".join(f"- {c}" for c in clarifications)
        enriched_query = (
            f"[IDENTIFICATION TASK — user does NOT know the title/name]\n"
            f"Observed: {original_query}\n"
            f"\n"
            f"SIGNAL DECOMPOSITION:\n"
            f"  PRIMARY (subject to identify): {primary_signal}\n"
            f"  SUPPORTING (scene details): {supporting_signal}\n"
            f"  CONTEXT (franchise/platform constraints): {context_signal}\n"
            f"\n"
            f"Clarifications from user:\n{clarification_lines}\n"
            f"\n"
            f"{_build_ad_celebrity_hint(clarifications, context_signal)}"
            f"HARD CONSTRAINTS:\n"
            f"1. The candidate's LEAD / TITLE character must match PRIMARY in its primary role — not merely appear in supporting cast.\n"
            f"2. PROHIBITED: delivering any candidate without ≥2 live sources confirming it matches PRIMARY in the lead role.\n"
            f"3. List all titles you seriously considered in `considered_alternatives` — even ones you ruled out.\n"
        )
        turn = pending.get("turn", 1)

        log.info("PreFlight answer turn %d for %s: %s", turn, run_id, body.answer[:50])

        # Check if a follow-up question is warranted (max 2 clarification turns)
        follow_up = None
        if turn < 2:
            answer_lower = body.answer.lower()
            # If user answered with a social/streaming platform, ask ad vs organic
            social_platforms = {"youtube", "facebook", "instagram", "tiktok", "twitter", "x"}
            streaming_platforms = {"netflix", "amazon", "prime", "disney", "hbo", "apple tv", "hulu", "peacock"}
            is_social = any(p in answer_lower for p in social_platforms)
            is_streaming = any(p in answer_lower for p in streaming_platforms)

            if is_social:
                follow_up = {
                    "question": "Was it an ad, or organic content (a video, post, or clip)?",
                    "options": ["An ad / advertisement", "A video / post / clip", "Not sure"],
                }
            elif is_streaming:
                follow_up = {
                    "question": "Was it a trailer for one specific title, or a general platform promo showing multiple titles?",
                    "options": ["Trailer for one specific title", "General promo / multiple titles shown", "Not sure"],
                }

        if follow_up:
            # Ask follow-up — store updated pending state, don't launch brain yet
            from app.routers.v3.stream import push_event as _push_event
            _PREFLIGHT_PENDING[run_id] = {
                **pending,
                "clarifications": clarifications,
                "turn": turn + 1,
                "question": follow_up["question"],
            }
            _asyncio.create_task(_push_event(pending["uid"], {
                "type": "brain.question",
                "run_id": run_id,
                "job_id": run_id,
                "question": follow_up["question"],
                "options": follow_up["options"],
                "preflight": True,
            }))
            return {"status": "ok", "mode": "preflight_followup"}

        # All clarifications gathered — launch brain with enriched query
        from app.routers.v3.agent import _run_is_research
        task = _asyncio.create_task(
            _run_is_research(
                run_id=run_id,
                uid=pending["uid"],
                pipeline_id=pending["pipeline_id"],
                query=enriched_query,
                past_research=pending.get("past_research"),
                session_id=pending.get("session_id"),
                session_context=pending.get("session_context", ""),
                preflight_result=None,
            )
        )
        task.add_done_callback(
            lambda t: log.error("PreFlight brain task failed: %s", t.exception()) if t.exception() else None
        )
        return {"status": "ok", "mode": "preflight_resumed"}

    # Case 2: Pipeline-layer confirmation gate answer (brain.confirm)
    from app.routers.v3.agent import _CONFIRM_PENDING, _run_is_research
    confirm = _CONFIRM_PENDING.pop(run_id, None)
    if confirm:
        import asyncio as _asyncio2
        answer_lower = body.answer.lower()

        if "yes" in answer_lower or "correct" in answer_lower:
            # Confirmed — complete the run by storing trail + pushing results
            _asyncio2.create_task(_deliver_confirmed_result(confirm))
            return {"status": "ok", "mode": "confirmed"}

        elif "not sure" in answer_lower or "unsure" in answer_lower or "maybe" in answer_lower:
            # Not sure — deliver with low-confidence framing
            result = confirm["result"]
            for f in result.get("findings", []):
                f["confidence"] = min(f.get("confidence", 50), 55)
                f["confidence_reason"] = "User unsure — treating as best guess, not confirmed"
            _asyncio2.create_task(_deliver_confirmed_result(confirm))
            return {"status": "ok", "mode": "unsure_delivered"}

        else:
            # "No, try another" — re-run brain with rejected candidates injected
            rejected = confirm.get("rejected", [])
            original_query = confirm["query"]
            rejected_block = "\n".join(f"- {r}" for r in rejected)

            # Extract clarifications and context from original query to rebuild celebrity hint
            _clari_lines = []
            _ctx = "none"
            for line in original_query.splitlines():
                if line.startswith("- ") and any(w in line.lower() for w in ("youtube","facebook","instagram","tiktok","ad","streaming","netflix")):
                    _clari_lines.append(line[2:])
                if "CONTEXT (franchise" in line:
                    _ctx = line.split(":")[-1].strip()
            _celebrity_hint = _build_ad_celebrity_hint(_clari_lines, _ctx)

            rerun_query = (
                f"{original_query}\n\n"
                f"REJECTED CANDIDATES (do not re-propose these):\n{rejected_block}\n"
                f"\n"
                f"{_celebrity_hint}"
                f"Search for a DIFFERENT candidate. Prioritise the CELEBRITY interpretation if not yet tried:\n"
                f"who is the most prominent actress/actor known FROM '{_ctx}' movies who might now appear in an ad for a different show?"
            )
            # Reuse the SAME run_id — reset status to queued so the existing tab stays
            # and shows the re-run's flow graph instead of erroring and opening a new tab.
            from app.routers.v3.db import execute as _exec
            _exec(
                """UPDATE pipeline_runs
                   SET status = 'queued',
                       finished_at = NULL,
                       error_message = NULL,
                       confirmation_data = NULL
                   WHERE id = %s""",
                (run_id,),
            )
            # Tell the frontend the run is starting over (resets Researching… state)
            from app.routers.v3.stream import push_event as _push_rerun
            _asyncio2.create_task(_push_rerun(confirm["uid"], {
                "type": "job.update",
                "job_id": run_id,
                "run_id": run_id,
                "status": "running",
                "message": "Searching for a different result…",
            }))
            from app.routers.v3.agent import _CONFIRM_PENDING as _CP
            _CP[f"rejected:{run_id}"] = rejected
            task = _asyncio2.create_task(
                _run_is_research(
                    run_id=run_id,
                    uid=confirm["uid"],
                    pipeline_id=confirm["pipeline_id"],
                    query=rerun_query,
                    past_research=confirm.get("past_research"),
                    session_id=confirm.get("session_id"),
                    session_context=confirm.get("session_context", ""),
                )
            )
            task.add_done_callback(
                lambda t: log.error("Confirm rerun failed: %s", t.exception()) if t.exception() else None
            )
            return {"status": "ok", "mode": "rerun", "run_id": run_id}

    # Case 3: In-flight brain question — signal the waiting brain subprocess
    event = _pending_events.get(run_id)
    if not event:
        raise HTTPException(status_code=404, detail="No pending question for this run")

    _pending_answers[run_id] = body.answer
    event.set()

    return {"status": "ok"}


async def _deliver_confirmed_result(confirm: dict) -> None:
    """Complete a held identification result after user confirms it."""
    import json as _json
    from app.routers.v3.agent import _run_is_research  # noqa — just for type ref
    from app.routers.v3.db import execute as _exec, fetch_one as _fetch_one
    from app.routers.v3.stream import push_event as _push
    from app.services.session_service import update_session_after_run

    run_id    = confirm["run_id"]
    uid       = confirm["uid"]
    result    = confirm["result"]
    session_id = confirm.get("session_id")
    query     = confirm["query"]

    try:
        if session_id:
            update_session_after_run(
                session_id=session_id,
                user_message=query,
                agent_summary=result.get("summary", ""),
                run_id=run_id,
                findings=result.get("findings", []),
                entity_type=result.get("entity_type", "unknown"),
                is_investigation=True,
            )
            _exec("UPDATE pipeline_runs SET session_id = %s WHERE id = %s", (session_id, run_id))

        trail_id = str(__import__("uuid").uuid4())
        _exec(
            """INSERT INTO research_trails
               (id, user_id, run_id, query, entity_type, trail, findings, tool_calls, suggested_pipeline)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (trail_id, uid, run_id, query,
             result.get("entity_type", "unknown"),
             _json.dumps(result.get("tree", {})),
             _json.dumps(result.get("findings", [])),
             result.get("tree", {}).get("total_branches", 0),
             _json.dumps(result.get("pipeline")) if result.get("pipeline") else None),
        )
        # Clear confirmation_data and mark succeeded — no longer pending
        _exec(
            "UPDATE pipeline_runs SET status = 'succeeded', finished_at = now(), confirmation_data = NULL WHERE id = %s",
            (run_id,),
        )

        await _push(uid, {
            "type": "job.update", "job_id": run_id, "run_id": run_id,
            "status": "succeeded", "result_count": len(result.get("findings", [])),
        })
        await _push(uid, {
            "type": "pipeline.run.complete", "run_id": run_id, "status": "succeeded",
        })
    except Exception as exc:
        log.error("_deliver_confirmed_result failed: %s", exc)
