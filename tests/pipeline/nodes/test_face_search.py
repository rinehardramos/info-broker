"""Tests for face search (reverse facial recognition) node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.face_search import FaceSearchNode, _search_pimeyes
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = FaceSearchNode()
    assert node.node_type == "face_search"
    assert node.category == "enrich"

def test_search_pimeyes_returns_matches():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"results": [
        {"thumbnailUrl": "https://x.com/thumb.jpg", "sourceUrl": "https://x.com/page", "score": 0.95}
    ]}
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.post.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        result = _search_pimeyes("https://example.com/face.jpg", "fake-key")
    assert len(result) >= 1
    assert result[0]["source_url"] == "https://x.com/page"
    assert result[0]["confidence"] == 0.95

def test_execute_with_api_key():
    with (
        patch("app.pipeline.nodes.face_search._resolve_api_key", return_value="k"),
        patch("app.pipeline.nodes.face_search._search_pimeyes") as m,
    ):
        m.return_value = [{"source_url": "https://x.com", "confidence": 0.9, "thumbnail_url": "t"}]
        results = _arun(FaceSearchNode().execute(
            {"image_url": "https://example.com/face.jpg"}, [], CTX))
    assert len(results) >= 1
    assert results[0]["matches"][0]["confidence"] == 0.9

def test_execute_no_key_returns_note():
    with patch("app.pipeline.nodes.face_search._resolve_api_key", return_value=None):
        results = _arun(FaceSearchNode().execute(
            {"image_url": "https://example.com/face.jpg"}, [], CTX))
    assert "requires" in results[0].get("note", "").lower() or results[0].get("error")

def test_execute_no_image_error():
    results = _arun(FaceSearchNode().execute({}, [], CTX))
    assert results[0].get("error")
