"""Preflight router — MVP-M8.

Two endpoints:
  POST /v3/preflight         — classify query, suggest strategy/mode, return estimate + wallet snapshot
  POST /v3/preflight/confirm — place RU hold and return hold_id

TODO (post-MVP): replace stub classifier with a real LLM-backed or fine-tuned classifier.
TODO (post-MVP): surface top-3 strategy suggestions from classifier when catalog has >1 strategy.
"""
from __future__ import annotations

import logging
import uuid as _uuid_mod
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from pathlib import Path

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import fetch_one
from app.pipeline.catalogs.budget import (
    BudgetEnvelope,
    CAPABILITY_LEVELS,
    HYPOTHESIS_COUNT_LEVELS,
    SPEED_LEVELS,
    RESOURCE_LEVELS,
    DEPTH_LEVELS,
)
from app.pipeline.catalogs.loader import load_catalog
from app.pipeline.estimator import estimate_run
from app.pipeline import budget as wallet

# ---------------------------------------------------------------------------
# Mode + strategy catalogs — loaded once at import time
# ---------------------------------------------------------------------------

_MODES_DIR = Path(__file__).resolve().parent.parent.parent / "pipeline" / "catalogs" / "registries" / "modes"
_STRATEGIES_DIR = Path(__file__).resolve().parent.parent.parent / "pipeline" / "catalogs" / "registries" / "strategies"
_MODE_CATALOG = load_catalog("mode", _MODES_DIR)
_STRATEGY_CATALOG = load_catalog("strategy", _STRATEGIES_DIR)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v3/preflight", tags=["v3-preflight"])

# ---------------------------------------------------------------------------
# Strategy budget minimums (floor enforcement per strategy)
# ---------------------------------------------------------------------------

# media_identification requires at least "competing" hypotheses for accuracy
_STRATEGY_HYPOTHESIS_FLOOR: dict[str, str] = {
    "media_identification": "competing",
}

_HYPOTHESIS_ORDER = list(HYPOTHESIS_COUNT_LEVELS)  # single < paired < competing < adversarial < swarm


def _hypothesis_meets_floor(value: str, floor: str) -> bool:
    try:
        return _HYPOTHESIS_ORDER.index(value) >= _HYPOTHESIS_ORDER.index(floor)
    except ValueError:
        return True


# ---------------------------------------------------------------------------
# Classifier (stub)
# ---------------------------------------------------------------------------

# TODO (post-MVP): replace with a real classifier — LLM-backed or fine-tuned.
# MVP only has one strategy so this always returns media_identification.
_CELEBRITY_PATTERNS = {
    "advertisement", "ad", "commercial", "curling iron", "mole", "cheek",
    "asian girl", "actress", "actor", "celebrity", "kpop", "k-pop",
}


def _engine_v2_supported_strategies() -> set[str]:
    """Strategy IDs registered in app/pipeline/catalogs/registries/strategies.

    Computed lazily so we don't blow up at import time if the registry path
    isn't accessible. Cached for the lifetime of the process.
    """
    global _SUPPORTED_STRATEGIES_CACHE
    cache = globals().get("_SUPPORTED_STRATEGIES_CACHE")
    if cache is not None:
        return cache
    try:
        from pathlib import Path
        reg = Path(__file__).parent.parent.parent / "pipeline" / "catalogs" / "registries" / "strategies"
        names = {p.stem for p in reg.glob("*.py") if not p.stem.startswith("_")}
    except Exception:
        names = {"media_identification"}
    if not names:
        names = {"media_identification"}
    globals()["_SUPPORTED_STRATEGIES_CACHE"] = names
    return names


def _classify_intent(query: str) -> str:
    """Raw orchestrator classification — the brain's read of WHAT the user
    is asking about. Independent of which engine_v2 strategy will actually
    run. Used for the UI "Detected intent" badge so it matches the user's
    query even when engine_v2 hasn't yet registered a strategy for that
    intent (currently only media_identification is registered).
    """
    try:
        from app.pipeline.strategies.orchestrator import classify_query as _orch_classify
        cat = _orch_classify(query or "")
        alias = {"researcher": "person"}
        return alias.get(cat, cat) if cat else "media_identification"
    except Exception:
        return "media_identification"


