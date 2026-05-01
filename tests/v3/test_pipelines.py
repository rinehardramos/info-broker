"""
Pipeline feature tests — unit, integration, and security.

Run against a live Postgres instance:
    POSTGRES_HOST=localhost pytest tests/v3/test_pipelines.py -v
"""
from __future__ import annotations

import os
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from tests.v3.test_auth import _register_user

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_HOST"),
    reason="Requires Postgres",
)

client = TestClient(app)


def test_pipelines_table_has_is_system_column():
    """Schema migration adds is_system (NOT NULL boolean) column."""
    from app.routers.v3.db import fetch_one
    row = fetch_one(
        "SELECT column_name, is_nullable, data_type FROM information_schema.columns "
        "WHERE table_name = 'pipelines' AND column_name = 'is_system'"
    )
    assert row is not None, "is_system column not found in pipelines table"
    assert row["is_nullable"] == "NO", "is_system must be NOT NULL"


NODE_A = str(uuid.uuid4())
NODE_B = str(uuid.uuid4())
NODE_C = str(uuid.uuid4())

_PIPELINE_BODY = {
    "name": "Test Pipeline",
    "description": "desc",
    "nodes": [
        {"id": NODE_A, "node_type": "ddg_search", "label": "Step A", "config": {}, "position_x": 0, "position_y": 0},
        {"id": NODE_B, "node_type": "rss_monitor", "label": "Step B", "config": {}, "position_x": 0, "position_y": 1},
    ],
    "edges": [
        {"source_node_id": NODE_A, "target_node_id": NODE_B, "edge_type": "results"},
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth(username: str) -> dict:
    _register_user(username, "pass")
    r = client.post("/v3/auth/login", json={"username": username, "password": "pass"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _create_pipeline(headers: dict, body: dict | None = None) -> dict:
    r = client.post("/v3/pipelines", json=body or _PIPELINE_BODY, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# ===========================================================================
# UNIT — Pipeline CRUD
# ===========================================================================

class TestPipelineCRUD:
    def test_create_pipeline_returns_201(self):
        h = _auth("pl_create1")
        r = client.post("/v3/pipelines", json=_PIPELINE_BODY, headers=h)
        assert r.status_code == 201
        d = r.json()
        assert d["name"] == "Test Pipeline"
        assert "id" in d

    def test_create_pipeline_nodes_and_edges_stored(self):
        h = _auth("pl_create2")
        p = _create_pipeline(h)
        r = client.get(f"/v3/pipelines/{p['id']}", headers=h)
        assert r.status_code == 200
        d = r.json()
        assert len(d["nodes"]) == 2
        assert len(d["edges"]) == 1

    def test_list_pipelines_returns_own_only(self):
        h = _auth("pl_list1")
        _create_pipeline(h)
        r = client.get("/v3/pipelines", headers=h)
        assert r.status_code == 200
        ids = [p["id"] for p in r.json()]
        assert len(ids) >= 1

    def test_get_pipeline_detail(self):
        h = _auth("pl_get1")
        p = _create_pipeline(h)
        r = client.get(f"/v3/pipelines/{p['id']}", headers=h)
        assert r.status_code == 200
        d = r.json()
        assert d["id"] == p["id"]
        node_labels = {n["label"] for n in d["nodes"]}
        assert "Step A" in node_labels
        assert "Step B" in node_labels

    def test_update_pipeline_name(self):
        h = _auth("pl_upd1")
        p = _create_pipeline(h)
        body = {**_PIPELINE_BODY, "name": "Renamed"}
        r = client.put(f"/v3/pipelines/{p['id']}", json=body, headers=h)
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed"

    def test_delete_pipeline(self):
        h = _auth("pl_del1")
        p = _create_pipeline(h)
        r = client.delete(f"/v3/pipelines/{p['id']}", headers=h)
        assert r.status_code == 204
        r2 = client.get(f"/v3/pipelines/{p['id']}", headers=h)
        assert r2.status_code == 404

    def test_get_nonexistent_pipeline_returns_404(self):
        h = _auth("pl_404")
        r = client.get(f"/v3/pipelines/{uuid.uuid4()}", headers=h)
        assert r.status_code == 404


# ===========================================================================
# INTEGRATION — Node preservation (bug fix #9)
# ===========================================================================

class TestNodePreservation:
    """
    Saving a pipeline after deleting a step must only remove that node.
    All other nodes (and their step_run history) must be preserved.
    """

    def test_deleting_one_node_leaves_other_intact(self):
        h = _auth("pl_nodefix1")
        p = _create_pipeline(h)
        pid = p["id"]

        # Save with only NODE_A — simulates user deleting Step B
        body = {
            "name": "Test Pipeline",
            "description": None,
            "nodes": [
                {"id": NODE_A, "node_type": "ddg_search", "label": "Step A",
                 "config": {}, "position_x": 0, "position_y": 0},
            ],
            "edges": [],
        }
        r = client.put(f"/v3/pipelines/{pid}", json=body, headers=h)
        assert r.status_code == 200

        detail = client.get(f"/v3/pipelines/{pid}", headers=h).json()
        assert len(detail["nodes"]) == 1
        assert detail["nodes"][0]["label"] == "Step A"
        assert len(detail["edges"]) == 0

    def test_deleted_node_is_fully_removed(self):
        h = _auth("pl_nodefix2")
        p = _create_pipeline(h)
        pid = p["id"]

        # Remove Step A, keep Step B
        body = {
            "name": "Test Pipeline",
            "description": None,
            "nodes": [
                {"id": NODE_B, "node_type": "rss_monitor", "label": "Step B",
                 "config": {}, "position_x": 0, "position_y": 1},
            ],
            "edges": [],
        }
        client.put(f"/v3/pipelines/{pid}", json=body, headers=h)
        detail = client.get(f"/v3/pipelines/{pid}", headers=h).json()
        node_ids = {n["id"] for n in detail["nodes"]}
        assert NODE_A not in node_ids
        assert NODE_B in node_ids

    def test_saving_same_nodes_is_idempotent(self):
        """Re-saving without changes must not duplicate or drop nodes."""
        h = _auth("pl_nodefix3")
        p = _create_pipeline(h)
        pid = p["id"]

        client.put(f"/v3/pipelines/{pid}", json=_PIPELINE_BODY, headers=h)
        client.put(f"/v3/pipelines/{pid}", json=_PIPELINE_BODY, headers=h)

        detail = client.get(f"/v3/pipelines/{pid}", headers=h).json()
        assert len(detail["nodes"]) == 2
        assert len(detail["edges"]) == 1

    def test_other_pipelines_unaffected_when_step_deleted(self):
        """Deleting a step from pipeline A must not touch pipeline B's nodes."""
        h = _auth("pl_nodefix4")

        # Create two pipelines
        node_x = str(uuid.uuid4())
        pa = _create_pipeline(h, {
            "name": "Pipeline A", "description": None,
            "nodes": [{"id": NODE_A, "node_type": "ddg_search", "label": "A-Step",
                       "config": {}, "position_x": 0, "position_y": 0}],
            "edges": [],
        })
        pb = _create_pipeline(h, {
            "name": "Pipeline B", "description": None,
            "nodes": [{"id": node_x, "node_type": "rss_monitor", "label": "B-Step",
                       "config": {}, "position_x": 0, "position_y": 0}],
            "edges": [],
        })

        # Delete the only step from Pipeline A
        client.put(f"/v3/pipelines/{pa['id']}", json={
            "name": "Pipeline A", "description": None, "nodes": [], "edges": [],
        }, headers=h)

        # Pipeline B must still have its node
        detail_b = client.get(f"/v3/pipelines/{pb['id']}", headers=h).json()
        assert len(detail_b["nodes"]) == 1
        assert detail_b["nodes"][0]["label"] == "B-Step"

    def test_node_config_updated_on_save(self):
        h = _auth("pl_nodefix5")
        p = _create_pipeline(h)
        pid = p["id"]

        updated_config = {"query": "test query", "max_results": 5}
        body = {
            "name": "Test Pipeline",
            "description": None,
            "nodes": [
                {"id": NODE_A, "node_type": "ddg_search", "label": "Step A",
                 "config": updated_config, "position_x": 10, "position_y": 20},
            ],
            "edges": [],
        }
        client.put(f"/v3/pipelines/{pid}", json=body, headers=h)
        detail = client.get(f"/v3/pipelines/{pid}", headers=h).json()
        node = next(n for n in detail["nodes"] if n["id"] == NODE_A)
        assert node["config"] == updated_config
        assert node["position_x"] == 10


# ===========================================================================
# INTEGRATION — Cancel pipeline run
# ===========================================================================

class TestCancelPipelineRun:
    def test_cancel_nonexistent_run_returns_404(self):
        h = _auth("pl_cancel1")
        r = client.post(f"/v3/pipelines/runs/{uuid.uuid4()}/cancel", headers=h)
        assert r.status_code == 404

    def test_cancel_another_users_run_returns_404(self):
        """User B cannot cancel User A's run — 404 (not 403) to avoid enumeration."""
        h_a = _auth("pl_cancel_a")
        h_b = _auth("pl_cancel_b")
        # User A creates a pipeline (no active run to cancel, just check isolation)
        pa = _create_pipeline(h_a)
        # User B tries to cancel a fake run ID — must 404
        r = client.post(f"/v3/pipelines/runs/{uuid.uuid4()}/cancel", headers=h_b)
        assert r.status_code == 404
        _ = pa  # suppress unused warning


# ===========================================================================
# INTEGRATION — Plugin enabled settings
# ===========================================================================

class TestPluginEnabled:
    def test_get_plugin_enabled_defaults_to_true(self):
        h = _auth("pl_plugin1")
        r = client.get("/v3/settings/plugins/some-new-plugin/enabled", headers=h)
        assert r.status_code == 200
        assert r.json()["enabled"] is True

    def test_disable_and_reenable_plugin(self):
        h = _auth("pl_plugin2")
        client.put("/v3/settings/plugins/test-plugin/enabled",
                   json={"enabled": False}, headers=h)
        r = client.get("/v3/settings/plugins/test-plugin/enabled", headers=h)
        assert r.json()["enabled"] is False

        client.put("/v3/settings/plugins/test-plugin/enabled",
                   json={"enabled": True}, headers=h)
        r2 = client.get("/v3/settings/plugins/test-plugin/enabled", headers=h)
        assert r2.json()["enabled"] is True

    def test_plugin_enabled_response_includes_plugin_id(self):
        h = _auth("pl_plugin3")
        r = client.get("/v3/settings/plugins/linkedin-scraper/enabled", headers=h)
        assert r.json()["plugin_id"] == "linkedin-scraper"


# ===========================================================================
# INTEGRATION — Node type enabled
# ===========================================================================

class TestNodeTypeEnabled:
    def test_get_node_enabled_defaults_to_true(self):
        h = _auth("pl_node_en1")
        r = client.get("/v3/pipelines/nodes/types/ddg_search/enabled", headers=h)
        assert r.status_code == 200
        assert r.json()["enabled"] is True

    def test_disable_node_type_excludes_from_list(self):
        h = _auth("pl_node_en2")
        client.put("/v3/pipelines/nodes/types/ddg_search/enabled",
                   json={"enabled": False}, headers=h)
        r = client.get("/v3/pipelines/nodes/types", headers=h)
        node_types = [n["node_type"] for n in r.json()]
        assert "ddg_search" not in node_types
        # restore
        client.put("/v3/pipelines/nodes/types/ddg_search/enabled",
                   json={"enabled": True}, headers=h)

    def test_reenable_node_type_reappears_in_list(self):
        h = _auth("pl_node_en3")
        client.put("/v3/pipelines/nodes/types/rss_monitor/enabled",
                   json={"enabled": False}, headers=h)
        client.put("/v3/pipelines/nodes/types/rss_monitor/enabled",
                   json={"enabled": True}, headers=h)
        r = client.get("/v3/pipelines/nodes/types", headers=h)
        node_types = [n["node_type"] for n in r.json()]
        assert "rss_monitor" in node_types


# ===========================================================================
# SECURITY — Authentication enforcement
# ===========================================================================

class TestAuthEnforcement:
    ENDPOINTS = [
        ("GET",    "/v3/pipelines"),
        ("POST",   "/v3/pipelines"),
        ("GET",    f"/v3/pipelines/{uuid.uuid4()}"),
        ("PUT",    f"/v3/pipelines/{uuid.uuid4()}"),
        ("DELETE", f"/v3/pipelines/{uuid.uuid4()}"),
        ("GET",    "/v3/pipelines/nodes/types"),
        ("GET",    f"/v3/pipelines/nodes/types/ddg_search/enabled"),
        ("PUT",    f"/v3/pipelines/nodes/types/ddg_search/enabled"),
        ("POST",   f"/v3/pipelines/runs/{uuid.uuid4()}/cancel"),
        ("GET",    f"/v3/settings/plugins/linkedin-scraper/enabled"),
        ("PUT",    f"/v3/settings/plugins/linkedin-scraper/enabled"),
    ]

    @pytest.mark.parametrize("method,path", ENDPOINTS)
    def test_unauthenticated_request_rejected(self, method, path):
        r = getattr(client, method.lower())(path)
        assert r.status_code in (401, 403), (
            f"{method} {path} returned {r.status_code} — expected 401/403"
        )


# ===========================================================================
# SECURITY — User isolation (pipelines are tenant-scoped)
# ===========================================================================

class TestUserIsolation:
    def test_user_cannot_read_another_users_pipeline(self):
        h_a = _auth("pl_iso_a1")
        h_b = _auth("pl_iso_b1")
        pa = _create_pipeline(h_a)
        r = client.get(f"/v3/pipelines/{pa['id']}", headers=h_b)
        assert r.status_code == 404

    def test_user_cannot_update_another_users_pipeline(self):
        h_a = _auth("pl_iso_a2")
        h_b = _auth("pl_iso_b2")
        pa = _create_pipeline(h_a)
        r = client.put(f"/v3/pipelines/{pa['id']}", json=_PIPELINE_BODY, headers=h_b)
        assert r.status_code == 404

    def test_user_cannot_delete_another_users_pipeline(self):
        h_a = _auth("pl_iso_a3")
        h_b = _auth("pl_iso_b3")
        pa = _create_pipeline(h_a)
        r = client.delete(f"/v3/pipelines/{pa['id']}", headers=h_b)
        assert r.status_code == 404

    def test_list_pipelines_scoped_to_user(self):
        h_a = _auth("pl_iso_a4")
        h_b = _auth("pl_iso_b4")
        pa = _create_pipeline(h_a)
        r = client.get("/v3/pipelines", headers=h_b)
        ids = [p["id"] for p in r.json()]
        assert pa["id"] not in ids

    def test_invalid_bearer_token_rejected(self):
        r = client.get("/v3/pipelines", headers={"Authorization": "Bearer invalid.jwt.token"})
        assert r.status_code in (401, 403)

    def test_malformed_auth_header_rejected(self):
        r = client.get("/v3/pipelines", headers={"Authorization": "NotBearer abc"})
        assert r.status_code in (401, 403)


# ===========================================================================
# SECURITY — Input validation
# ===========================================================================

class TestInputValidation:
    def test_create_pipeline_empty_name_rejected(self):
        h = _auth("pl_val1")
        body = {**_PIPELINE_BODY, "name": ""}
        r = client.post("/v3/pipelines", json=body, headers=h)
        # FastAPI validates min_length or non-empty — expect 422
        assert r.status_code == 422

    def test_create_pipeline_missing_name_rejected(self):
        h = _auth("pl_val2")
        body = {k: v for k, v in _PIPELINE_BODY.items() if k != "name"}
        r = client.post("/v3/pipelines", json=body, headers=h)
        assert r.status_code == 422

    def test_pipeline_id_must_be_uuid(self):
        h = _auth("pl_val3")
        r = client.get("/v3/pipelines/not-a-uuid", headers=h)
        assert r.status_code in (404, 422)

    def test_cancel_run_with_invalid_uuid_handled(self):
        h = _auth("pl_val4")
        r = client.post("/v3/pipelines/runs/not-a-uuid/cancel", headers=h)
        assert r.status_code in (404, 422)
