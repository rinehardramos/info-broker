from __future__ import annotations

import json
import logging
import os
import time
import uuid

import requests
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one, get_conn
from app.routers.v3.models import (
    ApifyConfigIn,
    ApifyConfigOut,
    ApifyRunConfigOut,
    ApifyRunIn,
    ApifyRunOut,
    ApifyRunStatusOut,
    LinkedInProfileGradeIn,
    LinkedInProfileOut,
)

router = APIRouter(prefix="/v3/apify", tags=["v3-apify"])
log = logging.getLogger(__name__)

_BASE_URL = os.getenv("APIFY_BASE_URL", "https://api.apify.com/v2")
_POLL_INTERVAL = 10   # seconds between status polls
_MAX_POLL_TIME = 600  # 10 minutes max

_TERMINAL = {"succeeded", "failed", "ingest_failed"}
_MASKED = "\u2022" * 8


def _get_setting(key: str) -> str | None:
    row = fetch_one("SELECT value FROM core_settings WHERE key = %s", (key,))
    return row["value"] if row else None


def _upsert_setting(key: str, value: str, is_secret: bool = False) -> None:
    execute(
        """
        INSERT INTO core_settings (key, value, is_secret)
        VALUES (%s, %s, %s)
        ON CONFLICT (key) DO UPDATE
        SET value = EXCLUDED.value, is_secret = EXCLUDED.is_secret, updated_at = now()
        """,
        (key, value, is_secret),
    )


def _get_run_config(user_id: str) -> ApifyRunConfigOut:
    row = fetch_one(
        """SELECT job_titles, locations, max_items, scraper_mode,
                  auto_query_segmentation, auto_query_segmentation_levels,
                  auto_query_segmentation_countries, recently_changed_jobs,
                  recently_posted_on_linkedin
           FROM apify_run_configs WHERE user_id = %s""",
        (user_id,),
    )
    if row:
        return ApifyRunConfigOut(**row)
    return ApifyRunConfigOut(
        job_titles=[], locations=[], max_items=300, scraper_mode="Full + email search",
        auto_query_segmentation=False,
        auto_query_segmentation_levels=["country", "industry", "seniority_level"],
        auto_query_segmentation_countries=[],
        recently_changed_jobs=False,
        recently_posted_on_linkedin=False,
    )


@router.get("/config", response_model=ApifyConfigOut)
def get_config(user: dict = Depends(get_current_user)):
    raw_key = _get_setting("apify_api_key")
    return ApifyConfigOut(
        api_key=None if raw_key is None else _MASKED,
        actor_id=_get_setting("apify_actor_id"),
        run_config=_get_run_config(str(user["id"])),
    )


@router.post("/config", response_model=ApifyConfigOut)
def save_config(body: ApifyConfigIn, user: dict = Depends(get_current_user)):
    if body.api_key is not None:
        _upsert_setting("apify_api_key", body.api_key, is_secret=True)
    if body.actor_id is not None:
        _upsert_setting("apify_actor_id", body.actor_id)

    run_config_fields = [
        body.job_titles, body.locations, body.max_items, body.scraper_mode,
        body.auto_query_segmentation, body.auto_query_segmentation_levels,
        body.auto_query_segmentation_countries, body.recently_changed_jobs,
        body.recently_posted_on_linkedin,
    ]
    if any(f is not None for f in run_config_fields):
        e = _get_run_config(str(user["id"]))
        execute(
            """
            INSERT INTO apify_run_configs
                (user_id, job_titles, locations, max_items, scraper_mode,
                 auto_query_segmentation, auto_query_segmentation_levels,
                 auto_query_segmentation_countries, recently_changed_jobs,
                 recently_posted_on_linkedin)
            VALUES (%s, %s::jsonb, %s::jsonb, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
            ON CONFLICT (user_id) DO UPDATE
            SET job_titles                        = EXCLUDED.job_titles,
                locations                         = EXCLUDED.locations,
                max_items                         = EXCLUDED.max_items,
                scraper_mode                      = EXCLUDED.scraper_mode,
                auto_query_segmentation           = EXCLUDED.auto_query_segmentation,
                auto_query_segmentation_levels    = EXCLUDED.auto_query_segmentation_levels,
                auto_query_segmentation_countries = EXCLUDED.auto_query_segmentation_countries,
                recently_changed_jobs             = EXCLUDED.recently_changed_jobs,
                recently_posted_on_linkedin       = EXCLUDED.recently_posted_on_linkedin,
                updated_at                        = now()
            """,
            (
                str(user["id"]),
                json.dumps(body.job_titles if body.job_titles is not None else e.job_titles),
                json.dumps(body.locations if body.locations is not None else e.locations),
                body.max_items if body.max_items is not None else e.max_items,
                body.scraper_mode if body.scraper_mode is not None else e.scraper_mode,
                body.auto_query_segmentation if body.auto_query_segmentation is not None else e.auto_query_segmentation,
                json.dumps(body.auto_query_segmentation_levels if body.auto_query_segmentation_levels is not None else e.auto_query_segmentation_levels),
                json.dumps(body.auto_query_segmentation_countries if body.auto_query_segmentation_countries is not None else e.auto_query_segmentation_countries),
                body.recently_changed_jobs if body.recently_changed_jobs is not None else e.recently_changed_jobs,
                body.recently_posted_on_linkedin if body.recently_posted_on_linkedin is not None else e.recently_posted_on_linkedin,
            ),
        )
    return get_config(user=user)