# Known intent categories the user may select as an override. Kept in sync
# with _CATEGORY_SIGNALS keys in orchestrator.py — the orchestrator is the
# source of truth, this list is the *selectable* subset for the UI.
_KNOWN_INTENTS: list[tuple[str, str]] = [
    ("media_identification", "Media Identification"),
    ("person",               "Person"),
    ("lead",                 "Lead"),
    ("company",              "Company"),
    ("due_diligence",        "Due Diligence"),
    ("researcher",           "Researcher"),
    ("place",                "Place"),
    ("real_estate",          "Real Estate"),
    ("generation",           "Generation"),
    ("explanation",          "Explanation"),
    ("prediction",           "Prediction"),
    ("synthesis",            "Synthesis"),
]

_VALID_INTENT_IDS: set[str] = {i for i, _ in _KNOWN_INTENTS}


def _classify_query(query: str, mode: str | None = None) -> str:
    """Return a strategy_id for the given query, clamped to whatever
    engine_v2's catalog registry actually supports. ``mode`` (optional)
    feeds the mode-anchored step of the resolution chain — see
    ``_resolve_strategy``.
    """
    return _resolve_strategy(_classify_intent(query), mode)


# Lead-generation phrasing → infer leads_generation mode when the user didn't
# pick one explicitly. This is what lets a real-estate query (or the
# real-estate-leads template) reach the composite (real_estate, leads_generation)
# → real_estate_leads route, so the brain branches to contact + owner-background
# enrichment instead of listings-only. Kept to explicit lead phrasing to avoid
# steering ordinary searches into leads mode.
_LEADS_MODE_SIGNALS = (
    # Generic lead-gen phrasing
    "lead list", "leads list", "lead generation", "lead-gen", "leadgen",
    "generate leads", "find leads", "prospect list", "prospecting",
    "outreach list", "contact list", "build a list of contacts",
    "rental leads", "sales leads", "real estate leads", "real-estate leads",
    "property leads",
    # Real-estate lead-gen idioms (owner/agent outreach sourcing).
    # Kept specific (paired with "owner"/"agent"/"seller"/"landlord") so an
    # ordinary "what's the contact info for X" query doesn't flip to leads mode.
    "fsbo", "for sale by owner", "frbo", "for rent by owner",
    "motivated seller", "motivated sellers", "off-market owner",
    "owner contact", "owner contacts", "owners' contact", "agent contact",
    "landlord contact", "broker contact", "seller contact",
    "property owners", "list of owners", "find owners", "owner information",
    "skip trace", "skip-trace",
)


def _infer_mode(query: str) -> str | None:
    """Infer an optimization mode from query phrasing when none was supplied.

    Currently only detects leads_generation (the one mode with a composite
    strategy route). Returns None when no signal matches, preserving the
    existing default-mode behavior.
    """
    q = (query or "").lower()
    if any(sig in q for sig in _LEADS_MODE_SIGNALS):
        return "leads_generation"
    return None



# ---------------------------------------------------------------------------
# Composite strategy routing: (intent, mode) → strategy_id
#
# When a user picks a specific intent + mode combination that warrants a
# dedicated strategy (rather than the intent's default strategy), this map
# overrides step 1 of the resolution chain before the plain intent match.
# ---------------------------------------------------------------------------

_COMPOSITE_STRATEGY: dict[tuple[str, str], str] = {
    ("real_estate", "leads_generation"): "real_estate_leads",
}


