import pytest
from app.search_engine.plugins.base import SearchPlugin, PluginResult


class MinimalPlugin:
    name = "minimal"
    description = "test"
    requires_api_key = False
    config_schema: dict = {}

    async def search(self, query, *, max_results=5, config=None):
        return []

    def available(self):
        return True

    def configure(self, config: dict) -> None:
        pass


def test_plugin_has_config_schema():
    p = MinimalPlugin()
    assert isinstance(p.config_schema, dict)


def test_plugin_has_configure():
    p = MinimalPlugin()
    p.configure({"key": "value"})  # must not raise
