"""Tests for Google Maps Places node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.google_maps_places import GoogleMapsPlacesNode, _search_places
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = GoogleMapsPlacesNode()
    assert node.node_type == "google_maps_places"
    assert node.category == "source"

def test_search_places_returns_results():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"places": [
        {"displayName": {"text": "Acme Coffee"}, "formattedAddress": "123 Main St",
         "rating": 4.5, "userRatingCount": 200, "types": ["cafe"],
         "googleMapsUri": "https://maps.google.com/place/123"},
    ]}
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.post.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        results = _search_places("Acme Coffee Manila", "fake-key", 5)
    assert len(results) == 1
    assert results[0]["name"] == "Acme Coffee"
    assert results[0]["rating"] == 4.5

def test_execute_with_key():
    with (
        patch("app.pipeline.nodes.google_maps_places._resolve_api_key", return_value="k"),
        patch("app.pipeline.nodes.google_maps_places._search_places") as m,
    ):
        m.return_value = [{"name": "Shop", "rating": 4.0, "source": "google_maps_places"}]
        results = _arun(GoogleMapsPlacesNode().execute({"query": "coffee manila"}, [], CTX))
    assert results[0]["name"] == "Shop"

def test_execute_no_key():
    with patch("app.pipeline.nodes.google_maps_places._resolve_api_key", return_value=None):
        results = _arun(GoogleMapsPlacesNode().execute({"query": "test"}, [], CTX))
    assert results[0].get("error")

def test_execute_no_query():
    results = _arun(GoogleMapsPlacesNode().execute({}, [], CTX))
    assert results[0].get("error")
