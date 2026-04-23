"""Tests for POST /v1/playlists/source-audio."""
from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.modules.setdefault("qdrant_client", MagicMock())
sys.modules.setdefault("qdrant_client.models", MagicMock())

os.environ.setdefault("INFO_BROKER_API_KEY", "test-secret-key")
os.environ.setdefault("POSTGRES_DB", "info_broker")
os.environ.setdefault("POSTGRES_USER", "user")
os.environ.setdefault("POSTGRES_PASSWORD", "password")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6333")

from app.main import app  # noqa: E402
from app.routers.media import _process_playlist_source  # noqa: E402
from app.schemas_media import PlaylistSourceRequest, PlaylistSong  # noqa: E402

API_KEY = "test-secret-key"

# Callback URL used in tests — no credentials embedded.
CB_URL = "http://cb.test/done"

ALL_R2_VARS = [
    "S3_BUCKET",
    "S3_ENDPOINT",
    "S3_REGION",
    "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY",
]


def _r2_env(monkeypatch) -> None:
    """Populate R2 env vars with safe placeholder values."""
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("S3_REGION", "auto")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "test-access-key")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "test-secret-key")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _songs(n: int = 2) -> list[dict]:
    return [
        {"song_id": f"song-{i}", "title": f"Title {i}", "artist": f"Artist {i}"}
        for i in range(n)
    ]


def _valid_body(n: int = 2, **overrides) -> dict:
    body: dict = {"station_id": "station-abc", "songs": _songs(n), "skip_existing": False}
    body.update(overrides)
    return body


def _fake_audio(output_dir: str) -> dict:
    path = os.path.join(output_dir, "audio.mp3")
    open(path, "wb").close()  # noqa: WPS515
    return {"path": path, "duration_sec": 180.0, "size_bytes": 4096, "format": "mp3"}


def _two_songs() -> list[PlaylistSong]:
    return [
        PlaylistSong(song_id="s1", title="Song One", artist="Artist A"),
        PlaylistSong(song_id="s2", title="Song Two", artist="Artist B"),
    ]


# ── route integration tests ────────────────────────────────────────────────────


class TestPlaylistSourceRoute:
    def test_missing_api_key_returns_401(self, client: TestClient) -> None:
        r = client.post("/v1/playlists/source-audio", json=_valid_body())
        assert r.status_code == 401

    def test_wrong_api_key_returns_401(self, client: TestClient) -> None:
        r = client.post(
            "/v1/playlists/source-audio",
            json=_valid_body(),
            headers={"X-API-Key": "wrong-key"},
        )
        assert r.status_code == 401

    def test_missing_station_id_returns_422(self, client: TestClient) -> None:
        body = _valid_body()
        del body["station_id"]
        r = client.post(
            "/v1/playlists/source-audio",
            json=body,
            headers={"X-API-Key": API_KEY},
        )
        assert r.status_code == 422

    def test_missing_songs_returns_422(self, client: TestClient) -> None:
        body = _valid_body()
        del body["songs"]
        r = client.post(
            "/v1/playlists/source-audio",
            json=body,
            headers={"X-API-Key": API_KEY},
        )
        assert r.status_code == 422

    def test_limit_zero_returns_422(self, client: TestClient) -> None:
        r = client.post(
            "/v1/playlists/source-audio",
            json={**_valid_body(), "limit": 0},
            headers={"X-API-Key": API_KEY},
        )
        assert r.status_code == 422

    def test_valid_request_returns_202_with_job_id_and_station_id(
        self, client: TestClient
    ) -> None:
        r = client.post(
            "/v1/playlists/source-audio",
            json=_valid_body(),
            headers={"X-API-Key": API_KEY},
        )
        assert r.status_code == 202
        body = r.json()
        assert "job_id" in body
        assert body["status"] == "queued"
        assert body["station_id"] == "station-abc"


# ── background task unit tests ─────────────────────────────────────────────────


