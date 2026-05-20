"""Lint test: every MCP tool exposed by mcp_server/server.py must be
registered in MCP_TOOL_CATEGORIES so it has a defined gating policy.

Without this, adding a new `@mcp.tool()` results in a silently-denied tool
(the brain can't call it, but no error is raised). This test catches the
omission at PR time so the developer can choose the right category before
landing the change.

To resolve a failure:
  1. Open `app/pipeline/runners/working_memory.py`
  2. Add `"<your_tool_name>": "<category>"` to MCP_TOOL_CATEGORIES
  3. Categories: source | lookup | enrich | score | knowledge | meta |
     destination | clarification — see the operator guide's
     "Categorization rules of thumb" table for guidance.
"""
from __future__ import annotations

import ast
from pathlib import Path

from app.pipeline.runners.working_memory import MCP_TOOL_CATEGORIES

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVER_PY = _REPO_ROOT / "mcp_server" / "server.py"


def _extract_mcp_tool_names(server_py: Path) -> set[str]:
    """Parse the MCP server source and return every function name decorated
    with @mcp.tool(...). Uses AST rather than regex so it stays correct as
    decorator syntax evolves (positional args, kwargs, etc.)."""
    tree = ast.parse(server_py.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            # @mcp.tool(...) or @mcp.tool
            call = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(call, ast.Attribute) and call.attr == "tool":
                value = call.value
                if isinstance(value, ast.Name) and value.id == "mcp":
                    names.add(node.name)
                    break
    return names


def test_mcp_server_has_some_tools_to_parse():
    """Smoke check: if this fails, the parser is broken or the file moved."""
    names = _extract_mcp_tool_names(_SERVER_PY)
    assert len(names) >= 20, f"expected at least 20 MCP tools, found {len(names)}"


def test_every_mcp_tool_is_categorized():
    """The load-bearing lint. Every @mcp.tool() must appear in
    MCP_TOOL_CATEGORIES — otherwise it's silently denied at the gate."""
    exposed = _extract_mcp_tool_names(_SERVER_PY)
    categorized = set(MCP_TOOL_CATEGORIES.keys())
    missing = exposed - categorized
    if missing:
        msg = (
            f"\n{len(missing)} MCP tool(s) exposed by mcp_server/server.py are "
            f"NOT in MCP_TOOL_CATEGORIES:\n"
            + "\n".join(f"  - {name}" for name in sorted(missing))
            + "\n\nWithout categorization these tools will be silently denied "
              "at every phase. Add each to MCP_TOOL_CATEGORIES in "
              "app/pipeline/runners/working_memory.py with one of: source, "
              "lookup, enrich, score, knowledge, meta, destination, "
              "clarification. See the operator guide for category rules."
        )
        raise AssertionError(msg)


def test_no_phantom_tools_in_registry():
    """Inverse: every name in MCP_TOOL_CATEGORIES must correspond to a real
    @mcp.tool() in server.py. Catches the case where a tool was removed but
    the registry entry was left behind (creates confusion but not a security
    issue — the entry is just inert).

    Allow-list a few entries that are intentionally registered but not yet
    wired (for forward-compatibility): none for now.
    """
    exposed = _extract_mcp_tool_names(_SERVER_PY)
    phantom = set(MCP_TOOL_CATEGORIES.keys()) - exposed
    assert not phantom, (
        f"\nMCP_TOOL_CATEGORIES contains {len(phantom)} entries that are NOT "
        f"defined as @mcp.tool() in mcp_server/server.py:\n"
        + "\n".join(f"  - {name}" for name in sorted(phantom))
        + "\n\nEither remove the registry entry or add the corresponding "
          "@mcp.tool() in server.py."
    )


def test_every_category_value_is_in_phase_allowed_categories_or_explicitly_excluded():
    """If a category exists in MCP_TOOL_CATEGORIES, it must either appear in
    at least one phase's allow-set, OR be explicitly excluded from all phases
    (meta, destination — admin/output tools the brain should never call).

    This catches the case where someone adds a new category to the type alias
    but forgets to update PHASE_ALLOWED_CATEGORIES.
    """
    from app.pipeline.runners.working_memory import PHASE_ALLOWED_CATEGORIES
    EXPLICITLY_EXCLUDED = {"meta", "destination"}   # never brain-callable
    used_cats = set(MCP_TOOL_CATEGORIES.values())
    cats_in_any_phase = set().union(*PHASE_ALLOWED_CATEGORIES.values())
    unhandled = used_cats - cats_in_any_phase - EXPLICITLY_EXCLUDED
    assert not unhandled, (
        f"\nCategories used by tools but not declared in any phase nor "
        f"explicitly excluded:\n"
        + "\n".join(f"  - {c}" for c in sorted(unhandled))
        + "\n\nEither add the category to one or more phases in "
          "PHASE_ALLOWED_CATEGORIES, or extend EXPLICITLY_EXCLUDED here if "
          "the category should be admin-only / never brain-callable."
    )