def _resolve_strategy(intent: str, mode: str | None = None) -> str:
    """Map an intent (and optional mode) to an engine_v2-runnable strategy_id.

    Resolution chain (most specific → most permissive):

      0. **Composite map** — (intent, mode) pair matches a dedicated composite
         strategy (e.g. real_estate + leads_generation → real_estate_leads).
         Runs BEFORE the plain intent match so specialised strategies win.
      1. **Intent module** — a dedicated strategy module whose id matches
         ``intent`` (e.g. ``real_estate`` → ``real_estate.py``). Most precise.
      2. **Mode-anchored strategy** — the first id in the mode's
         ``strategy_suggestions`` list (catalog field on
         ``OptimizationMode``) that is actually registered. Lets a user who
         picks "academic_research" mode with a vague query still route to
         the academic strategy.
      3. **``generic_search``** — permissive single-phase retrieval floor.
         Prevents hard-fail on intents that have no dedicated module
         (regression-tested against the b0e457a4 run that died at the
         media_identification gather gate).
      4. **``media_identification``** — legacy fallback for the unlikely
         case where ``generic_search`` isn't registered yet.
      5. **First supported strategy** — absolute last resort.

    Shared by auto-detection and ``intent_override`` so both paths land in
    the same place.
    """
    supported = _engine_v2_supported_strategies()

    # 0. Composite map: (intent, mode) → dedicated strategy.
    if mode and (intent, mode) in _COMPOSITE_STRATEGY:
        cand = _COMPOSITE_STRATEGY[(intent, mode)]
        if cand in supported:
            return cand

    # 1. Dedicated intent module wins.
    if intent in supported:
        return intent

    # 2. Mode anchor — first registered strategy in the mode's suggestion list.
    if mode:
        mode_entry = _MODE_CATALOG.get(mode)
        if mode_entry is not None:
            for candidate in mode_entry.strategy_suggestions:
                if candidate in supported:
                    return candidate

    # 3. Permissive floor.
    if "generic_search" in supported:
        return "generic_search"

    # 4. Legacy floor (in case generic_search hasn't been deployed yet).
    if "media_identification" in supported:
        return "media_identification"

    # 5. Whatever's available.
    return next(iter(supported))


def _suggest_mode(strategy_id: str) -> str:
    """Suggest a mode based on the strategy's declared ``default_mode``.

    Each registered Strategy catalog entry carries a ``default_mode`` field
    (see app/pipeline/catalogs/builders/research_skeleton.py and
    app/pipeline/catalogs/registries/strategies/*.py). Falls back to
    ``quick_lookup`` if the strategy isn't registered.
    """
    entry = _STRATEGY_CATALOG.get(strategy_id)
    if entry is not None:
        return entry.default_mode
    return "quick_lookup"


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class DialsIn(BaseModel):
    capability: Optional[str] = "general"
    hypothesis_count: Optional[str] = "competing"
    depth: Optional[str] = "search"
    speed: Optional[str] = "normal"
    resource: Optional[str] = "medium"


class PreflightIn(BaseModel):
    query: str
    mode: Optional[str] = None
    dials: Optional[DialsIn] = None
    strategy: Optional[str] = None
    # User-supplied override for the auto-detected intent. When set, it
    # replaces _classify_intent() output and drives suggested_strategy /
    # suggested_mode. Validated against _VALID_INTENT_IDS.
    intent_override: Optional[str] = None


class IntentOut(BaseModel):
    id: str
    label: str


# ---------------------------------------------------------------------------
# Mode catalog response models
# ---------------------------------------------------------------------------

class ModeDialDefaultsOut(BaseModel):
    speed: str
    capability: str
    resource: str
    depth: str
    hypothesis_count: str


class ModeOut(BaseModel):
    id: str
    label: str
    description: str
    dial_defaults: ModeDialDefaultsOut


_MODE_META: dict[str, dict[str, str]] = {
    "quick_lookup": {
        "label": "Quick Lookup",
        "description": "Speed-first single-answer retrieval. Best for factual one-off questions.",
    },
    "leads_generation": {
        "label": "Leads Generation",
        "description": "Fast contact and lead extraction across multiple targets in parallel.",
    },
    "data_retrieval": {
        "label": "Data Retrieval",
        "description": "Structured-source data fetching (databases, TMDB, registries).",
    },
    "market_analysis": {
        "label": "Market Analysis",
        "description": "Comparative trend analysis with deep research across competing hypotheses.",
    },
    "investigation": {
        "label": "Investigation",
        "description": "Deep OSINT investigation with adversarial hypotheses and disconfirmation. Optimized against tunneling.",
    },
    "academic_research": {
        "label": "Academic Research",
        "description": "Exhaustive primary-source and citation-chain research. Maximum depth.",
    },
}


class EnvelopeOut(BaseModel):
    capability: str
    hypothesis_count: str
    depth: str
    speed: str
    resource: str
    mode: Optional[str]


class EstimateOut(BaseModel):
    estimated_ru: int
    estimated_ru_p90: int
    est_wall_time_s: int
    est_branches: int
    est_tool_calls: int


class WalletSnapshotOut(BaseModel):
    balance_ru: int
    held_ru: int
    available_ru: int
    after_run_projection: int


class PreflightOut(BaseModel):
    classifier_output: str
    suggested_strategy: str
    suggested_mode: str
    envelope: EnvelopeOut
    estimate: EstimateOut
    wallet: WalletSnapshotOut
    warnings: list[str]


