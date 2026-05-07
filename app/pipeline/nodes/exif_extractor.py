"""EXIF metadata extractor node — extracts GPS, timestamps, and device info from images."""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "EXIF metadata reveals GPS coordinates, capture timestamps, and device/author info "
    "embedded in images and documents — useful for geolocation and attribution"
)


def _fetch_file_bytes(url: str) -> bytes:
    """Fetch file content from a URL. Returns raw bytes."""
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content
    except Exception as exc:
        log.warning("exif_extractor: failed to fetch %r: %s", url, exc)
        raise


def _dms_to_decimal(dms_values: tuple, ref: str) -> float | None:
    """Convert DMS (degrees, minutes, seconds) tuple to decimal degrees."""
    try:
        degrees = float(dms_values[0])
        minutes = float(dms_values[1])
        seconds = float(dms_values[2])
        decimal = degrees + minutes / 60.0 + seconds / 3600.0
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except Exception:
        return None


def _extract_exif_from_bytes(data: bytes) -> dict:
    """Extract EXIF metadata from image bytes using PIL/Pillow."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS
    except ImportError:
        return {"error": "Pillow not installed"}

    try:
        import io
        img = Image.open(io.BytesIO(data))
        raw_exif = img._getexif()  # type: ignore[attr-defined]
        if not raw_exif:
            return {}
    except Exception:
        return {}

    metadata: dict = {}
    gps_data: dict = {}

    # Map numeric EXIF tag IDs to human-readable names
    tag_map = {v: k for k, v in TAGS.items()}

    for tag_id, value in raw_exif.items():
        tag_name = TAGS.get(tag_id, str(tag_id))

        if tag_name == "GPSInfo":
            # Decode GPS sub-tags
            for gps_tag_id, gps_value in value.items():
                gps_tag_name = GPSTAGS.get(gps_tag_id, str(gps_tag_id))
                gps_data[gps_tag_name] = gps_value
        elif tag_name == "DateTime":
            metadata["datetime"] = str(value)
        elif tag_name == "DateTimeOriginal":
            metadata["datetime_original"] = str(value)
        elif tag_name == "DateTimeDigitized":
            metadata["datetime_digitized"] = str(value)
        elif tag_name == "Make":
            metadata["make"] = str(value)
        elif tag_name == "Model":
            metadata["model"] = str(value)
        elif tag_name in ("Make", "Model"):
            pass
        elif tag_name == "Software":
            metadata["software"] = str(value)
        elif tag_name in ("Artist", "Author"):
            metadata["author"] = str(value)
        elif tag_name == "Copyright":
            metadata["copyright"] = str(value)
        elif tag_name == "ImageDescription":
            metadata["description"] = str(value)

    # Derive a convenience "device" field from make + model
    if metadata.get("make") or metadata.get("model"):
        parts = [metadata.get("make", ""), metadata.get("model", "")]
        metadata["device"] = " ".join(p for p in parts if p).strip()

    # Convert GPS coordinates
    if gps_data:
        lat = _dms_to_decimal(
            gps_data.get("GPSLatitude", ()),
            gps_data.get("GPSLatitudeRef", "N"),
        )
        lon = _dms_to_decimal(
            gps_data.get("GPSLongitude", ()),
            gps_data.get("GPSLongitudeRef", "E"),
        )
        if lat is not None and lon is not None:
            metadata["gps_latitude"] = lat
            metadata["gps_longitude"] = lon
        alt = gps_data.get("GPSAltitude")
        if alt is not None:
            try:
                metadata["gps_altitude"] = float(alt)
            except Exception:
                pass

    return metadata


class ExifExtractorNode:
    node_type = "exif_extractor"
    display_name = "EXIF Extractor"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "file_url": {
                "type": "string",
                "title": "File URL",
                "description": "URL of the image or document to extract EXIF metadata from.",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        # Gather URLs from config and from upstream inputs
        urls: list[str] = []
        config_url = (config.get("file_url") or "").strip()
        if config_url:
            urls.append(config_url)
        for item in inputs:
            url = (item.get("file_url") or "").strip()
            if url:
                urls.append(url)

        if not urls:
            return [{"error": "No file_url provided", "source": "exif_extractor", "reason": _REASON}]

        loop = asyncio.get_running_loop()
        results: list[dict] = []

        for url in urls:
            try:
                raw = await loop.run_in_executor(None, _fetch_file_bytes, url)
            except Exception as exc:
                results.append({
                    "file_url": url,
                    "error": f"Failed to fetch file: {exc}",
                    "source": "exif_extractor",
                    "reason": _REASON,
                })
                continue

            metadata = await loop.run_in_executor(None, _extract_exif_from_bytes, raw)
            results.append({
                "file_url": url,
                "metadata": metadata,
                "source": "exif_extractor",
                "reason": _REASON,
            })

        return results
