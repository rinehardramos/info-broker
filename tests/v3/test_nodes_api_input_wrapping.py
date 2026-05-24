"""Regression tests for /v3/nodes/{node}/execute input wrapping (issue #111).

Ad-hoc/MCP callers pass a node's target as top-level payload fields rather than
an explicit ``inputs`` list. The endpoint must wrap recognised target fields
(query/domain/url/...) as a single upstream item so enrich nodes receive their
target — while leaving pure config-only payloads (research_goal, criteria, ...)
untouched so config-only nodes keep synthesising their own input.
"""
from __future__ import annotations

from app.routers.v3.nodes_api import _INPUT_TARGET_FIELDS, _wrap_payload_as_input


def test_explicit_inputs_are_never_overwritten():
    explicit = [{"query": "real input"}]
    assert _wrap_payload_as_input(explicit, {"domain": "x.com"}) is explicit


def test_domain_payload_is_wrapped():
    # The whois bug: domain stayed in config, inputs was empty -> zero items.
    assert _wrap_payload_as_input([], {"domain": "example.com"}) == [
        {"domain": "example.com"}
    ]


def test_query_payload_is_wrapped():
    assert _wrap_payload_as_input([], {"query": "openai", "max_results": 3}) == [
        {"query": "openai", "max_results": 3}
    ]


def test_urls_payload_is_wrapped():
    assert _wrap_payload_as_input([], {"urls": ["https://a.com"]}) == [
        {"urls": ["https://a.com"]}
    ]


def test_config_only_payload_is_not_wrapped():
    # research_goal is a config key, not a per-item target: must stay empty so
    # intelligent_search/ai_scoring/summarizer keep their empty-inputs behaviour.
    assert _wrap_payload_as_input([], {"research_goal": "find founders"}) == []
    assert _wrap_payload_as_input([], {"criteria": "relevance", "threshold": 50}) == []


def test_empty_body_is_not_wrapped():
    assert _wrap_payload_as_input([], {}) == []


def test_wrapped_item_is_a_copy_not_the_body():
    body = {"domain": "example.com"}
    wrapped = _wrap_payload_as_input([], body)
    wrapped[0]["domain"] = "mutated"
    assert body["domain"] == "example.com"  # config dict untouched


def test_config_keys_excluded_from_target_allowlist():
    # Guard against accidentally adding a config key that would regress the
    # empty-inputs-branching nodes.
    for forbidden in ("research_goal", "criteria", "instructions", "score_field"):
        assert forbidden not in _INPUT_TARGET_FIELDS
