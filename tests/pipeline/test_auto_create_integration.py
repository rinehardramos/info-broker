"""Integration: auto-create wired into suggest_plugin flow."""
from unittest.mock import patch
import asyncio

from app.pipeline.auto_create import auto_create_plugin, is_auto_create_enabled


def _arun(coro):
    return asyncio.run(coro)


def test_auto_create_disabled_returns_status():
    with patch("app.pipeline.auto_create._get_setting", return_value="false"):
        result = _arun(auto_create_plugin("test_node", "A test", "Testing"))
    assert result["status"] == "disabled"


def test_auto_create_enabled_with_low_merit():
    with (
        patch("app.pipeline.auto_create._get_setting", return_value="true"),
        patch("app.pipeline.auto_create._call_llm", side_effect=Exception("no API")),
    ):
        result = _arun(auto_create_plugin("test_node", "A test", "Testing"))
    assert result["status"] == "needs_manual"


def test_auto_create_full_mock_flow():
    """Full flow: enabled -> HIGH merit -> generate -> register -> auto_created."""
    with (
        patch("app.pipeline.auto_create._get_setting", return_value="true"),
        patch("app.pipeline.auto_create._call_llm") as mock_llm,
        patch("app.pipeline.auto_create._persist_auto_node"),
    ):
        # First call: merit assessment
        # Second call: code generation
        mock_llm.side_effect = [
            '{"achievable": "HIGH", "api_url": "https://api.test.com", "auth_method": "none", "response_format": "JSON", "category": "source", "notes": "Free"}',
            '''
class AutoTestPluginNode:
    node_type = "auto_test_plugin"
    display_name = "Auto Test Plugin"
    category = "source"
    config_schema = {"type": "object", "properties": {}}

    async def execute(self, config, inputs, context):
        return [{"source": "auto_test_plugin", "reason": "test"}]
''',
        ]
        result = _arun(auto_create_plugin("auto_test_plugin", "A test plugin", "Testing"))

    assert result["status"] == "auto_created"
    assert result["tool_name"] == "run_auto_test_plugin"

    # Clean up
    from app.pipeline.nodes import NodeRegistry
    if "auto_test_plugin" in NodeRegistry._nodes:
        del NodeRegistry._nodes["auto_test_plugin"]
