"""Audio sourcing adapter - downloads audio via yt-dlp and optionally uploads to S3-compatible storage.

yt-dlp and ffprobe are expected as system binaries (installed in the Docker image).
Missing binaries are handled gracefully: FileNotFoundError is raised with a clear message
so the route can return a useful error rather than an unhandled crash.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
import unicodedata

log = logging.getLogger(__name__)


class AudioSourceUnavailable(Exception):
    """Raised when yt-dlp or ffprobe are missing or the download fails."""


async def source_audio(title: str, artist: str, output_dir: str | None = None) -> dict:
    """Search YouTube and download audio as MP3.

    Returns a dict with keys: path, duration_sec, size_bytes, format.
    Raises AudioSourceUnavailable when yt-dlp is missing or the download fails.
    """
    if not title.strip() or not artist.strip():
        raise ValueError("title and artist are required")

    query = f"{artist} - {title}"

    with tempfile.TemporaryDirectory() as tmpdir:
        target_dir = output_dir or tmpdir
        # yt-dlp appends the extension itself; the template without extension is
        # what we pass to --output. After extraction the file will be audio.mp3.
        out_template = os.path.join(target_dir, "audio.%(ext)s")
        outfile = os.path.join(target_dir, "audio.mp3")

        try:
            proc = await asyncio.create_subprocess_exec(
                "yt-dlp", f"ytsearch1:{query}",
                "--extract-audio", "--audio-format", "mp3", "--audio-quality", "192K",
                "--no-playlist", "--max-downloads", "1",
                "--output", out_template,
                "--no-warnings", "--quiet",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise AudioSourceUnavailable("yt-dlp is not installed or not on PATH") from exc

        try:
            await asyncio.wait_for(proc.wait(), timeout=120)
        except asyncio.TimeoutError as exc:
            proc.kill()
            raise AudioSourceUnavailable(f"yt-dlp timed out for: {query}") from exc

        # Exit code 101 means "--max-downloads reached" — the requested download
        # completed successfully; yt-dlp just signals there are no more items.
        if proc.returncode not in (0, 101):
            stderr_bytes = b""
            if proc.stderr:
                stderr_bytes = await proc.stderr.read()
            raise AudioSourceUnavailable(
                f"yt-dlp exited with code {proc.returncode} for: {query} "
                f"— {stderr_bytes.decode(errors='replace').strip()}"
            )

        if not os.path.exists(outfile):
            raise AudioSourceUnavailable(f"yt-dlp produced no audio for: {query}")

        duration_sec = await probe_duration(outfile)
        size_bytes = os.path.getsize(outfile)

        return {
            "path": outfile,
            "duration_sec": duration_sec,
            "size_bytes": size_bytes,
            "format": "mp3",
        }


async def probe_duration(path: str) -> float | None:
    """Return audio duration in seconds via ffprobe, or None if unavailable."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        info = json.loads(stdout)
        return round(float(info["format"]["duration"]), 2)
    except FileNotFoundError:
        log.warning("ffprobe not found — duration will be None")
        return None
    except Exception:  # noqa: BLE001
        log.warning("ffprobe failed to parse duration for %s", path)
        return None


async def upload_to_s3(
    file_path: str,
    bucket: str,
    key: str,
    endpoint: str,
    access_key: str,
    secret_key: str,
    region: str = "auto",
) -> str:
    """Upload a file to an S3-compatible store (R2 / B2 / AWS S3).

    Returns the object key on success.
    Raises ImportError if boto3 is not installed, RuntimeError on upload failure.
    """
    try:
        import boto3  # type: ignore[import-untyped]
        from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "boto3 is required for S3 uploads — install it with: pip install boto3"
        ) from exc

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    try:
        s3.upload_file(
            file_path,
            bucket,
            key,
            ExtraArgs={"ContentType": "audio/mpeg"},
        )
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError(f"S3 upload failed: {exc}") from exc

    return key


# ── HLS transcoding ──────────────────────────────────────────────────────────


