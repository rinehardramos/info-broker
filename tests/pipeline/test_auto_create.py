"""Tests for auto-create plugin pipeline."""
from __future__ import annotations
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from app.pipeline.auto_create import (
    assess_merit, generate_node_code, hot_register_node, auto_create_plugin,
    is_auto_create_enabled,
)
from app.pipeline.nodes.base import RunContext

def _arun(coro): return asyncio.run(coro)

def test_is_auto_create_enabled_default_false():
    with patch("app.pipeline.auto_create._get_setting", return_value=None):
        assert is_auto_create_enabled() is False

def test_is_auto_create_enabled_true():
    with patch("app.pipeline.auto_create._get_setting", return_value="true"):
        assert is_auto_create_enabled() is True

def test_assess_merit_returns_dict():
    with patch("app.pipeline.auto_create._call_llm") as m:
        m.return_value = '{"achievable": "HIGH", "api_url": "https://api.example.com", "auth_method": "api_key", "response_format": "JSON", "category": "source", "notes": "Free API"}'
        result = _arun(assess_merit("test_plugin", "A test plugin", "needed for testing"))
    assert result["achievable"] == "HIGH"
    assert result["api_url"] == "https://api.example.com"

def test_assess_merit_returns_low_on_error():
    with patch("app.pipeline.auto_create._call_llm", side_effect=Exception("LLM error")):
        result = _arun(assess_merit("test_plugin", "desc", "reason"))
    assert result["achievable"] == "LOW"

def test_generate_node_code_returns_string():
    with patch("app.pipeline.auto_create._call_llm") as m:
        m.return_value = '''
class TestPluginNode:
    node_type = "test_plugin"
    display_name = "Test Plugin"
    category = "source"
    config_schema = {"type": "object", "properties": {}}

    async def execute(self, config, inputs, context):
        return [{"source": "test_plugin", "reason": "test"}]
'''
        code = _arun(generate_node_code("test_plugin", "A test plugin", {"api_url": "x", "category": "source"}))
    assert "class TestPluginNode" in code
    assert "node_type" in code

def test_hot_register_node_success():
    code = '''
class AutoTestNode:
    node_type = "auto_test_node"
    display_name = "Auto Test"
    category = "source"
    config_schema = {"type": "object", "properties": {}}

    async def execute(self, config, inputs, context):
        return [{"source": "auto_test_node"}]
'''
    result = hot_register_node("auto_test_node", code)
    assert result["success"] is True
    assert result["node_type"] == "auto_test_node"
    # Clean up: unregister
    from app.pipeline.nodes import NodeRegistry
    if "auto_test_node" in NodeRegistry._nodes:
        del NodeRegistry._nodes["auto_test_node"]

def test_hot_register_node_bad_code():
    result = hot_register_node("bad_node", "this is not valid python }{")
    assert result["success"] is False
    assert "error" in result

def test_auto_create_plugin_full_flow():
    with (
        patch("app.pipeline.auto_create.is_auto_create_enabled", return_value=True),
        patch("app.pipeline.auto_create.assess_merit") as mock_merit,
        patch("app.pipeline.auto_create.generate_node_code") as mock_gen,
        patch("app.pipeline.auto_create.hot_register_node") as mock_reg,
    ):
        mock_merit.return_value = {"achievable": "HIGH", "api_url": "x", "category": "source"}
        mock_gen.return_value = "class FooNode:\n    node_type = 'foo'\n"
        mock_reg.return_value = {"success": True, "node_type": "foo"}

        result = _arun(auto_create_plugin("foo", "desc", "reason"))
    assert result["status"] == "auto_created"
    assert result["tool_name"] == "run_foo"

def test_auto_create_plugin_disabled():
    with patch("app.pipeline.auto_create.is_auto_create_enabled", return_value=False):
        result = _arun(auto_create_plugin("foo", "desc", "reason"))
    assert result["status"] == "disabled"

def test_auto_create_plugin_low_merit():
    with (
        patch("app.pipeline.auto_create.is_auto_create_enabled", return_value=True),
        patch("app.pipeline.auto_create.assess_merit") as mock_merit,
    ):
        mock_merit.return_value = {"achievable": "LOW", "notes": "Paywalled"}
        result = _arun(auto_create_plugin("foo", "desc", "reason"))
    assert result["status"] == "needs_manual"
