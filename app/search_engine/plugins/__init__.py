from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.search_engine.plugins.base import SearchPlugin

log = logging.getLogger(__name__)

_PLUGIN_CLASSES: list[type] = []


def _load_plugins() -> list[type]:
    if _PLUGIN_CLASSES:
        return _PLUGIN_CLASSES
    from app.search_engine.plugins.ddg import DdgPlugin
    _PLUGIN_CLASSES.extend([DdgPlugin])
    return _PLUGIN_CLASSES


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, SearchPlugin] = {}

    def auto_discover(self) -> None:
        for cls in _load_plugins():
            try:
                instance = cls()
                self._plugins[instance.name] = instance
            except Exception as exc:
                log.warning("Failed to instantiate %s: %s", cls, exc)

    def get(self, name: str) -> SearchPlugin | None:
        return self._plugins.get(name)

    def available(self) -> list[SearchPlugin]:
        return [p for p in self._plugins.values() if p.available()]

    def all(self) -> list[SearchPlugin]:
        return list(self._plugins.values())
