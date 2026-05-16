"""Catalog loader — discovery + validation for the four catalog kinds.

Discovery convention (NEW — does NOT alter existing app/pipeline/strategies/):
    Each catalog file lives under:
        app/pipeline/catalogs/registries/{strategies,tactics,techniques,modes}/

    Each module exposes a module-level constant matching the catalog kind:
        STRATEGY = {...}   for strategies
        TACTIC   = {...}   for tactics
        TECHNIQUE = {...}  for techniques
        MODE     = {...}   for modes

    Files that lack the expected constant are silently skipped (allows
    __init__.py and helper modules to coexist in the same directory).

Usage::

    from pathlib import Path
    from app.pipeline.catalogs.loader import load_catalog

    strategies = load_catalog(
        "strategy",
        Path("app/pipeline/catalogs/registries/strategies"),
    )
    # strategies["media_identification"] -> Strategy(...)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import ValidationError

from app.pipeline.catalogs.schemas import (
    OptimizationMode,
    Strategy,
    Tactic,
    Technique,
)

# ---------------------------------------------------------------------------
# Public error type
# ---------------------------------------------------------------------------


class CatalogValidationError(Exception):
    """Raised when a catalog entry fails Pydantic validation.

    Attributes:
        file:   path to the offending module file
        errors: list of Pydantic error dicts (from ValidationError.errors())
    """

    def __init__(self, file: Path, errors: list[dict]) -> None:
        self.file = file
        self.errors = errors
        detail = "; ".join(
            f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}" for e in errors
        )
        super().__init__(f"Catalog validation failed in {file}: {detail}")


# ---------------------------------------------------------------------------
# Internal type map
# ---------------------------------------------------------------------------

_KIND = Literal["strategy", "tactic", "technique", "mode"]

_SCHEMA_MAP = {
    "strategy": Strategy,
    "tactic": Tactic,
    "technique": Technique,
    "mode": OptimizationMode,
}

_CONSTANT_MAP: dict[str, str] = {
    "strategy": "STRATEGY",
    "tactic": "TACTIC",
    "technique": "TECHNIQUE",
    "mode": "MODE",
}

T = TypeVar("T", Strategy, Tactic, Technique, OptimizationMode)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_catalog(kind: _KIND, dir: Path) -> dict[str, T]:  # type: ignore[type-var]
    """Discover, import, and validate all catalog entries of *kind* in *dir*.

    Args:
        kind: One of ``"strategy"``, ``"tactic"``, ``"technique"``, ``"mode"``.
        dir:  Directory to scan.  Must exist; if empty, returns ``{}``.

    Returns:
        Mapping of ``entry.id → validated schema instance``.

    Raises:
        CatalogValidationError: on the first file that fails Pydantic validation.
        ValueError: if *kind* is not one of the four known catalog kinds.
    """
    if kind not in _SCHEMA_MAP:
        raise ValueError(
            f"Unknown catalog kind '{kind}'. Must be one of: {list(_SCHEMA_MAP)}"
        )

    if not dir.exists():
        return {}

    schema_cls = _SCHEMA_MAP[kind]
    constant_name = _CONSTANT_MAP[kind]
    catalog: dict[str, T] = {}  # type: ignore[assignment]

    for path in sorted(dir.glob("*.py")):
        if path.name.startswith("_"):
            # skip __init__.py and private helpers
            continue

        module = _import_module_from_path(path)
        raw = getattr(module, constant_name, None)
        if raw is None:
            # File doesn't expose the expected constant — skip silently
            continue

        try:
            entry = schema_cls.model_validate(raw)  # type: ignore[attr-defined]
        except ValidationError as exc:
            raise CatalogValidationError(path, exc.errors()) from exc

        catalog[entry.id] = entry  # type: ignore[assignment]

    return catalog


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _import_module_from_path(path: Path):
    """Import a Python file by path and return the module object.

    Uses a deterministic module name derived from the absolute path so
    repeated loads of the same file hit the sys.modules cache.
    """
    module_name = f"_catalog_registry_{path.stem}_{abs(hash(str(path.resolve())))}"
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module