async def transcode_to_hls(
    input_path: str,
    output_dir: str,
    segment_duration: int = 6,
) -> dict:
    """Transcode audio to HLS segments (AAC 128k fMP4).

    Returns: { playlist_path, files, duration_sec, total_size_bytes }
    where files is a list of (local_path, relative_name) tuples.
    """
    playlist_path = os.path.join(output_dir, "playlist.m3u8")

    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", input_path,
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-f", "hls",
        "-hls_time", str(segment_duration),
        "-hls_segment_type", "fmp4",
        "-hls_fmp4_init_filename", "init.mp4",
        "-hls_segment_filename", os.path.join(output_dir, "seg-%03d.m4s"),
        "-hls_playlist_type", "vod",
        "-y",  # overwrite
        playlist_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        proc.kill()
        raise AudioSourceUnavailable("ffmpeg HLS transcode timed out")

    if proc.returncode != 0:
        raise AudioSourceUnavailable(
            f"ffmpeg HLS transcode failed (exit {proc.returncode}): "
            f"{stderr.decode(errors='replace').strip()[-200:]}"
        )

    # Collect all output files
    files: list[tuple[str, str]] = []
    total_size = 0
    for name in os.listdir(output_dir):
        fpath = os.path.join(output_dir, name)
        if os.path.isfile(fpath):
            files.append((fpath, name))
            total_size += os.path.getsize(fpath)

    duration_sec = await probe_duration(input_path)

    return {
        "playlist_path": playlist_path,
        "files": files,
        "duration_sec": duration_sec,
        "total_size_bytes": total_size,
    }


# Content-type mapping for HLS segment files
_HLS_CONTENT_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".mp4": "video/mp4",
    ".m4s": "video/iso.segment",
}


async def upload_hls_to_s3(
    hls_dir: str,
    base_key: str,
    bucket: str,
    endpoint: str,
    access_key: str,
    secret_key: str,
    region: str = "auto",
) -> int:
    """Upload all HLS segment files to S3/R2 under base_key/.

    Returns the number of files uploaded.
    """
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )

    uploaded = 0
    for name in os.listdir(hls_dir):
        fpath = os.path.join(hls_dir, name)
        if not os.path.isfile(fpath):
            continue

        ext = os.path.splitext(name)[1].lower()
        content_type = _HLS_CONTENT_TYPES.get(ext, "application/octet-stream")
        s3_key = f"{base_key}/{name}"

        try:
            s3.upload_file(fpath, bucket, s3_key, ExtraArgs={"ContentType": content_type})
            uploaded += 1
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError(f"S3 upload failed for {s3_key}: {exc}") from exc

    return uploaded


# ── R2 helpers ────────────────────────────────────────────────────────────────


def slugify(text: str) -> str:
    """URL-safe slug: lowercase, hyphenated, ASCII-only."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text.lower().strip())
    return re.sub(r"[-\s]+", "-", text).strip("-") or "unknown"


def s3_song_key(title: str, artist: str) -> str:
    """Build the R2 key prefix for a song using artist/title convention.

    Convention: audio/songs/{artist_slug}/{title_slug}
    HLS segments stored under this prefix: playlist.m3u8, init.mp4, seg-*.m4s
    Same song by same artist = same prefix (idempotent, shared across stations).
    """
    return f"audio/songs/{slugify(artist)}/{slugify(title)}"


def s3_config_from_env() -> dict:
    """Load R2 credentials from environment. Raises RuntimeError if any are missing."""
    import os
    required = {
        "bucket": os.getenv("S3_BUCKET"),
        "endpoint": os.getenv("S3_ENDPOINT"),
        "region": os.getenv("S3_REGION", "auto"),
        "access_key_id": os.getenv("S3_ACCESS_KEY_ID"),
        "secret_key": os.getenv("S3_SECRET_ACCESS_KEY"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise RuntimeError(f"Missing R2 env vars: {', '.join(missing)}")
    return required


async def s3_object_exists(
    key: str, bucket: str, endpoint: str, access_key: str, secret_key: str, region: str = "auto"
) -> bool:
    """Check if an object exists in R2 without downloading it."""
    import asyncio
    import boto3
    from botocore.exceptions import ClientError

    def _check():
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        try:
            client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False
            raise

    return await asyncio.get_event_loop().run_in_executor(None, _check)
