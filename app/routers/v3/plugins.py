from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_one
from app.routers.v3.models import PluginConfigIn, PluginConfigOut
from app.search_engine.plugins import PluginRegistry

router = APIRouter(prefix="/v3/plugins", tags=["v3-plugins"])

_registry = PluginRegistry()
_registry.auto_discover()


@router.get("", response_model=list[dict])
def list_plugins(user: dict = Depends(get_current_user)):
    """List plugins visible to the current user.

    All code-bundled plugins are `public` (anyone can use). Future
    org-scoped plugins (created via the plugin-request flow) carry a
    `visibility='private'` tag and an `org_id`; we filter those so a user
    only sees private plugins from their own org.
    """
    plugins: list[dict] = []
    user_org = str(user.get("org_id") or "")
    for p in _registry.all():
        info = {
            "name":             p.name,
            "description":      p.description,
            "requires_api_key": p.requires_api_key,
            "available":        p.available(),
            # Bundled plugins are always public; per-plugin override via
            # an optional `visibility` attribute on the plugin class.
            "visibility":       getattr(p, "visibility", "public"),
            "org_id":           getattr(p, "org_id", None),
        }
        if info["visibility"] == "private":
            owner_org = info["org_id"] or ""
            if owner_org and owner_org != user_org and not user.get("is_admin"):
                continue
        plugins.append(info)
    return plugins


@router.get("/{name}/schema")
def get_plugin_schema(name: str, user: dict = Depends(get_current_user)):
    plugin = _registry.get(name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    return plugin.config_schema or {"type": "object", "properties": {}}


@router.get("/{name}/config", response_model=PluginConfigOut)
def get_plugin_config(name: str, user: dict = Depends(get_current_user)):
    row = fetch_one(
        "SELECT * FROM plugin_configs WHERE user_id = %s AND plugin_name = %s",
        (str(user["id"]), name),
    )
    return PluginConfigOut(plugin_name=name, config=row["config"] if row else {})


@router.put("/{name}/config", response_model=PluginConfigOut)
def save_plugin_config(name: str, body: PluginConfigIn, user: dict = Depends(get_current_user)):
    plugin = _registry.get(name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    execute(
        """
        INSERT INTO plugin_configs (user_id, plugin_name, config)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, plugin_name) DO UPDATE
        SET config = EXCLUDED.config, updated_at = now()
        """,
        (str(user["id"]), name, json.dumps(body.config)),
    )
    return PluginConfigOut(plugin_name=name, config=body.config)