class PreflightConfirmIn(BaseModel):
    run_id: Optional[str] = None
    query: str
    envelope: DialsIn
    strategy_id: str
    # engine_v2: when True, engine_v2 is launched in the background after hold succeeds
    start_run: bool = False


class PreflightConfirmOut(BaseModel):
    run_id: str
    hold_id: str
    held_ru: int


class PreflightConfirmErrorOut(BaseModel):
    error: str  # "insufficient_ru" | "below_floor" | "wallet_unavailable"
    details: str


# ---------------------------------------------------------------------------
# Wallet snapshot helper
# ---------------------------------------------------------------------------

def _get_wallet_snapshot(user_id: str) -> dict:
    """Return wallet row or synthesize a starter balance."""
    try:
        row = fetch_one(
            "SELECT balance_ru, held_ru FROM user_budget_wallets WHERE user_id = %s",
            (user_id,),
        )
        if row:
            balance = int(row["balance_ru"])
            held = int(row["held_ru"])
            return {"balance_ru": balance, "held_ru": held, "available_ru": balance - held}
    except Exception:
        pass
    # Auto-provision default: wallet will be created on first hold()
    return {"balance_ru": 10000, "held_ru": 0, "available_ru": 10000}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def valid_preflight_mode_ids() -> set[str]:
    """Set of mode ids served by GET [REDACTED:high-entropy-base64:23ch:hash=a944149d].

    Used by settings/default_mode to validate user-chosen defaults against the
    same mode catalog the picker actually renders.
    """
    return set(_MODE_META.keys())


@router.get("/modes", response_model=list[ModeOut])
def list_modes(user: dict = Depends(get_current_user)):
    """Return optimization modes with id, label, description, and dial defaults.

    Non-admin users see only modes visible at their effective scope
    (per #107 visibility settings). Admins always see the full catalog so
    they can author/check visibility without locking themselves out.
    """
    result: list[ModeOut] = []
    for mode_id, mode_entry in _MODE_CATALOG.items():
        meta = _MODE_META.get(mode_id, {"label": mode_id, "description": ""})
        defaults = mode_entry.dial_defaults
        result.append(
            ModeOut(
                id=mode_id,
                label=meta["label"],
                description=meta["description"],
                dial_defaults=ModeDialDefaultsOut(
                    speed=defaults.get("speed", "normal"),
                    capability=defaults.get("capability", "general"),
                    resource=defaults.get("resource", "medium"),
                    depth=defaults.get("depth", "search"),
                    hypothesis_count=defaults.get("hypothesis_count", "competing"),
                ),
            )
        )

    if user.get("is_admin") or user.get("role") == "admin":
        return result

    from app.routers.v3.visibility import filter_visible
    org_id = str(user["org_id"]) if user.get("org_id") else None
    return filter_visible("mode", [m.model_dump() for m in result], org_id)


@router.get("/intents", response_model=list[IntentOut])
def list_intents(_user: dict = Depends(get_current_user)):
    """Return the list of intent categories a user may select as an override
    for the auto-detected `classifier_output`. UI populates the intent
    dropdown from this endpoint.
    """
    return [IntentOut(id=i, label=label) for i, label in _KNOWN_INTENTS]


