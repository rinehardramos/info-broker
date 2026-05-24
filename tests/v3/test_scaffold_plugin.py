"""Tests for plugin scaffold generator endpoint (#47).

These tests use dependency_overrides so they run without Postgres.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Unit test: slug helper
# ---------------------------------------------------------------------------

def test_scaffold_returns_node_type_and_file():
    """_make_node_type_slug converts names to valid node_type slugs."""
    from app.routers.v3.pipelines import _make_node_type_slug

    assert _make_node_type_slug("My Cool Plugin") == "my_cool_plugin"
    assert _make_node_type_slug("twitter-scraper") == "twitter_scraper"
    assert _make_node_type_slug("LinkedIn Lookup") == "linkedin_lookup"

    slug = _make_node_type_slug("My Cool Plugin")
    assert "-" not in slug
    assert " " not in slug
    assert slug == slug.lower()


# ---------------------------------------------------------------------------
# Unit test: require_admin raises 403 for non-admin
# ---------------------------------------------------------------------------

def test_scaffold_requires_admin_raises_403():
    """Non-admin user should get 403 from require_admin dependency."""
    from fastapi import HTTPException
    from app.routers.v3.auth import require_admin

    non_admin = {"id": "u1", "is_admin": False, "org_id": "org1"}
    with pytest.raises(HTTPException) as exc_info:
        require_admin(non_admin)
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Unit test: scaffold endpoint rejects empty name
# ---------------------------------------------------------------------------

def test_scaffold_missing_name_returns_422():
    """Scaffold endpoint returns 422 when 'name' is absent or blank."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.routers.v3.auth import get_current_user, require_admin

    admin_user = {"id": "u1", "is_admin": True, "org_id": "org1"}

    def _override():
        return admin_user

    app.dependency_overrides[get_current_user] = _override
    app.dependency_overrides[require_admin] = _override

    try:
        client = TestClient(app)
        resp = client.post(
            "/v3/pipelines/plugin-requests/scaffold",
            json={"description": "no name given"},
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(require_admin, None)


# ---------------------------------------------------------------------------
# Unit test: _generate_stub produces correct file + class
# ---------------------------------------------------------------------------

def test_generate_stub_builds_correct_class():
    """_generate_stub writes a file that contains the correct class name and node_type."""
    import os
    import tempfile
    from unittest.mock import patch, MagicMock

    from app.routers.v3.pipelines import _generate_stub

    with tempfile.TemporaryDirectory() as tmpdir:
        # Build a realistic routers/v3/ and pipeline/nodes/auto/ layout inside tmpdir
        routers_v3_dir = os.path.join(tmpdir, "app", "routers", "v3")
        auto_dir = os.path.join(tmpdir, "app", "pipeline", "nodes", "auto")
        os.makedirs(routers_v3_dir, exist_ok=True)
        os.makedirs(auto_dir, exist_ok=True)

        # fake_pipelines_py lives in routers/v3/; _generate_stub resolves
        # auto_dir as ../../pipeline/nodes/auto relative to that file.
        fake_pipelines_py = os.path.join(routers_v3_dir, "pipelines.py")
        original_abspath = os.path.abspath

        def fake_abspath(p):
            if str(p).endswith("pipelines.py"):
                return fake_pipelines_py
            return original_abspath(p)

        import app.pipeline.nodes as _nodes_mod
        _nodes_mod.NodeRegistry.register = MagicMock()
        _nodes_mod.NodeRegistry.auto_discover = MagicMock()

        spec = {"name": "My Cool Plugin", "description": "Test desc", "category": "source"}

        with (
            patch("os.path.abspath", side_effect=fake_abspath),
            patch("app.routers.v3.pipelines._set_node_enabled"),
        ):
            file_path, class_name = _generate_stub("my_cool_plugin", spec)

        assert class_name == "MyCoolPluginNode"
        assert file_path.endswith("my_cool_plugin.py")
        assert os.path.exists(file_path)

        content = open(file_path).read()
        assert 'node_type = "my_cool_plugin"' in content
        assert "class MyCoolPluginNode" in content
        assert 'category = "source"' in content