@router.post("/run", response_model=ApifyRunOut, status_code=202)
def start_run(background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    api_key = _get_setting("apify_api_key")
    actor_id = _get_setting("apify_actor_id")
    if not api_key or not actor_id:
        raise HTTPException(status_code=400, detail="Apify API key and actor ID must be configured.")

    config = _get_run_config(str(user["id"]))
    actor_input = {
        "currentJobTitles": config.job_titles,
        "locations": config.locations,
        "maxItems": config.max_items,
        "scraperMode": config.scraper_mode,
        "autoQuerySegmentation": config.auto_query_segmentation,
        "autoQuerySegmentationLevels": config.auto_query_segmentation_levels,
        "autoQuerySegmentationTargetCountries": config.auto_query_segmentation_countries,
        "recentlyChangedJobs": config.recently_changed_jobs,
        "recentlyPostedOnLinkedin": config.recently_posted_on_linkedin,
    }

    row = fetch_one(
        "INSERT INTO apify_runs (id, user_id, status) VALUES (%s, %s, 'queued') RETURNING *",
        (str(uuid.uuid4()), str(user["id"])),
    )
    background_tasks.add_task(_run_and_ingest, row["id"], api_key, actor_id, actor_input)
    return ApifyRunOut(**row)


def _run_and_ingest(run_id: str, api_key: str, actor_id: str, actor_input: dict) -> None:
    """Background task: start Apify actor run, poll until done, ingest dataset."""
    # 1. Start the actor run
    try:
        resp = requests.post(
            f"{_BASE_URL}/acts/{actor_id}/runs",
            params={"token": api_key},
            json=actor_input,
            timeout=30,
        )
        resp.raise_for_status()
        apify_run_id = resp.json()["data"]["id"]
    except Exception as exc:
        log.error("Failed to start Apify run for %s: %s", run_id, exc)
        execute(
            "UPDATE apify_runs SET status = 'failed', finished_at = now() WHERE id = %s",
            (run_id,),
        )
        return

    execute(
        "UPDATE apify_runs SET status = 'running', apify_run_id = %s WHERE id = %s",
        (apify_run_id, run_id),
    )

    # 2. Poll until terminal
    dataset_id = None
    deadline = time.time() + _MAX_POLL_TIME
    while time.time() < deadline:
        time.sleep(_POLL_INTERVAL)
        try:
            resp = requests.get(
                f"{_BASE_URL}/actor-runs/{apify_run_id}",
                params={"token": api_key},
                timeout=30,
            )
            resp.raise_for_status()
            run_data = resp.json()["data"]
            status = run_data.get("status")
            if status == "SUCCEEDED":
                dataset_id = run_data.get("defaultDatasetId")
                break
            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                log.warning("Apify run %s ended with status %s", apify_run_id, status)
                execute(
                    "UPDATE apify_runs SET status = 'failed', finished_at = now() WHERE id = %s",
                    (run_id,),
                )
                return
        except Exception as exc:
            log.warning("Poll error for run %s: %s", run_id, exc)

    if not dataset_id:
        log.error("Apify run %s timed out after %ds", apify_run_id, _MAX_POLL_TIME)
        execute(
            "UPDATE apify_runs SET status = 'failed', finished_at = now() WHERE id = %s",
            (run_id,),
        )
        return

    # 3. Ingest the dataset
    _ingest_dataset(run_id, api_key, dataset_id)


def _ingest_dataset(run_id: str, api_key: str, dataset_id: str) -> None:
    """Fetch Apify dataset items and write profiles to Postgres + Qdrant."""
    execute("UPDATE apify_runs SET status = 'ingesting' WHERE id = %s", (run_id,))
    try:
        resp = requests.get(
            f"{_BASE_URL}/datasets/{dataset_id}/items",
            params={"token": api_key},
            timeout=120,
        )
        resp.raise_for_status()
        profiles = resp.json()
    except Exception as exc:
        log.error("Dataset fetch failed for run %s: %s", run_id, exc)
        execute(
            "UPDATE apify_runs SET status = 'ingest_failed', finished_at = now() WHERE id = %s",
            (run_id,),
        )
        return

    if not isinstance(profiles, list):
        execute(
            "UPDATE apify_runs SET status = 'ingest_failed', finished_at = now() WHERE id = %s",
            (run_id,),
        )
        return

    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams
    from llm_providers import embed_text

    qdrant = QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )
    collection = "linkedin_profiles"
    if not qdrant.collection_exists(collection_name=collection):
        qdrant.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )

    count = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for profile in profiles:
                if not isinstance(profile, dict):
                    continue
                profile_id = str(profile.get("id") or "")[:128]
                if not profile_id:
                    continue
                first_name = str(profile.get("firstName") or "")[:256]
                last_name  = str(profile.get("lastName") or "")[:256]
                headline   = str(profile.get("headline") or "")[:1024]
                about      = str(profile.get("about") or "")[:8000]
                try:
                    cur.execute(
                        """
                        INSERT INTO linkedin_profiles
                            (id, first_name, last_name, headline, about, raw_data)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        (profile_id, first_name, last_name, headline, about, json.dumps(profile)),
                    )
                    text = f"{first_name} {last_name}\nHeadline: {headline}\nAbout: {about}"[:4000]
                    qdrant.upsert(
                        collection_name=collection,
                        points=[PointStruct(
                            id=str(uuid.uuid5(uuid.NAMESPACE_DNS, profile_id)),
                            vector=embed_text(text),
                            payload={
                                "apify_id": profile_id,
                                "first_name": first_name,
                                "last_name": last_name,
                                "headline": headline,
                            },
                        )],
                    )
                    count += 1
                except Exception as exc:
                    log.warning("Profile %s ingest error: %s", profile_id, exc)

    execute(
        "UPDATE apify_runs SET status = 'succeeded', item_count = %s, finished_at = now() WHERE id = %s",
        (count, run_id),
    )
    log.info("Ingest complete for run %s: %d profiles", run_id, count)


@router.get("/runs", response_model=list[ApifyRunOut])
def list_runs(user: dict = Depends(get_current_user)):
    rows = fetch_all(
        "SELECT * FROM apify_runs WHERE user_id = %s ORDER BY started_at DESC",
        (str(user["id"]),),
    )
    return [ApifyRunOut(**r) for r in rows]


@router.get("/profiles", response_model=list[LinkedInProfileOut])
def list_profiles(
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user),
):
    rows = fetch_all(
        """
        SELECT p.id, p.first_name, p.last_name, p.headline, p.about, g.grade
        FROM linkedin_profiles p
        LEFT JOIN linkedin_profile_grades g
               ON g.profile_id = p.id AND g.user_id = %s
        ORDER BY p.id
        LIMIT %s OFFSET %s
        """,
        (str(user["id"]), limit, offset),
    )
    return [LinkedInProfileOut(**r) for r in rows]


@router.post("/profiles/{profile_id}/grade")
def grade_profile(
    profile_id: str,
    body: LinkedInProfileGradeIn,
    user: dict = Depends(get_current_user),
):
    row = fetch_one("SELECT id FROM linkedin_profiles WHERE id = %s", (profile_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    execute(
        """
        INSERT INTO linkedin_profile_grades (profile_id, user_id, grade)
        VALUES (%s, %s, %s)
        ON CONFLICT (profile_id, user_id)
        DO UPDATE SET grade = EXCLUDED.grade, updated_at = now()
        """,
        (profile_id, str(user["id"]), body.grade),
    )
    return {"ok": True}


@router.get("/runs/{run_id}/status", response_model=ApifyRunStatusOut)
def get_run_status(run_id: str, user: dict = Depends(get_current_user)):
    row = fetch_one(
        "SELECT * FROM apify_runs WHERE id = %s AND user_id = %s",
        (run_id, str(user["id"])),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    return ApifyRunStatusOut(
        status=row["status"],
        item_count=row["item_count"],
        apify_run_id=row["apify_run_id"],
    )
