"""Unit tests for the LinkedInProfileNode (harvestapi actor)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from app.pipeline.nodes.linkedin_profile import (
    LinkedInProfileNode,
    _map_item,
)
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")

_PROFILE_BASE = "https://linkedin.com/in"


def _arun(coro):
    return asyncio.run(coro)


def _make_apify_mock(items, run_meta=None):
    if run_meta is None:
        run_meta = {"defaultDatasetId": "ds-123"}
    mock_dataset = MagicMock()
    mock_dataset.iterate_items.return_value = iter(items)
    mock_actor_handle = MagicMock()
    mock_actor_handle.call.return_value = run_meta
    mock_instance = MagicMock()
    mock_instance.actor.return_value = mock_actor_handle
    mock_instance.dataset.return_value = mock_dataset
    MockClass = MagicMock(return_value=mock_instance)
    return MockClass, mock_instance


def test_map_item_full_profile():
    item = {
        "profileUrl": f"{_PROFILE_BASE}/juan",
        "fullName": "Juan dela Cruz",
        "firstName": "Juan",
        "lastName": "dela Cruz",
        "headline": "CTO at TechPH",
        "location": "Manila, Philippines",
        "currentPosition": [{"title": "CTO", "companyName": "TechPH"}],
    }
    r = _map_item(item)
    assert r["full_name"] == "Juan dela Cruz"
    assert r["title"] == "CTO"
    assert r["company"] == "TechPH"
    assert r["source"] == "linkedin_profile"


def test_map_item_fallback_to_headline():
    item = {"fullName": "Maria", "headline": "Founder", "location": "Cebu", "currentPosition": []}
    r = _map_item(item)
    assert r["title"] == "Founder"
    assert r["company"] == ""


def test_map_item_minimal():
    r = _map_item({})
    assert r["full_name"] == ""
    assert r["source"] == "linkedin_profile"
    assert "id" in r


def test_map_item_dict_location():
    item = {"fullName": "Test", "location": {"linkedinText": "Manila, PH"}}
    r = _map_item(item)
    assert r["location"] == "Manila, PH"


def test_map_item_email_from_emails_list():
    item = {"fullName": "X", "emails": ["a@example.com"]}
    r = _map_item(item)
    assert r["email"] == "a@example.com"


def test_node_metadata():
    node = LinkedInProfileNode()
    assert node.node_type == "linkedin_profile"
    assert node.display_name == "LinkedIn Profile Search"
    assert node.category == "source"
    props = node.config_schema["properties"]
    assert "job_titles" in props
    assert "locations" in props
    assert "max_results" in props
    assert "scraper_mode" in props


def test_execute_with_job_titles():
    node = LinkedInProfileNode()
    items = [{"profileUrl": f"{_PROFILE_BASE}/jsmith", "fullName": "John Smith"}]
    MockApify, mock_instance = _make_apify_mock(items)
    with (
        patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake-key"),
        patch("apify_client.ApifyClient", MockApify),
    ):
        results = _arun(node.execute(
            {"job_titles": "CEO, CTO", "locations": "Philippines"}, [], CTX,
        ))
    run_input = mock_instance.actor.return_value.call.call_args[1]["run_input"]
    assert run_input["currentJobTitles"] == ["CEO", "CTO"]
    assert run_input["locations"] == ["Philippines"]
    assert len(results) == 1
    assert results[0]["source"] == "linkedin_profile"


def test_execute_with_query_fallback():
    node = LinkedInProfileNode()
    MockApify, mock_instance = _make_apify_mock([{"fullName": "Test"}])
    with (
        patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake-key"),
        patch("apify_client.ApifyClient", MockApify),
    ):
        _arun(node.execute({"query": "VP Engineering"}, [], CTX))
    run_input = mock_instance.actor.return_value.call.call_args[1]["run_input"]
    assert run_input["currentJobTitles"] == ["VP Engineering"]


def test_execute_without_api_key():
    node = LinkedInProfileNode()
    with patch(
        "app.pipeline.nodes.apify_actor._resolve_api_key",
        side_effect=RuntimeError("Apify API key not found"),
    ):
        results = _arun(node.execute({}, [], CTX))
    assert len(results) == 1
    assert results[0]["error_flagged"] is True
    assert "Apify API key" in results[0]["content"]


def test_execute_maps_items_correctly():
    node = LinkedInProfileNode()
    profile_url = f"{_PROFILE_BASE}/anna"
    items = [{
        "profileUrl": profile_url,
        "fullName": "Anna Reyes",
        "firstName": "Anna",
        "lastName": "Reyes",
        "headline": "VP Engineering",
        "location": "Manila",
        "currentPosition": [{"title": "VP Engineering", "companyName": "MegaCorp"}],
    }]
    MockApify, _ = _make_apify_mock(items)
    with (
        patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake-key"),
        patch("apify_client.ApifyClient", MockApify),
    ):
        results = _arun(node.execute({}, [], CTX))
    assert len(results) == 1
    r = results[0]
    assert r["full_name"] == "Anna Reyes"
    assert r["title"] == "VP Engineering"
    assert r["company"] == "MegaCorp"
    assert r["linkedin_url"] == profile_url
    assert r["source"] == "linkedin_profile"


def test_execute_actor_call_fails():
    node = LinkedInProfileNode()
    mock_actor_handle = MagicMock()
    mock_actor_handle.call.side_effect = Exception("Network error")
    mock_instance = MagicMock()
    mock_instance.actor.return_value = mock_actor_handle
    MockApify = MagicMock(return_value=mock_instance)
    with (
        patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake-key"),
        patch("apify_client.ApifyClient", MockApify),
    ):
        results = _arun(node.execute({}, [], CTX))
    assert len(results) == 1
    assert results[0]["error_flagged"] is True
    assert results[0]["source"] == "linkedin_profile"
