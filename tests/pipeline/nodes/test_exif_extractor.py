"""Tests for EXIF metadata extractor node."""
from __future__ import annotations
import asyncio
import io
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.exif_extractor import ExifExtractorNode, _extract_exif_from_bytes
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = ExifExtractorNode()
    assert node.node_type == "exif_extractor"
    assert node.category == "enrich"

def test_extract_exif_no_data():
    # Empty bytes should return empty metadata
    result = _extract_exif_from_bytes(b"not an image")
    assert result == {} or result.get("error")

def test_execute_fetches_url_and_extracts():
    fake_metadata = {"author": "John Doe", "software": "Photoshop"}
    with (
        patch("app.pipeline.nodes.exif_extractor._fetch_file_bytes", return_value=b"fake"),
        patch("app.pipeline.nodes.exif_extractor._extract_exif_from_bytes", return_value=fake_metadata),
    ):
        results = _arun(ExifExtractorNode().execute(
            {"file_url": "https://example.com/photo.jpg"}, [], CTX))
    assert results[0]["metadata"]["author"] == "John Doe"
    assert results[0]["source"] == "exif_extractor"

def test_execute_from_inputs():
    with (
        patch("app.pipeline.nodes.exif_extractor._fetch_file_bytes", return_value=b"fake"),
        patch("app.pipeline.nodes.exif_extractor._extract_exif_from_bytes", return_value={"device": "iPhone"}),
    ):
        results = _arun(ExifExtractorNode().execute(
            {}, [{"file_url": "https://example.com/img.png"}], CTX))
    assert results[0]["metadata"]["device"] == "iPhone"

def test_execute_no_url_error():
    results = _arun(ExifExtractorNode().execute({}, [], CTX))
    assert results[0].get("error")
