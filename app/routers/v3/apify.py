from __future__ import annotations

import json
import logging
import os
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
)

router = APIRouter(prefix="/v3/apify", tags=["v3-apify"])
log = logging.getLogger(__name__)

# Set APIFY_BASE_URL in the environment (see docker-compose.yml)
_APIFY_BASE = os.getenv("APIFY_BASE_URL", "")

_APIFY_STATUS_MAP = {
    "READY": "queued",
    "RUNNING": "running",
    "SUCCEEDED": "ingesting",
    "FAILED": "failed",
    "TIMED-OUT": "failed",
    "ABORTED": "failed",
}

_TERMINAL = {"succeeded", "failed", "ingest_failed"}
_MASKED = "\u2022" * 8


def _apify_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + api_key}


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
        "SELECT job_titles, locations, max_items, scraper_mode FROM apify_run_configs WHERE user_id = %s",
        (user_id,),
    )
    if row:
        return ApifyRunConfigOut(**row)
    return ApifyRunConfigOut(
        job_titles=[], locations=[], max_items=300, scraper_mode="Full + email search"
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

    if any(f is not None for f in [body.job_titles, body.locations, body.max_items, body.scraper_mode]):
        existing = _get_run_config(str(user["id"]))
        execute(
            """
            INSERT INTO apify_run_configs (user_id, job_titles, locations, max_items, scraper_mode)
            VALUES (%s, %s::jsonb, %s::jsonb, %s, %s)
            ON CONFLICT (user_id) DO UPDATE
            SET job_titles   = EXCLUDED.job_titles,
                locations    = EXCLUDED.locations,
                max_items    = EXCLUDED.max_items,
                scraper_mode = EXCLUDED.scraper_mode,
                updated_at   = now()
            """,
            (
                str(user["id"]),
                json.dumps(body.job_titles if body.job_titles is not None else existing.job_titles),
                json.dumps(body.locations if body.locations is not None else existing.locations),
                body.max_items if body.max_items is not None else existing.max_items,
                body.scraper_mode if body.scraper_mode is not None else existing.scraper_mode,
            ),
        )
    return get_config(user=user)


@router.post("/run", response_model=ApifyRunOut, status_code=202)
def start_run(body: ApifyRunIn, user: dict = Depends(get_current_user)):
    api_key = _get_setting("apify_api_key")
    actor_id = _get_setting("apify_actor_id")
    if not api_key or not actor_id:
        raise HTTPException(
            status_code=400,
            detail="Apify API key and actor ID must be configured before running.",
        )

    run_input = {
        "autoQuerySegmentation": False,
        "currentJobTitles": body.job_titles,
        "locations": body.locations,
        "maxItems": body.max_items,
        "profileScraperMode": body.scraper_mode,
        "recentlyChangedJobs": False,
        "recentlyPostedOnLinkedIn": False,
    }
    try:
        resp = requests.post(
            f"{_APIFY_BASE}/acts/{actor_id}/runs",
            headers=_apify_headers(api_key),
            json={"runInput": run_input},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Apify API error: {exc}")

    apify_run_id = resp.json().get("data", {}).get("id")
    row = fetch_one(
        "INSERT INTO apify_runs (id, user_id, apify_run_id, status) VALUES (%s, %s, %s, 'queued') RETURNING *",
        (str(uuid.uuid4()), str(user["id"]), apify_run_id),
    )
    return ApifyRunOut(**row)


def _ingest_dataset(run_id: str, dataset_id: str | None, api_key: str) -> None:
    """Background task: fetch Apify dataset and write to Postgres + Qdrant."""
    if not dataset_id:
        execute(
            "UPDATE apify_runs SET status = 'ingest_failed', finished_at = now() WHERE id = %s",
            (run_id,),
        )
        log.warning("No dataset_id for run %s", run_id)
        return

    try:
        resp = requests.get(
            f"{_APIFY_BASE}/datasets/{dataset_id}/items",
            headers={**_apify_headers(api_key), "Accept": "application/json"},
            params={"format": "json"},
            timeout=60,
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


@router.get("/runs/{run_id}/status", response_model=ApifyRunStatusOut)
def get_run_status(
    run_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    row = fetch_one(
        "SELECT * FROM apify_runs WHERE id = %s AND user_id = %s",
        (run_id, str(user["id"])),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")

    if row["status"] in _TERMINAL or row["status"] == "ingesting":
        return ApifyRunStatusOut(
            status=row["status"],
            item_count=row["item_count"],
            apify_run_id=row["apify_run_id"],
        )

    api_key = _get_setting("apify_api_key")
    try:
        resp = requests.get(
            f"{_APIFY_BASE}/actor-runs/{row['apify_run_id']}",
            headers=_apify_headers(api_key or ""),
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Apify poll failed for run %s: %s", run_id, exc)
        return ApifyRunStatusOut(
            status=row["status"],
            item_count=row["item_count"],
            apify_run_id=row["apify_run_id"],
        )

    apify_data = resp.json().get("data", {})
    new_status = _APIFY_STATUS_MAP.get(apify_data.get("status", ""), row["status"])

    if new_status != row["status"]:
        if new_status == "ingesting":
            execute("UPDATE apify_runs SET status = 'ingesting' WHERE id = %s", (run_id,))
            background_tasks.add_task(
                _ingest_dataset, run_id, apify_data.get("defaultDatasetId"), api_key or ""
            )
        elif new_status == "failed":
            execute(
                "UPDATE apify_runs SET status = 'failed', finished_at = now() WHERE id = %s",
                (run_id,),
            )
        else:
            execute("UPDATE apify_runs SET status = %s WHERE id = %s", (new_status, run_id))

    return ApifyRunStatusOut(
        status=new_status,
        item_count=row["item_count"],
        apify_run_id=row["apify_run_id"],
    )
