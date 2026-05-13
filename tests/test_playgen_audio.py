"""PlayGen Phase 7 — audio sourcing background task tests.

Tests:
1. Per-song failure doesn't abort the batch (_process_playlist_source).
2. Callback payload shape and R2 key format.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_playlist_request(songs, callback_url=None, skip_existing=False):
    """Build a PlaylistSourceRequest without touching the database."""
    from app.schemas_media import PlaylistSourceRequest, PlaylistSong

    return PlaylistSourceRequest(
        station_id="station-abc",
        songs=[PlaylistSong(**s) for s in songs],
        callback_url=callback_url,
        skip_existing=skip_existing,
        limit=50,
    )


def _fake_r2_config():
    return {
        "bucket": "test-bucket",
        "endpoint": "https://r2.example.com",
        "access_key_id": "AK",
        "secret_key": "SK",
        "region": "auto",
    }


def _fake_audio(path="/tmp/fake.mp3"):
    return {
        "path": path,
        "duration_sec": 210.0,
        "size_bytes": 4_200_000,
        "format": "mp3",
    }


def _fake_hls(hls_dir="/tmp/hls"):
    return {
        "playlist": f"{hls_dir}/playlist.m3u8",
        "total_size_bytes": 1_024_000,
        "segment_count": 35,
    }


# ---------------------------------------------------------------------------
# Test 1 — per-song failure doesn't abort the batch
# ---------------------------------------------------------------------------


def test_per_song_failure_does_not_abort_batch():
    """If one song fails, _process_playlist_source must continue and process the remaining songs."""
    from app.adapters.audio import AudioSourceUnavailable
    from app.routers.media import _process_playlist_source

    songs = [
        {"song_id": "s1", "title": "Song One", "artist": "Artist A"},
        {"song_id": "s2", "title": "Song Two", "artist": "Artist B"},
    ]
    request = _make_playlist_request(songs, callback_url="http://test.local/cb")

    callback_payloads: list[dict] = []

    call_count = 0

    async def _source_audio_side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise AudioSourceUnavailable("yt-dlp blocked")
        return _fake_audio()

    async def _fake_callback_post(url, json=None):
        callback_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 200
        return resp

    fake_client = AsyncMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.post = AsyncMock(side_effect=_fake_callback_post)

    r2_mock = MagicMock(return_value=_fake_r2_config())

    with (
        patch("app.routers.media.s3_config_from_env", r2_mock),
        patch("app.routers.media.source_audio", side_effect=_source_audio_side_effect),
        patch("app.routers.media.transcode_to_hls", new_callable=AsyncMock, return_value=_fake_hls()),
        patch("app.routers.media.upload_hls_to_s3", new_callable=AsyncMock, return_value=5),
        patch("app.routers.media.s3_object_exists", new_callable=AsyncMock, return_value=False),
        patch("httpx.AsyncClient", return_value=fake_client),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        asyncio.run(_process_playlist_source("job-001", request))

    # source_audio was called for both songs (not aborted after first failure)
    assert call_count == 2, f"Expected source_audio called twice, got {call_count}"

    # Callback was posted exactly once with the batch result
    assert len(callback_payloads) == 1
    payload = callback_payloads[0]

    assert payload["station_id"] == "station-abc"
    assert payload["failed"] == 1
    assert payload["sourced"] == 1

    # status should be "partial" (some sourced, some failed)
    assert payload["status"] == "partial"

    # Errors list must include the failed song
    assert len(payload["errors"]) == 1
    assert payload["errors"][0]["song_id"] == "s1"

    # Sourced songs list must include the successful song
    assert len(payload["songs"]) == 1
    assert payload["songs"][0]["song_id"] == "s2"


# ---------------------------------------------------------------------------
# Test 2 — callback payload shape and R2 key format
# ---------------------------------------------------------------------------


def test_callback_payload_shape_and_r2_key_format():
    """R2 object key must follow audio/songs/{artist_slug}/{title_slug}/playlist.m3u8 convention.

    The callback POST must contain station_id, job_id, total_songs, sourced,
    skipped, failed, songs (list with song_id and r2_key), and errors.
    """
    from app.adapters.audio import s3_song_key
    from app.routers.media import _process_playlist_source

    songs = [
        {"song_id": "song-99", "title": "Bohemian Rhapsody", "artist": "Queen"},
    ]
    request = _make_playlist_request(songs, callback_url="http://test.local/cb")

    callback_payloads: list[dict] = []

    async def _fake_callback_post(url, json=None):
        callback_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 200
        return resp

    fake_client = AsyncMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.post = AsyncMock(side_effect=_fake_callback_post)

    r2_mock = MagicMock(return_value=_fake_r2_config())

    with (
        patch("app.routers.media.s3_config_from_env", r2_mock),
        patch("app.routers.media.source_audio", new_callable=AsyncMock, return_value=_fake_audio()),
        patch("app.routers.media.transcode_to_hls", new_callable=AsyncMock, return_value=_fake_hls()),
        patch("app.routers.media.upload_hls_to_s3", new_callable=AsyncMock, return_value=3),
        patch("app.routers.media.s3_object_exists", new_callable=AsyncMock, return_value=False),
        patch("httpx.AsyncClient", return_value=fake_client),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        asyncio.run(_process_playlist_source("job-002", request))

    assert len(callback_payloads) == 1
    payload = callback_payloads[0]

    # Required top-level fields
    for field in ("job_id", "station_id", "total_songs", "sourced", "skipped", "failed", "songs", "errors"):
        assert field in payload, f"Missing field {field!r} in callback payload"

    assert payload["station_id"] == "station-abc"
    assert payload["total_songs"] == 1
    assert payload["sourced"] == 1
    assert payload["failed"] == 0
    assert payload["status"] == "completed"

    # R2 key format: audio/songs/{artist_slug}/{title_slug}/playlist.m3u8
    expected_base = s3_song_key(title="Bohemian Rhapsody", artist="Queen")
    expected_key = f"{expected_base}/playlist.m3u8"

    assert len(payload["songs"]) == 1
    song_result = payload["songs"][0]
    assert song_result["song_id"] == "song-99"
    assert song_result["r2_key"] == expected_key, (
        f"Expected r2_key={expected_key!r}, got {song_result['r2_key']!r}"
    )