@router.post("", response_model=PreflightOut)
def preflight(body: PreflightIn, user: dict = Depends(get_current_user)):
    """Classify query, suggest strategy + mode, compute RU estimate, snapshot wallet."""
    uid = str(user["id"])

    # Validate intent_override up-front so an invalid value is a 422, not
    # a silent fallback to the auto-detected intent.
    if body.intent_override is not None and body.intent_override not in _VALID_INTENT_IDS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown intent_override '{body.intent_override}'. "
                   f"Valid values: {sorted(_VALID_INTENT_IDS)}",
        )

    # Classifier — override wins over auto-detection. Mode (if user-supplied)
    # feeds the resolution chain's mode-anchor step, so users picking a mode
    # with a vague query route through that mode's preferred strategy.
    # Mode: explicit user choice wins; otherwise infer from lead-gen phrasing so
    # a real-estate-leads query/template reaches the (real_estate, leads_generation)
    # → real_estate_leads composite route. Falls back to the strategy default.
    effective_mode = body.mode or _infer_mode(body.query)
    if body.intent_override:
        effective_intent = body.intent_override
        strategy_id = body.strategy or _resolve_strategy(effective_intent, effective_mode)
    else:
        effective_intent = _classify_intent(body.query)
        strategy_id = body.strategy or _classify_query(body.query, effective_mode)
    suggested_mode = effective_mode or _suggest_mode(strategy_id)

    # Resolve mode dial defaults — mode sets the baseline; explicit dials override per-dial
    mode_entry = _MODE_CATALOG.get(suggested_mode)
    mode_defaults = mode_entry.dial_defaults if mode_entry else {}

    # Build envelope from dials — explicit dials win over mode defaults, mode defaults win over
    # hardcoded fallbacks (normal/general/medium/search/competing)
    dials = body.dials or DialsIn()

    def _resolve(dial_val: Optional[str], mode_key: str, fallback: str, domain: tuple) -> str:
        if dial_val and dial_val in domain:
            return dial_val
        md = mode_defaults.get(mode_key)
        if md and md in domain:
            return md
        return fallback

    cap = _resolve(dials.capability, "capability", "general", CAPABILITY_LEVELS)
    depth = _resolve(dials.depth, "depth", "search", DEPTH_LEVELS)
    hyp = _resolve(dials.hypothesis_count, "hypothesis_count", "competing", HYPOTHESIS_COUNT_LEVELS)
    speed = _resolve(dials.speed, "speed", "normal", SPEED_LEVELS)
    resource = _resolve(dials.resource, "resource", "medium", RESOURCE_LEVELS)

    warnings: list[str] = []

    # Enforce strategy budget minimums
    floor = _STRATEGY_HYPOTHESIS_FLOOR.get(strategy_id)
    if floor and not _hypothesis_meets_floor(hyp, floor):
        old_hyp = hyp
        hyp = floor
        warnings.append(
            f"hypothesis_count upgraded from '{old_hyp}' to '{floor}': "
            f"strategy '{strategy_id}' requires at least '{floor}' hypotheses for accuracy."
        )

    envelope = BudgetEnvelope(
        capability=cap,
        hypothesis_count=hyp,
        depth=depth,
        speed=speed,
        resource=resource,
        mode=suggested_mode,
    )

    est = estimate_run(strategy_id, envelope)

    ws = _get_wallet_snapshot(uid)
    after_run = ws["available_ru"] - est.estimated_ru_p90

    return PreflightOut(
        # classifier_output = raw intent (what the user asked about, or
        # the user's explicit override); suggested_strategy = engine-runnable
        # strategy (clamped to registry).
        classifier_output=effective_intent,
        suggested_strategy=strategy_id,
        suggested_mode=suggested_mode,
        envelope=EnvelopeOut(
            capability=envelope.capability,
            hypothesis_count=envelope.hypothesis_count,
            depth=envelope.depth,
            speed=envelope.speed,
            resource=envelope.resource,
            mode=envelope.mode,
        ),
        estimate=EstimateOut(
            estimated_ru=est.estimated_ru,
            estimated_ru_p90=est.estimated_ru_p90,
            est_wall_time_s=est.est_wall_time_s,
            est_branches=est.est_branches,
            est_tool_calls=est.est_tool_calls,
        ),
        wallet=WalletSnapshotOut(
            balance_ru=ws["balance_ru"],
            held_ru=ws["held_ru"],
            available_ru=ws["available_ru"],
            after_run_projection=after_run,
        ),
        warnings=warnings,
    )


