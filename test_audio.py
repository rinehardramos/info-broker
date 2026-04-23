"""Tests for the audio sourcing adapter and POST /v1/songs/source route."""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

API_KEY = "test-broker-key"

# Placeholder values for S3 fields — not real credentials.
_FAKE_BUCKET = "test-bucket"
_FAKE_KEY = "songs/test.mp3"
_FAKE_ENDPOINT = "http://localhost:9000"
_FAKE_ACCESS = "testaccesskey"
_FAKE_SECRET = "testsecretkey"
_FAKE_CALLBACK = "http://localhost:8080/hook"
_FAKE_DEAD_CALLBACK = "http://localhost:9999/hook"


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch):
    monkeypatch.setenv("INFO_BROKER_API_KEY", API_KEY)
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ── source_audio ──────────────────────────────────────────────────────────────


class TestSourceAudio:
    @pytest.mark.asyncio
    async def test_happy_path_returns_dict(self, tmp_path):
        outfile = tmp_path / "audio.mp3"
        outfile.write_bytes(b"\xff\xfb" * 100)

        async def _fake_exec(*args, **kwargs):
            class _P:
                returncode = 0
                stderr = None

                async def wait(self):
                    return 0

            return _P()

        with (
            patch("app.adapters.audio.asyncio.create_subprocess_exec", side_effect=_fake_exec),
            patch("app.adapters.audio.probe_duration", return_value=180.5),
        ):
            from app.adapters.audio import source_audio

            result = await source_audio(
                title="Yesterday", artist="The Beatles", output_dir=str(tmp_path)
            )

        assert result["format"] == "mp3"
        assert result["duration_sec"] == 180.5
        assert result["size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_missing_ytdlp_raises_unavailable(self):
        with patch(
            "app.adapters.audio.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("yt-dlp not found"),
        ):
            from app.adapters.audio import AudioSourceUnavailable, source_audio

            with pytest.raises(AudioSourceUnavailable, match="yt-dlp"):
                await source_audio(title="Song", artist="Artist")

    @pytest.mark.asyncio
    async def test_nonzero_exit_raises_unavailable(self, tmp_path):
        async def _fake_exec(*args, **kwargs):
            class _Stream:
                async def read(self):
                    return b"ERROR: no video"

            class _P:
                returncode = 1
                stderr = _Stream()

                async def wait(self):
                    return 1

            return _P()

        with patch("app.adapters.audio.asyncio.create_subprocess_exec", side_effect=_fake_exec):
            from app.adapters.audio import AudioSourceUnavailable, source_audio

            with pytest.raises(AudioSourceUnavailable, match="exited with code 1"):
                await source_audio(title="x", artist="y", output_dir=str(tmp_path))

    @pytest.mark.asyncio
    async def test_blank_title_raises_value_error(self):
        from app.adapters.audio import source_audio

        with pytest.raises(ValueError, match="required"):
            await source_audio(title="  ", artist="Artist")

    @pytest.mark.asyncio
    async def test_blank_artist_raises_value_error(self):
        from app.adapters.audio import source_audio

        with pytest.raises(ValueError, match="required"):
            await source_audio(title="Song", artist="  ")


# ── probe_duration ────────────────────────────────────────────────────────────


class TestProbeDuration:
    @pytest.mark.asyncio
    async def test_returns_none_when_ffprobe_missing(self):
        with patch(
            "app.adapters.audio.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("ffprobe not found"),
        ):
            from app.adapters.audio import probe_duration

            assert await probe_duration("/some/file.mp3") is None

    @pytest.mark.asyncio
    async def test_parses_ffprobe_json_output(self):
        out = json.dumps({"format": {"duration": "213.456"}}).encode()

        async def _fake_exec(*args, **kwargs):
            class _P:
                async def communicate(self):
                    return out, b""

            return _P()

        with patch("app.adapters.audio.asyncio.create_subprocess_exec", side_effect=_fake_exec):
            from app.adapters.audio import probe_duration

            assert await probe_duration("/some/file.mp3") == 213.46

    @pytest.mark.asyncio
    async def test_returns_none_on_corrupt_output(self):
        async def _fake_exec(*args, **kwargs):
            class _P:
                async def communicate(self):
                    return b"not-json", b""

            return _P()

        with patch("app.adapters.audio.asyncio.create_subprocess_exec", side_effect=_fake_exec):
            from app.adapters.audio import probe_duration

            assert await probe_duration("/some/file.mp3") is None


# ── upload_to_s3 ──────────────────────────────────────────────────────────────


class TestUploadToS3:
    @pytest.mark.asyncio
    async def test_upload_returns_key(self, tmp_path):
        dummy = tmp_path / "audio.mp3"
        dummy.write_bytes(b"fake")

        # boto3 may not be installed in the local dev venv (it is a runtime dep
        # installed via uv sync / Docker). Inject a fake module so the lazy
        # import inside upload_to_s3 resolves without the real package.
        fake_s3_client = SimpleNamespace(upload_file=lambda *a, **kw: None)
        fake_boto3 = SimpleNamespace(client=lambda *a, **kw: fake_s3_client)
        fake_botocore = SimpleNamespace(
            exceptions=SimpleNamespace(BotoCoreError=Exception, ClientError=Exception)
        )
        sys.modules.setdefault("botocore", fake_botocore)
        sys.modules.setdefault("botocore.exceptions", fake_botocore.exceptions)
        sys.modules["boto3"] = fake_boto3  # type: ignore[assignment]
        try:
            import importlib
            import app.adapters.audio as audio_mod
            importlib.reload(audio_mod)
            key = await audio_mod.upload_to_s3(
                file_path=str(dummy),
                bucket=_FAKE_BUCKET,
                key=_FAKE_KEY,
                endpoint=_FAKE_ENDPOINT,
                access_key=_FAKE_ACCESS,
                secret_key=_FAKE_SECRET,
            )
        finally:
            sys.modules.pop("boto3", None)
        assert key == _FAKE_KEY

    @pytest.mark.asyncio
    async def test_missing_boto3_raises_import_error(self):
        original = sys.modules.get("boto3")
        sys.modules["boto3"] = None  # type: ignore[assignment]
        try:
            import importlib
            import app.adapters.audio as audio_mod

            importlib.reload(audio_mod)
            with pytest.raises(ImportError, match="boto3"):
                await audio_mod.upload_to_s3(
                    file_path="/f.mp3",
                    bucket="b",
                    key="k",
                    endpoint=_FAKE_ENDPOINT,
                    access_key=_FAKE_ACCESS,
                    secret_key=_FAKE_SECRET,
                )
        finally:
            if original is None:
                sys.modules.pop("boto3", None)
            else:
                sys.modules["boto3"] = original


# ── /v1/songs/source route ────────────────────────────────────────────────────


class TestSongSourceRoute:
    def test_missing_api_key_returns_401(self, client):
        r = client.post("/v1/songs/source", json={"title": "Song", "artist": "Artist"})
        assert r.status_code == 401

    def test_wrong_api_key_returns_401(self, client):
        r = client.post(
            "/v1/songs/source",
            json={"title": "Song", "artist": "Artist"},
            headers={"X-API-Key": "bad-key"},
        )
        assert r.status_code == 401

    def test_missing_body_returns_422(self, client):
        r = client.post("/v1/songs/source", headers={"X-API-Key": API_KEY})
        assert r.status_code == 422

    def test_missing_title_returns_422(self, client):
        r = client.post(
            "/v1/songs/source",
            json={"artist": "Artist"},
            headers={"X-API-Key": API_KEY},
        )
        assert r.status_code == 422

    def test_missing_artist_returns_422(self, client):
        r = client.post(
            "/v1/songs/source",
            json={"title": "Song"},
            headers={"X-API-Key": API_KEY},
        )
        assert r.status_code == 422

    def test_happy_path_returns_202_with_job_id(self, client):
        r = client.post(
            "/v1/songs/source",
            json={"title": "Yesterday", "artist": "The Beatles"},
            headers={"X-API-Key": API_KEY},
        )
        assert r.status_code == 202
        body = r.json()
        assert body["status"] == "queued"
        assert "job_id" in body
        import uuid as _uuid

        _uuid.UUID(body["job_id"])  # raises ValueError if not a valid UUID

    def test_each_request_gets_unique_job_id(self, client):
        r1 = client.post(
            "/v1/songs/source",
            json={"title": "a", "artist": "b"},
            headers={"X-API-Key": API_KEY},
        )
        r2 = client.post(
            "/v1/songs/source",
            json={"title": "c", "artist": "d"},
            headers={"X-API-Key": API_KEY},
        )
        assert r1.json()["job_id"] != r2.json()["job_id"]


# ── _process_song_source background task ─────────────────────────────────────


class TestProcessSongSource:
    @pytest.mark.asyncio
    async def test_success_no_upload_no_callback(self, tmp_path):
        audio_result = {
            "path": str(tmp_path / "audio.mp3"),
            "duration_sec": 200.0,
            "size_bytes": 5000,
            "format": "mp3",
        }
        from app.routers.media import _process_song_source
        from app.schemas_media import SongSourceRequest

        with patch("app.routers.media.source_audio", return_value=audio_result):
            await _process_song_source("job-1", SongSourceRequest(title="Song", artist="Artist"))

    @pytest.mark.asyncio
    async def test_success_with_upload_target(self, tmp_path):
        audio_result = {
            "path": str(tmp_path / "audio.mp3"),
            "duration_sec": 200.0,
            "size_bytes": 5000,
            "format": "mp3",
        }
        from app.routers.media import _process_song_source
        from app.schemas_media import S3UploadTarget, SongSourceRequest

        target = S3UploadTarget(
            bucket=_FAKE_BUCKET,
            key=_FAKE_KEY,
            endpoint=_FAKE_ENDPOINT,
            access_key_id=_FAKE_ACCESS,
            secret_access_key=_FAKE_SECRET,
        )
        req = SongSourceRequest(title="Song", artist="Artist", upload_target=target)

        with (
            patch("app.routers.media.source_audio", return_value=audio_result),
            patch("app.routers.media.upload_to_s3", return_value=_FAKE_KEY) as mock_upload,
        ):
            await _process_song_source("job-2", req)

        mock_upload.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_audio_failure_posts_error_to_callback(self):
        from app.adapters.audio import AudioSourceUnavailable
        from app.routers.media import _process_song_source
        from app.schemas_media import SongSourceRequest

        posted: list[dict] = []

        class _FakeResp:
            status_code = 200

        class _FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            async def post(self, url, json=None):
                posted.append(json or {})
                return _FakeResp()

        with (
            patch(
                "app.routers.media.source_audio",
                side_effect=AudioSourceUnavailable("yt-dlp not installed"),
            ),
            patch("app.routers.media.httpx.AsyncClient", return_value=_FakeClient()),
        ):
            await _process_song_source(
                "job-3",
                SongSourceRequest(
                    title="Song", artist="Artist", callback_url=_FAKE_CALLBACK
                ),
            )

        assert len(posted) == 1
        assert posted[0]["status"] == "failed"
        assert "yt-dlp" in posted[0]["error"]
        assert posted[0]["job_id"] == "job-3"

    @pytest.mark.asyncio
    async def test_callback_failure_does_not_propagate(self):
        """A broken callback URL must not crash the background task."""
        audio_result = {
            "path": "/tmp/audio.mp3",
            "duration_sec": 100.0,
            "size_bytes": 1000,
            "format": "mp3",
        }
        from app.routers.media import _process_song_source
        from app.schemas_media import SongSourceRequest

        class _BrokenClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            async def post(self, url, json=None):
                raise ConnectionError("callback host unreachable")

        with (
            patch("app.routers.media.source_audio", return_value=audio_result),
            patch("app.routers.media.httpx.AsyncClient", return_value=_BrokenClient()),
        ):
            await _process_song_source(
                "job-4",
                SongSourceRequest(
                    title="Song", artist="Artist", callback_url=_FAKE_DEAD_CALLBACK
                ),
            )

    @pytest.mark.asyncio
    async def test_success_callback_includes_all_result_fields(self):
        audio_result = {
            "path": "/tmp/audio.mp3",
            "duration_sec": 213.5,
            "size_bytes": 8192,
            "format": "mp3",
        }
        from app.routers.media import _process_song_source
        from app.schemas_media import SongSourceRequest

        posted: list[dict] = []

        class _FakeResp:
            status_code = 200

        class _FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            async def post(self, url, json=None):
                posted.append(json or {})
                return _FakeResp()

        with (
            patch("app.routers.media.source_audio", return_value=audio_result),
            patch("app.routers.media.httpx.AsyncClient", return_value=_FakeClient()),
        ):
            await _process_song_source(
                "job-5",
                SongSourceRequest(
                    title="Song", artist="Artist", callback_url=_FAKE_CALLBACK
                ),
            )

        body = posted[0]
        assert body["status"] == "completed"
        assert body["duration_sec"] == 213.5
        assert body["size_bytes"] == 8192
        assert body["format"] == "mp3"
        assert body["error"] is None
