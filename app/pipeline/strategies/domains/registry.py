"""Domain sub-strategy registry with lazy auto-discovery."""

from __future__ import annotations

import importlib
import importlib.util
import pathlib
from typing import Any

_DOMAINS_DIR = pathlib.Path(__file__).parent

# Cache: {category: {name: module_attrs}}
_registry: dict[str, dict[str, dict[str, Any]]] | None = None

_REQUIRED_ATTRS = ("CATEGORY", "NAME", "DISPLAY_NAME", "DESCRIPTION", "STRATEGY", "SELECTORS")


def _load_registry() -> dict[str, dict[str, dict[str, Any]]]:
    """Scan category directories and load all sub-strategy modules."""
    registry: dict[str, dict[str, dict[str, Any]]] = {}

    for category_dir in sorted(_DOMAINS_DIR.iterdir()):
        if not category_dir.is_dir():
            continue
        if category_dir.name.startswith("_"):
            continue

        category_entries: dict[str, dict[str, Any]] = {}

        for py_file in sorted(category_dir.glob("*.py")):
            if py_file.name == "__init__.py":
                continue

            module_name = (
                f"app.pipeline.strategies.domains.{category_dir.name}.{py_file.stem}"
            )
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                # Fall back to spec-based loading when the package is not installed
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)  # type: ignore[union-attr]

            # Only register modules that have all required attributes
            if not all(hasattr(module, attr) for attr in _REQUIRED_ATTRS):
                continue

            name: str = module.NAME  # type: ignore[attr-defined]
            category_entries[name] = {
                "name": name,
                "display_name": module.DISPLAY_NAME,  # type: ignore[attr-defined]
                "description": module.DESCRIPTION,  # type: ignore[attr-defined]
                "strategy": module.STRATEGY,  # type: ignore[attr-defined]
                "selectors": list(module.SELECTORS),  # type: ignore[attr-defined]
                "category": module.CATEGORY,  # type: ignore[attr-defined]
            }

        if category_entries:
            registry[category_dir.name] = category_entries

    return registry


def _get_registry() -> dict[str, dict[str, dict[str, Any]]]:
    global _registry
    if _registry is None:
        _registry = _load_registry()
    return _registry


def get_substrategy(category: str, name: str) -> str:
    """Return strategy text for a sub-strategy, or empty string if not found."""
    registry = _get_registry()
    entry = registry.get(category, {}).get(name)
    if entry is None:
        return ""
    return entry["strategy"]


def list_substrategies(category: str) -> list[dict]:
    """Return [{name, display_name, description}] for all sub-strategies in a category."""
    registry = _get_registry()
    entries = registry.get(category, {})
    return [
        {
            "name": entry["name"],
            "display_name": entry["display_name"],
            "description": entry["description"],
        }
        for entry in entries.values()
    ]


def get_substrategy_selectors(category: str, name: str) -> list[str]:
    """Return selector list for a sub-strategy, or empty list if not found."""
    registry = _get_registry()
    entry = registry.get(category, {}).get(name)
    if entry is None:
        return []
    return entry["selectors"]
