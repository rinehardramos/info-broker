"""Auto-create plugin pipeline — LLM-powered node generation + hot registration."""

from __future__ import annotations
import json
import logging
import os
from typing import Any

log = logging.getLogger(__name__)

# Template: an existing simple node for the LLM to follow
_NODE_TEMPLATE = '''"""Auto-generated pipeline node: {name}."""

from __future__ import annotations
import asyncio
import logging
import httpx
from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)
_REASON = "{description}"

class {class_name}:
    node_type = "{name}"
    display_name = "{display_name}"
    category = "{category}"
    config_schema = {{
        "type": "object",
        "properties": {{
            "query": {{"type": "string", "title": "Query"}},
        }},
        "required": [],
    }}

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        query = (config.get("query") or "").strip()
        if not query:
            for item in inputs:
                query = (item.get("query") or item.get("name") or "").strip()
                if query:
                    break
        if not query:
            return [{{"error": "No query provided", "source": "{name}", "reason": _REASON}}]

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _fetch, query)

def _fetch(query: str) -> list[dict]:
    try:
        with httpx.Client(timeout=20.0) as client:
            # TODO: implement actual API call
            return [{{"query": query, "source": "{name}", "reason": _REASON, "note": "Auto-generated stub"}}]
    except Exception as exc:
        log.warning("{name}: error: %s", exc)
        return [{{"error": str(exc), "source": "{name}", "reason": _REASON}}]
'''


def is_auto_create_enabled() -> bool:
    """Check if auto_create_techniques is toggled ON in settings."""
    val = _get_setting("auto_create_techniques")
    return val == "true" if val else False


def _get_setting(key: str) -> str | None:
    """Read a setting from core_settings DB table."""
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one("SELECT value FROM core_settings WHERE key = %s", (key,))
        return row["value"] if row else None
    except Exception:
        return None


async def assess_merit(name: str, description: str, reason: str) -> dict:
    """LLM-powered merit assessment. Returns achievability rating + API details."""
    prompt = f"""Evaluate if this plugin can be automatically implemented.

Plugin: {name}
Description: {description}
Reason: {reason}

Assess:
1. Is there a free/cheap public API? (provide URL if yes)
2. What authentication is needed? (none / api_key / oauth)
3. Expected response format? (JSON / HTML / XML)

Rate: HIGH (free API), MEDIUM (scrapeable), LOW (paywalled/impossible)

Output ONLY JSON: {{"achievable": "HIGH|MEDIUM|LOW", "api_url": "...", "auth_method": "...", "response_format": "...", "category": "source|enrich", "notes": "..."}}"""

    try:
        response = await _call_llm(prompt)
        # Parse JSON from response
        start = response.index("{")
        end = response.rindex("}") + 1
        return json.loads(response[start:end])
    except Exception as exc:
        log.warning("Merit assessment failed: %s", exc)
        return {"achievable": "LOW", "notes": f"Assessment failed: {exc}"}


async def generate_node_code(name: str, description: str, merit: dict) -> str:
    """LLM-powered code generation. Returns Python module source code."""
    class_name = "".join(w.capitalize() for w in name.split("_")) + "Node"
    display_name = name.replace("_", " ").title()
    category = merit.get("category", "source")

    prompt = f"""Generate a Python pipeline node for info-broker.

Follow this EXACT pattern:
{_NODE_TEMPLATE.format(
    name=name, description=description, class_name=class_name,
    display_name=display_name, category=category,
)}

Make the _fetch() function actually call this API:
- URL: {merit.get('api_url', 'unknown')}
- Auth: {merit.get('auth_method', 'none')}
- Format: {merit.get('response_format', 'JSON')}

Output ONLY the Python code. No markdown. No explanation."""

    try:
        code = await _call_llm(prompt)
        # Strip markdown fences if present
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0]
        elif "```" in code:
            code = code.split("```")[1].split("```")[0]
        return code.strip()
    except Exception as exc:
        log.warning("Code generation failed: %s", exc)
        # Return the template as fallback
        return _NODE_TEMPLATE.format(
            name=name, description=description, class_name=class_name,
            display_name=display_name, category=category,
        )


def hot_register_node(name: str, code: str) -> dict:
    """Compile and register a node from source code. Returns success/failure dict."""
    try:
        # Compile check
        compiled = compile(code, f"<auto:{name}>", "exec")

        # Execute in isolated namespace
        namespace: dict[str, Any] = {}
        exec(compiled, namespace)  # noqa: S102

        # Find the node class (look for class with node_type attribute)
        node_class = None
        for obj in namespace.values():
            if isinstance(obj, type) and hasattr(obj, "node_type") and hasattr(obj, "execute"):
                node_class = obj
                break

        if not node_class:
            return {"success": False, "error": "No PipelineNode class found in generated code"}

        # Register
        from app.pipeline.nodes import NodeRegistry
        instance = node_class()
        NodeRegistry.register(instance)

        # Write to auto/ directory for persistence
        _persist_auto_node(name, code)

        log.info("Auto-created and registered node: %s", name)
        return {"success": True, "node_type": instance.node_type}

    except SyntaxError as exc:
        return {"success": False, "error": f"Syntax error: {exc}"}
    except Exception as exc:
        return {"success": False, "error": f"Registration failed: {exc}"}


def _persist_auto_node(name: str, code: str) -> None:
    """Write auto-created node to disk for persistence across restarts."""
    auto_dir = os.path.join(os.path.dirname(__file__), "nodes", "auto")
    os.makedirs(auto_dir, exist_ok=True)

    init_path = os.path.join(auto_dir, "__init__.py")
    if not os.path.exists(init_path):
        with open(init_path, "w") as f:
            f.write("")

    path = os.path.join(auto_dir, f"{name}.py")
    with open(path, "w") as f:
        f.write(code)
    log.info("Persisted auto-created node to %s", path)


async def auto_create_plugin(name: str, description: str, reason: str) -> dict:
    """Main entry point: assess merit, generate code, register, return status."""
    if not is_auto_create_enabled():
        return {"status": "disabled", "message": "Auto-create is toggled OFF in settings"}

    # Step 1: Assess merit
    merit = await assess_merit(name, description, reason)
    if merit.get("achievable") == "LOW":
        return {"status": "needs_manual", "message": f"Low achievability: {merit.get('notes', '')}"}

    # Step 2: Generate code
    code = await generate_node_code(name, description, merit)

    # Step 3: Hot register
    result = hot_register_node(name, code)
    if not result["success"]:
        return {"status": "auto_create_failed", "error": result["error"]}

    return {
        "status": "auto_created",
        "tool_name": f"run_{name}",
        "node_type": result["node_type"],
        "message": f"Auto-created {name} and registered as run_{name}",
    }


async def _call_llm(prompt: str) -> str:
    """Call LLM for merit assessment or code generation."""
    try:
        import anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            try:
                from app.routers.v3.db import fetch_one
                row = fetch_one("SELECT value FROM core_settings WHERE key = 'anthropic_api_key'", ())
                if row:
                    api_key = row["value"]
            except Exception:
                pass

        if not api_key:
            raise ValueError("No Anthropic API key available")

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception as exc:
        log.warning("LLM call failed: %s", exc)
        raise