@router.post("/confirm")
async def preflight_confirm(body: PreflightConfirmIn, user: dict = Depends(get_current_user)):
    """Place a wallet hold for the confirmed run.

    Returns PreflightConfirmOut on success, or HTTP 402 with error detail on hold failure.
    """
    uid = str(user["id"])
    run_id = body.run_id or str(_uuid_mod.uuid4())
    idempotency_key = f"preflight_confirm__{uid}__{run_id}"

    # Validate and apply strategy floor to envelope
    hyp = body.envelope.hypothesis_count or "competing"
    cap = body.envelope.capability or "general"
    depth = body.envelope.depth or "search"
    speed = body.envelope.speed or "normal"
    resource = body.envelope.resource or "medium"

    floor = _STRATEGY_HYPOTHESIS_FLOOR.get(body.strategy_id)
    if floor and not _hypothesis_meets_floor(hyp, floor):
        hyp = floor

    try:
        envelope = BudgetEnvelope(
            capability=cap if cap in CAPABILITY_LEVELS else "general",
            hypothesis_count=hyp,
            depth=depth if depth in DEPTH_LEVELS else "search",
            speed=speed if speed in SPEED_LEVELS else "normal",
            resource=resource if resource in RESOURCE_LEVELS else "medium",
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    est = estimate_run(body.strategy_id, envelope)
    p90 = est.estimated_ru_p90

    result = wallet.hold(uid, run_id, p90, idempotency_key)

    if not result.ok:
        reason = result.reason or "insufficient"
        if reason == "below_floor":
            error_key = "below_floor"
            detail = "Wallet balance would drop below your safety floor. Lower your floor or top up."
        elif reason == "wallet_unavailable":
            error_key = "wallet_unavailable"
            detail = "Wallet service unavailable. Please try again."
        else:
            error_key = "insufficient_ru"
            detail = f"Insufficient RU. This run requires {p90} RU (p90). Top up your wallet to proceed."

        raise HTTPException(
            status_code=402,
            detail={"error": error_key, "details": detail},
        )

    confirm_out = PreflightConfirmOut(
        run_id=run_id,
        hold_id=result.hold_id,
        held_ru=result.held_ru,
    )

    # engine_v2 launch — kick off background pipeline run after a successful hold.
    # Only fires when the caller explicitly sets start_run=True (the frontend
    # sets this on the ?engine=v2 path after preflight confirm).
    if body.start_run:
        # Pre-run admission gate — same checks as POST /v3/agent/message.
        # The wallet hold is already in place at this point; if rejected,
        # the caller should NOT consume the hold (returned hold_id remains
        # valid for a retry once capacity opens).
        from app.services.admission_gate import check_admission
        decision = check_admission(uid)
        if not decision.admitted:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "admission_rejected",
                    "reason": decision.reason,
                    "message": decision.message,
                    "retry_after_seconds": decision.retry_after_seconds,
                    "global_active": decision.global_active,
                    "user_active": decision.user_active,
                    "user_runs_today": decision.user_runs_today,
                    "hold_id": result.hold_id,
                },
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )
        try:
            import asyncio as _asyncio
            from app.pipeline.engine_v2 import run_engine_v2
            from app.routers.v3.stream import push_event
            from app.routers.v3.db import execute as _db_execute

            # Synchronously insert pipeline_runs row BEFORE returning the
            # response. This closes a race where the frontend's GET
            # /v3/pipelines/runs/{runId} fires before engine_v2's async
            # INSERT lands, and the user sees a "Run not found" page.
            try:
                _db_execute(
                    """INSERT INTO pipeline_runs (id, pipeline_id, user_id, status, trigger_type, query)
                       VALUES (%s, '00000000-0000-4000-8000-000000000001', %s, 'running', 'agent', %s)
                       ON CONFLICT (id) DO NOTHING""",
                    (run_id, uid, body.query),
                )
            except Exception as exc:
                log.warning("preflight: pipeline_runs pre-insert failed (non-fatal): %s", exc)

            _envelope = BudgetEnvelope(
                capability=cap if cap in CAPABILITY_LEVELS else "general",
                hypothesis_count=hyp,
                depth=depth if depth in DEPTH_LEVELS else "search",
                speed=speed if speed in SPEED_LEVELS else "normal",
                resource=resource if resource in RESOURCE_LEVELS else "medium",
            )

            async def _emit_event(payload: dict) -> None:
                await push_event(uid, payload)

            async def _run_engine() -> None:
                try:
                    await run_engine_v2(
                        user_id=uid,
                        run_id=run_id,
                        hold_id=result.hold_id,
                        hold_amount_ru=result.held_ru,
                        query=body.query,
                        envelope=_envelope,
                        strategy_id=body.strategy_id,
                        event_emit=_emit_event,
                    )
                except Exception as exc:
                    log.error("engine_v2 background run failed: %s", exc)
                    await push_event(uid, {
                        "type": "job.failed",
                        "run_id": run_id,
                        "job_id": run_id,
                        "status": "failed",
                        "message": f"engine_v2 failed: {str(exc)[:200]}",
                    })

            task = _asyncio.create_task(_run_engine())
            task.add_done_callback(
                lambda t: log.error("engine_v2 task unhandled: %s", t.exception())
                if t.exception() else None
            )
        except Exception as exc:
            log.error("engine_v2 launch failed: %s", exc)

    return confirm_out
