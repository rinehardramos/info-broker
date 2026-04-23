"""Unit tests for R2 helper functions in app/adapters/audio.py."""
from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.adapters.audio import s3_config_from_env, s3_object_exists, s3_song_key

# Plain non-credential test values — no embedded passwords in URLs.
BUCKET = "test-bucket"
ENDPOINT = "http://localhost:9000"
KEY_ID = "testkeyid"
SECRET = "testsecretvalue"
REGION = "auto"

FULL_ENV = {
    "S3_BUCKET": BUCKET,
    "S3_ENDPOINT": ENDPOINT,
    "S3_REGION": REGION,
    "S3_ACCESS_KEY_ID": KEY_ID,
    "S3_SECRET_ACCESS_KEY": SECRET,
}


class TestR2SongKey:
    def test_default_ext_is_mp3(self):
        assert s3_song_key("s1", "song1") == "songs/s1/song1.mp3"

    def test_custom_ext(self):
        assert s3_song_key("station-99", "abc123", ".flac") == "songs/station-99/abc123.flac"

    def test_key_structure_matches_playgen(self):
        # Key must match PlayGen's presignedUrlService songAudioKey():
        # songs/{stationId}/{songId}.mp3
        key = s3_song_key("my-station", "track-42")
        parts = key.split("/")
        assert parts[0] == "songs"
        assert parts[1] == "my-station"
        assert parts[2] == "track-42.mp3"


class TestR2ConfigFromEnv:
    def test_missing_all_vars_raises_runtime_error(self, monkeypatch):
        for var in FULL_ENV:
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(RuntimeError, match="Missing R2 env vars"):
            s3_config_from_env()

    def test_missing_single_var_raises_runtime_error(self, monkeypatch):
        for k, v in FULL_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.delenv("S3_SECRET_ACCESS_KEY")
        with pytest.raises(RuntimeError, match="secret_key"):
            s3_config_from_env()

    def test_all_vars_present_returns_correct_dict(self, monkeypatch):
        for k, v in FULL_ENV.items():
            monkeypatch.setenv(k, v)
        cfg = s3_config_from_env()
        assert cfg["bucket"] == BUCKET
        assert cfg["endpoint"] == ENDPOINT
        assert cfg["region"] == REGION
        assert cfg["access_key_id"] == KEY_ID
        assert cfg["secret_key"] == SECRET

    def test_region_defaults_to_auto_when_not_set(self, monkeypatch):
        for k, v in FULL_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.delenv("S3_REGION", raising=False)
        cfg = s3_config_from_env()
        assert cfg["region"] == "auto"


class TestR2ObjectExists:
    """Tests for s3_object_exists.

    boto3 and botocore are runtime dependencies (not installed in the dev venv).
    We inject a fake boto3 module via sys.modules so the lazy imports inside
    s3_object_exists resolve without the real packages.
    """

    # Fake ClientError that mirrors the botocore signature used in the adapter.
    class _FakeClientError(Exception):
        def __init__(self, code: str):
            self.response = {"Error": {"Code": code, "Message": "test"}}
            super().__init__(code)

    def _inject_fake_boto3(self, mock_client: MagicMock) -> None:
        """Inject mock boto3 + botocore into sys.modules."""
        fake_boto3 = SimpleNamespace(client=lambda *a, **kw: mock_client)
        fake_botocore_exc = SimpleNamespace(ClientError=self._FakeClientError)
        fake_botocore = SimpleNamespace(exceptions=fake_botocore_exc)
        sys.modules["boto3"] = fake_boto3  # type: ignore[assignment]
        sys.modules["botocore"] = fake_botocore  # type: ignore[assignment]
        sys.modules["botocore.exceptions"] = fake_botocore_exc  # type: ignore[assignment]

    def _restore_boto3(self) -> None:
        for mod in ("boto3", "botocore", "botocore.exceptions"):
            sys.modules.pop(mod, None)

    @pytest.mark.asyncio
    async def test_returns_true_when_object_exists(self):
        mock_client = MagicMock()
        mock_client.head_object.return_value = {}
        self._inject_fake_boto3(mock_client)
        try:
            import importlib
            import app.adapters.audio as audio_mod
            importlib.reload(audio_mod)
            result = await audio_mod.s3_object_exists(
                key="songs/s1/song1.mp3",
                bucket=BUCKET,
                endpoint=ENDPOINT,
                access_key=KEY_ID,
                secret_key=SECRET,
            )
        finally:
            self._restore_boto3()
        assert result is True
        mock_client.head_object.assert_called_once_with(Bucket=BUCKET, Key="songs/s1/song1.mp3")

    @pytest.mark.asyncio
    async def test_returns_false_on_404(self):
        mock_client = MagicMock()
        mock_client.head_object.side_effect = self._FakeClientError("404")
        self._inject_fake_boto3(mock_client)
        try:
            import importlib
            import app.adapters.audio as audio_mod
            importlib.reload(audio_mod)
            result = await audio_mod.s3_object_exists(
                key="songs/s1/missing.mp3",
                bucket=BUCKET,
                endpoint=ENDPOINT,
                access_key=KEY_ID,
                secret_key=SECRET,
            )
        finally:
            self._restore_boto3()
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_no_such_key(self):
        mock_client = MagicMock()
        mock_client.head_object.side_effect = self._FakeClientError("NoSuchKey")
        self._inject_fake_boto3(mock_client)
        try:
            import importlib
            import app.adapters.audio as audio_mod
            importlib.reload(audio_mod)
            result = await audio_mod.s3_object_exists(
                key="songs/s1/missing.mp3",
                bucket=BUCKET,
                endpoint=ENDPOINT,
                access_key=KEY_ID,
                secret_key=SECRET,
            )
        finally:
            self._restore_boto3()
        assert result is False

    @pytest.mark.asyncio
    async def test_re_raises_non_404_client_error(self):
        mock_client = MagicMock()
        mock_client.head_object.side_effect = self._FakeClientError("403")
        self._inject_fake_boto3(mock_client)
        try:
            import importlib
            import app.adapters.audio as audio_mod
            importlib.reload(audio_mod)
            with pytest.raises(self._FakeClientError):
                await audio_mod.s3_object_exists(
                    key="songs/s1/song.mp3",
                    bucket=BUCKET,
                    endpoint=ENDPOINT,
                    access_key=KEY_ID,
                    secret_key=SECRET,
                )
        finally:
            self._restore_boto3()
