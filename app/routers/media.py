"""/v1/* media endpoints used by playgen-dj for script generation.

Each handler:
  - is rate-limited via slowapi (per-API-key bucket)
  - is gated by ``require_api_key``
  - reads/writes a per-endpoint TTL cache before/after touching upstreams
  - maps adapter exceptions to consistent HTTP error codes
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import shutil
import uuid

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status

from app.adapters.audio import (
    AudioSourceUnavailable,
    s3_config_from_env,
    s3_object_exists,
    s3_song_key,
    source_audio,
    upload_to_s3,
)
from app.adapters.jokes import JokeUnavailable, fetch_joke
from app.adapters.music import SongEnrichmentUnavailable, fetch_song_enrichment
from app.adapters.news import NewsUnavailable, fetch_news
from app.adapters.weather import WeatherUnavailable, fetch_weather
from app.deps import require_api_key
from app.lib.cache import TTLCache, cache_key
from app.lib.rate_limit import limiter
from app.schemas_media import (
    JokeResponse,
    JokeStyle,
    NewsResponse,
    NewsScope,
    NewsTopic,
    PlaylistSourceRequest,
    PlaylistSourceResult,
    SourcedSong,
    SongEnrichmentResponse,
    SongSourceRequest,
    SongSourceResult,
    WeatherResponse,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["media"])

# 10 min weather TTL — keeps repeat DJ jobs from hammering OpenWeatherMap.
_weather_cache: TTLCache[WeatherResponse] = TTLCache(default_ttl=600, max_entries=512)
# 15 min news TTL — fresh enough for "current events" while still cutting load.
_news_cache: TTLCache[NewsResponse] = TTLCache(default_ttl=900, max_entries=512)
# 7 day song-enrichment TTL — recording metadata is effectively immutable.
_song_cache: TTLCache[SongEnrichmentResponse] = TTLCache(
    default_ttl=7 * 24 * 3600, max_entries=4096
)


@router.get(
    "/weather",
    response_model=WeatherResponse,
    summary="Current weather for a city or lat/lon",
)
@limiter.limit("60/minute")
def get_weather(
    request: Request,
    response: Response,
    city: str | None = Query(default=None, max_length=100),
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
    _api_key: str = Depends(require_api_key),
) -> WeatherResponse:
    if not city and (lat is None or lon is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="city or lat+lon required",
        )

    key = cache_key("weather", city, country_code, lat, lon)
    cached = _weather_cache.get(key)
    if cached is not None:
        return cached

    try:
        result = fetch_weather(
            city=city, country_code=country_code, lat=lat, lon=lon
        )
    except WeatherUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"weather unavailable: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("weather adapter crashed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="weather provider error",
        ) from exc

    _weather_cache.set(key, result)
    return result


@router.get(
    "/news",
    response_model=NewsResponse,
    summary="Top news headlines, optionally scoped + filtered by topic",
)
@limiter.limit("60/minute")
def get_news(
    request: Request,
    response: Response,
    scope: NewsScope = Query(default="global"),
    topic: NewsTopic = Query(default="any"),
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
    query: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=10, ge=1, le=50),
    _api_key: str = Depends(require_api_key),
) -> NewsResponse:
    if scope in ("country", "local") and not country_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="country_code required when scope is 'country' or 'local'",
        )

    key = cache_key("news", scope, topic, country_code, query, limit)
    cached = _news_cache.get(key)
    if cached is not None:
        return cached

    try:
        result = fetch_news(
            scope=scope,
            topic=topic,
            country_code=country_code,
            query=query,
            limit=limit,
        )
    except NewsUnavailable as exc:
        # The bundled fallback should make this practically unreachable, but
        # keep the explicit branch for forensics.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"news unavailable: {exc}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("news adapter crashed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="news provider error",
        ) from exc

    _news_cache.set(key, result)
    return result


@router.get(
    "/songs/enrich",
    response_model=SongEnrichmentResponse,
    summary="Enrich a (title, artist) pair with album/year/genre/trivia from MusicBrainz",
)
@limiter.limit("120/minute")
def get_song_enrichment(
    request: Request,
    response: Response,
    title: str = Query(..., max_length=200),
    artist: str = Query(..., max_length=200),
    _api_key: str = Depends(require_api_key),
) -> SongEnrichmentResponse:
    key = cache_key("song", title, artist)
    cached = _song_cache.get(key)
    if cached is not None:
        return cached

    try:
        result = fetch_song_enrichment(title=title, artist=artist)
    except SongEnrichmentUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no enrichment found: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("song enrichment crashed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="enrichment provider error",
        ) from exc

    _song_cache.set(key, result)
    return result


@router.get(
    "/jokes",
    response_model=JokeResponse,
    summary="A single joke, optionally styled and safety-filtered",
)
@limiter.limit("60/minute")
def get_joke(
    request: Request,
    response: Response,
    style: JokeStyle = Query(default="any"),
    safe: bool = Query(default=True),
    _api_key: str = Depends(require_api_key),
) -> JokeResponse:
    # No cache: jokes must be fresh + varied. Variety > load reduction here.
    try:
        return fetch_joke(style=style, safe=safe)
    except JokeUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"joke unavailable: {exc}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("joke adapter crashed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="joke provider error",
        ) from exc


# ── audio sourcing ─────────────────────────────────────────────────────────────


async def _process_song_source(job_id: str, request: SongSourceRequest) -> None:
    """Background task: download audio, optionally upload to S3, POST callback."""
    result = SongSourceResult(job_id=job_id, status="failed")
    try:
        audio = await source_audio(title=request.title, artist=request.artist)
        object_key: str | None = None
        if request.upload_target is not None:
            t = request.upload_target
            object_key = await upload_to_s3(
                file_path=audio["path"],
                bucket=t.bucket,
                key=t.key,
                endpoint=t.endpoint,
                access_key=t.access_key_id,
                secret_key=t.secret_access_key,
                region=t.region,
            )
        result = SongSourceResult(
            job_id=job_id,
            status="completed",
            duration_sec=audio["duration_sec"],
            size_bytes=audio["size_bytes"],
            format=audio["format"],
            object_key=object_key,
        )
        log.info("song_source job=%s completed title=%r artist=%r", job_id, request.title, request.artist)
    except (AudioSourceUnavailable, ImportError, RuntimeError, ValueError) as exc:
        result = SongSourceResult(job_id=job_id, status="failed", error=str(exc))
        log.warning("song_source job=%s failed: %s", job_id, exc)
    except Exception as exc:  # noqa: BLE001
        result = SongSourceResult(job_id=job_id, status="failed", error=f"unexpected error: {exc}")
        log.exception("song_source job=%s crashed", job_id)

    if request.callback_url:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(request.callback_url, json=result.model_dump())
        except Exception as exc:  # noqa: BLE001
            log.warning("song_source job=%s callback to %s failed: %s", job_id, request.callback_url, exc)


@router.post(
    "/songs/source",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=dict,
    summary="Download song audio via yt-dlp, optionally upload to S3-compatible storage",
)
@limiter.limit("10/minute")
async def source_song_audio(
    request: Request,
    response: Response,
    body: SongSourceRequest,
    background_tasks: BackgroundTasks,
    _api_key: str = Depends(require_api_key),
) -> dict:
    """Queue an audio download job. Returns immediately with a job_id.

    Processing happens asynchronously. If ``callback_url`` is provided a POST
    with a ``SongSourceResult`` JSON body is made on completion (success or failure).
    """
    job_id = str(uuid.uuid4())
    background_tasks.add_task(_process_song_source, job_id, body)
    return {"job_id": job_id, "status": "queued"}


# ── playlist audio sourcing ────────────────────────────────────────────────────


async def _process_playlist_source(job_id: str, request: PlaylistSourceRequest) -> None:
    """Background task: download audio for each song, upload to R2, POST callback."""
    sourced = 0
    skipped = 0
    failed = 0
    sourced_songs: list[SourcedSong] = []
    errors: list[dict] = []

    total_songs = len(request.songs)
    print(f"[playlist_source] job={job_id} START station_id={request.station_id} total_songs={total_songs}", flush=True)
    log.info("playlist_source job=%s START station_id=%s total_songs=%d", job_id, request.station_id, total_songs)

    try:
        r2 = s3_config_from_env()
    except RuntimeError as exc:
        print(f"[playlist_source] job={job_id} ERROR R2 config unavailable: {exc}", flush=True)
        log.error("playlist_source job=%s R2 config unavailable: %s", job_id, exc)
        result = PlaylistSourceResult(
            job_id=job_id,
            status="failed",
            station_id=request.station_id,
            total_songs=total_songs,
            sourced=0,
            skipped=0,
            failed=total_songs,
            error=str(exc),
        )
        if request.callback_url:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(request.callback_url, json=result.model_dump())
            except Exception as cb_exc:  # noqa: BLE001
                print(f"[playlist_source] job={job_id} WARNING callback failed: {cb_exc}", flush=True)
                log.warning("playlist_source job=%s callback failed: %s", job_id, cb_exc)
        return

    songs = request.songs[: request.limit]

    for idx, song in enumerate(songs, start=1):
        key = s3_song_key(title=song.title, artist=song.artist)
        output_dir = tempfile.mkdtemp()
        try:
            if request.skip_existing:
                try:
                    exists = await s3_object_exists(
                        key=key,
                        bucket=r2["bucket"],
                        endpoint=r2["endpoint"],
                        access_key=r2["access_key_id"],
                        secret_key=r2["secret_key"],
                        region=r2["region"],
                    )
                except Exception as exists_exc:  # noqa: BLE001
                    print(f"[playlist_source] job={job_id} WARNING s3_object_exists failed for song_id={song.song_id}: {exists_exc}", flush=True)
                    log.warning("playlist_source job=%s s3_object_exists failed song_id=%s: %s", job_id, song.song_id, exists_exc)
                    exists = False
                if exists:
                    skipped += 1
                    # Still report skipped songs so PlayGen can update audio_url if missing
                    s3_public_base = os.getenv("S3_PUBLIC_URL_BASE", "").rstrip("/")
                    cdn_url = f"{s3_public_base}/{key}" if s3_public_base else None
                    sourced_songs.append(SourcedSong(song_id=song.song_id, r2_key=key, audio_url=cdn_url))
                    print(f"[playlist_source] job={job_id} SKIP [{idx}/{len(songs)}] song_id={song.song_id} already in R2", flush=True)
                    log.info("playlist_source job=%s SKIP song_id=%s already in R2", job_id, song.song_id)
                    continue

            print(f"[playlist_source] job={job_id} SOURCING [{idx}/{len(songs)}] song_id={song.song_id} title={song.title!r} artist={song.artist!r}", flush=True)
            log.info("playlist_source job=%s SOURCING song_id=%s title=%r", job_id, song.song_id, song.title)

            try:
                audio = await source_audio(
                    title=song.title, artist=song.artist, output_dir=output_dir
                )
            except AudioSourceUnavailable as exc:
                raise  # re-raise to be caught by the outer except below

            await upload_to_s3(
                file_path=audio["path"],
                bucket=r2["bucket"],
                key=key,
                endpoint=r2["endpoint"],
                access_key=r2["access_key_id"],
                secret_key=r2["secret_key"],
                region=r2["region"],
            )
            sourced += 1
            s3_public_base = os.getenv("S3_PUBLIC_URL_BASE", "").rstrip("/")
            cdn_url = f"{s3_public_base}/{key}" if s3_public_base else None
            sourced_songs.append(SourcedSong(song_id=song.song_id, r2_key=key, audio_url=cdn_url))
            print(f"[playlist_source] job={job_id} OK [{idx}/{len(songs)}] song_id={song.song_id} key={key}", flush=True)
            log.info(
                "playlist_source job=%s OK song_id=%s title=%r key=%s",
                job_id, song.song_id, song.title, key,
            )
        except AudioSourceUnavailable as exc:
            failed += 1
            errors.append({
                "song_id": song.song_id,
                "title": song.title,
                "artist": song.artist,
                "error": str(exc),
            })
            print(f"[playlist_source] job={job_id} UNAVAILABLE [{idx}/{len(songs)}] song_id={song.song_id}: {exc}", flush=True)
            log.warning("playlist_source job=%s AudioSourceUnavailable song_id=%s: %s", job_id, song.song_id, exc)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append({
                "song_id": song.song_id,
                "title": song.title,
                "artist": song.artist,
                "error": str(exc),
            })
            print(f"[playlist_source] job={job_id} FAILED [{idx}/{len(songs)}] song_id={song.song_id}: {exc}", flush=True)
            log.warning(
                "playlist_source job=%s failed song_id=%s: %s",
                job_id, song.song_id, exc,
            )
        finally:
            shutil.rmtree(output_dir, ignore_errors=True)

    total = len(songs)
    if failed == 0:
        status_str = "completed"
    elif sourced > 0 or skipped > 0:
        status_str = "partial"
    else:
        status_str = "failed"

    print(f"[playlist_source] job={job_id} DONE status={status_str} sourced={sourced} skipped={skipped} failed={failed}", flush=True)
    log.info(
        "playlist_source job=%s DONE status=%s sourced=%d skipped=%d failed=%d",
        job_id, status_str, sourced, skipped, failed,
    )

    result = PlaylistSourceResult(
        job_id=job_id,
        status=status_str,
        station_id=request.station_id,
        total_songs=total,
        sourced=sourced,
        skipped=skipped,
        failed=failed,
        songs=sourced_songs,
        errors=errors,
    )

    if request.callback_url:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(request.callback_url, json=result.model_dump())
        except Exception as exc:  # noqa: BLE001
            print(f"[playlist_source] job={job_id} WARNING callback to {request.callback_url} failed: {exc}", flush=True)
            log.warning("playlist_source job=%s callback to %s failed: %s", job_id, request.callback_url, exc)


@router.post(
    "/playlists/source-audio",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=dict,
    summary="Download audio for a list of songs via yt-dlp, upload each to Cloudflare R2",
)
@limiter.limit("5/minute")
async def source_playlist_audio(
    request: Request,
    response: Response,
    body: PlaylistSourceRequest,
    background_tasks: BackgroundTasks,
    _api_key: str = Depends(require_api_key),
) -> dict:
    """Queue an audio sourcing job for a playlist.

    Processing happens asynchronously. Songs are downloaded sequentially to
    respect yt-dlp rate limits. If ``callback_url`` is set, a POST with a
    ``PlaylistSourceResult`` JSON body is made on completion.
    """
    job_id = str(uuid.uuid4())
    background_tasks.add_task(_process_playlist_source, job_id, body)
    return {"job_id": job_id, "status": "queued", "station_id": body.station_id}
