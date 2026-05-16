#!/usr/bin/env python3
"""Upload a file to R2 under the infobroker/ prefix and print a read-only
   signed URL valid for 7 days (R2's max presign TTL).

Usage:
  uv run python3 scripts/upload-to-r2.py <local-file-path> [<key-suffix>]

Examples:
  uv run python3 scripts/upload-to-r2.py docs/demos/v0.6.0/feature-tour.webm
  uv run python3 scripts/upload-to-r2.py report.pdf releases/0.7.0/report.pdf

If <key-suffix> is omitted, the file's basename is used. The key is
always prefixed with 'infobroker/'. The presigned URL is GET-only —
no write or delete capability.

Required env (read from .env or process env):
  S3_BUCKET, S3_ENDPOINT, S3_REGION, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY
"""
from __future__ import annotations

import mimetypes
import os
import sys
from pathlib import Path

try:
    import boto3
except ImportError:
    print("error: boto3 not installed. Run with `uv run python3` from the repo root.", file=sys.stderr)
    sys.exit(2)


def load_env() -> dict[str, str]:
    """Read .env (repo root) into a plain dict. Process env takes precedence."""
    env: dict[str, str] = {}
    dotenv = Path(__file__).resolve().parent.parent / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    # Process env wins so callers can override per-invocation.
    for k in (
        "S3_BUCKET", "S3_ENDPOINT", "S3_REGION",
        "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY",
    ):
        if k in os.environ:
            env[k] = os.environ[k]
    return env


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__, file=sys.stderr)
        return 1

    src = Path(sys.argv[1])
    if not src.is_file():
        print(f"error: {src} is not a file", file=sys.stderr)
        return 1

    env = load_env()
    missing = [k for k in (
        "S3_BUCKET", "S3_ENDPOINT", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY",
    ) if not env.get(k)]
    if missing:
        print(f"error: missing env vars: {', '.join(missing)}", file=sys.stderr)
        return 1

    suffix = sys.argv[2] if len(sys.argv) >= 3 else src.name
    # Hard-prefix with infobroker/ — don't double-prefix if caller already added it.
    key = suffix if suffix.startswith("infobroker/") else f"infobroker/{suffix}"

    content_type = mimetypes.guess_type(src.name)[0] or "application/octet-stream"

    s3 = boto3.client(
        "s3",
        endpoint_url=env["S3_ENDPOINT"],
        aws_access_key_id=env["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=env["S3_SECRET_ACCESS_KEY"],
        region_name=env.get("S3_REGION", "auto"),
    )

    size_mb = src.stat().st_size / 1_000_000
    print(f"Uploading {size_mb:.1f} MB → r2://{env['S3_BUCKET']}/{key}", file=sys.stderr)
    s3.upload_file(
        str(src), env["S3_BUCKET"], key,
        ExtraArgs={"ContentType": content_type, "ContentDisposition": "inline"},
    )
    print("Uploaded ✓", file=sys.stderr)

    # Presigned URLs default to GET; we don't grant any write actions, so this
    # is read-only by construction. R2 maxes out at 7 days (604800 s).
    url = s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": env["S3_BUCKET"], "Key": key},
        ExpiresIn=7 * 24 * 3600,
        HttpMethod="GET",
    )
    # Print URL to stdout so callers can capture it; status notes go to stderr.
    print(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