class TestProcessPlaylistSource:
    @pytest.mark.asyncio
    async def test_happy_path_sources_all_songs(self, monkeypatch, tmp_path) -> None:
        _r2_env(monkeypatch)

        async def fake_source(title, artist, output_dir=None):
            return _fake_audio(output_dir or str(tmp_path))

        captured: list[dict] = []

        async def fake_post(self_arg, url, **kwargs):
            captured.append(kwargs.get("json", {}))
            return MagicMock(status_code=200)

        with (
            patch("app.routers.media.s3_object_exists", new=AsyncMock(return_value=False)),
            patch("app.routers.media.source_audio", side_effect=fake_source),
            patch("app.routers.media.upload_to_s3", new=AsyncMock(return_value="key")),
            patch("httpx.AsyncClient.post", fake_post),
        ):
            await _process_playlist_source(
                "job-1",
                PlaylistSourceRequest(
                    station_id="stn-1",
                    songs=_two_songs(),
                    skip_existing=False,
                    callback_url=CB_URL,
                ),
            )

        assert len(captured) == 1
        result = captured[0]
        assert result["sourced"] == 2
        assert result["skipped"] == 0
        assert result["failed"] == 0
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_skip_existing_skips_all_when_all_exist(
        self, monkeypatch, tmp_path
    ) -> None:
        _r2_env(monkeypatch)
        captured: list[dict] = []

        async def fake_post(self_arg, url, **kwargs):
            captured.append(kwargs.get("json", {}))
            return MagicMock(status_code=200)

        mock_source = AsyncMock()
        with (
            patch("app.routers.media.s3_object_exists", new=AsyncMock(return_value=True)),
            patch("app.routers.media.source_audio", mock_source),
            patch("httpx.AsyncClient.post", fake_post),
        ):
            await _process_playlist_source(
                "job-2",
                PlaylistSourceRequest(
                    station_id="stn-1",
                    songs=_two_songs(),
                    skip_existing=True,
                    callback_url=CB_URL,
                ),
            )

        mock_source.assert_not_awaited()
        assert len(captured) == 1
        result = captured[0]
        assert result["skipped"] == 2
        assert result["sourced"] == 0
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_s3_config_missing_sets_failed_status(self, monkeypatch) -> None:
        for k in ALL_R2_VARS:
            monkeypatch.delenv(k, raising=False)

        captured: list[dict] = []

        async def fake_post(self_arg, url, **kwargs):
            captured.append(kwargs.get("json", {}))
            return MagicMock(status_code=200)

        with patch("httpx.AsyncClient.post", fake_post):
            await _process_playlist_source(
                "job-3",
                PlaylistSourceRequest(
                    station_id="stn-1",
                    songs=[PlaylistSong(song_id="s1", title="Song One", artist="Artist A")],
                    skip_existing=False,
                    callback_url=CB_URL,
                ),
            )

        assert len(captured) == 1
        result = captured[0]
        assert result["status"] == "failed"
        assert result["error"] is not None
        assert "R2" in result["error"]

    @pytest.mark.asyncio
    async def test_partial_failure_sets_partial_status(
        self, monkeypatch, tmp_path
    ) -> None:
        _r2_env(monkeypatch)
        call_count = 0

        async def sometimes_fails(title, artist, output_dir=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _fake_audio(output_dir or str(tmp_path))
            raise RuntimeError("yt-dlp failed")

        captured: list[dict] = []

        async def fake_post(self_arg, url, **kwargs):
            captured.append(kwargs.get("json", {}))
            return MagicMock(status_code=200)

        with (
            patch("app.routers.media.s3_object_exists", new=AsyncMock(return_value=False)),
            patch("app.routers.media.source_audio", side_effect=sometimes_fails),
            patch("app.routers.media.upload_to_s3", new=AsyncMock(return_value="key")),
            patch("httpx.AsyncClient.post", fake_post),
        ):
            await _process_playlist_source(
                "job-4",
                PlaylistSourceRequest(
                    station_id="stn-1",
                    songs=_two_songs(),
                    skip_existing=False,
                    callback_url=CB_URL,
                ),
            )

        assert len(captured) == 1
        result = captured[0]
        assert result["status"] == "partial"
        assert result["sourced"] == 1
        assert result["failed"] == 1
        assert result["errors"][0]["song_id"] == "s2"

    @pytest.mark.asyncio
    async def test_limit_applied_to_songs(self, monkeypatch, tmp_path) -> None:
        _r2_env(monkeypatch)
        sourced_titles: list[str] = []

        async def fake_source(title, artist, output_dir=None):
            sourced_titles.append(title)
            return _fake_audio(output_dir or str(tmp_path))

        with (
            patch("app.routers.media.s3_object_exists", new=AsyncMock(return_value=False)),
            patch("app.routers.media.source_audio", side_effect=fake_source),
            patch("app.routers.media.upload_to_s3", new=AsyncMock(return_value="key")),
        ):
            await _process_playlist_source(
                "job-5",
                PlaylistSourceRequest(
                    station_id="stn-1",
                    songs=[
                        PlaylistSong(song_id=f"s{i}", title=f"Song {i}", artist="A")
                        for i in range(5)
                    ],
                    skip_existing=False,
                    limit=3,
                ),
            )

        assert len(sourced_titles) == 3

    @pytest.mark.asyncio
    async def test_no_callback_url_does_not_post(self, monkeypatch, tmp_path) -> None:
        _r2_env(monkeypatch)

        async def fake_source(title, artist, output_dir=None):
            return _fake_audio(output_dir or str(tmp_path))

        mock_post = AsyncMock()
        with (
            patch("app.routers.media.s3_object_exists", new=AsyncMock(return_value=False)),
            patch("app.routers.media.source_audio", side_effect=fake_source),
            patch("app.routers.media.upload_to_s3", new=AsyncMock(return_value="key")),
            patch("httpx.AsyncClient.post", mock_post),
        ):
            await _process_playlist_source(
                "job-6",
                PlaylistSourceRequest(
                    station_id="stn-1",
                    songs=[PlaylistSong(song_id="s1", title="Song One", artist="Artist A")],
                    skip_existing=False,
                    callback_url=None,
                ),
            )

        mock_post.assert_not_awaited()
