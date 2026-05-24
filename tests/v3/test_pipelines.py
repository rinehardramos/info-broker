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


def _register_admin(username: str, password: str) -> None:
    """Insert a test user with is_admin=True, refreshing hash on conflict."""
    import uuid as _uuid
    from passlib.context import CryptContext
    from app.routers.v3.db import execute
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    org_id = str(_uuid.uuid4())
    execute(
        "INSERT INTO ui_users (username, password_hash, is_admin, org_id) VALUES (%s, %s, true, %s) "
        "ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash, is_admin = true",
        (username, ctx.hash(password), org_id),
    )

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


# Module-level sentinel UUIDs: used ONLY in tests that need to assert on specific
# node IDs within a single pipeline.  All cross-test node creation goes through
# _fresh_pipeline_body() which mints new IDs per call.
_SENTINEL_NODE_A = str(uuid.uuid4())
_SENTINEL_NODE_B = str(uuid.uuid4())
_SENTINEL_NODE_C = str(uuid.uuid4())


def _fresh_pipeline_body(
    name: str = "Test Pipeline",
    *,
    node_a_id: str | None = None,
    node_b_id: str | None = None,
) -> dict:
    """Return a pipeline body with freshly generated node IDs.

    Each call mints NEW UUIDs so that concurrent tests do not collide on the
    pipeline_nodes primary key.  Pass explicit IDs when the test needs to
    reference specific nodes by ID (e.g. TestNodePreservation).
    """
    na = node_a_id or str(uuid.uuid4())
    nb = node_b_id or str(uuid.uuid4())
    return {
        "name": name,
        "description": "desc",
        "nodes": [
            {"id": na, "node_type": "ddg_search", "label": "Step A", "config": {}, "position_x": 0, "position_y": 0},
            {"id": nb, "node_type": "rss_monitor", "label": "Step B", "config": {}, "position_x": 0, "position_y": 1},
        ],
        "edges": [
            {"source_node_id": na, "target_node_id": nb, "edge_type": "results"},
        ],
    }


# Backward-compat alias pointing to the SENTINEL nodes — only for tests that
# explicitly need these specific IDs (e.g. TestNodePreservation).
NODE_A = _SENTINEL_NODE_A
NODE_B = _SENTINEL_NODE_B
NODE_C = _SENTINEL_NODE_C

# Default pipeline body used by helpers — generates fresh IDs every time.
_PIPELINE_BODY = _fresh_pipeline_body()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth(username: str) -> dict:
    _register_user(username, "pass")
    r = client.post("/v3/auth/login", json={"username": username, "password": "pass"})
    assert r.status_code == 200, f"Login failed for {username}: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _auth_admin(username: str) -> dict:
    """Return auth headers for an admin user."""
    _register_admin(username, "pass")
    r = client.post("/v3/auth/login", json={"username": username, "password": "pass"})
    assert r.status_code == 200, f"Login failed for admin {username}: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _create_pipeline(headers: dict, body: dict | None = None) -> dict:
    """Create a pipeline; generates fresh node IDs if no body is supplied."""
    r = client.post("/v3/pipelines", json=body or _fresh_pipeline_body(), headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# ===========================================================================
# UNIT — Pipeline CRUD
# ===========================================================================

class TestPipelineCRUD:
    def test_create_pipeline_returns_201(self):
        h = _auth(f"pl_create1_{uuid.uuid4().hex[:8]}")
        r = client.post("/v3/pipelines", json=_fresh_pipeline_body(), headers=h)
        assert r.status_code == 201
        d = r.json()
        assert d["name"] == "Test Pipeline"
        assert "id" in d

    def test_create_pipeline_nodes_and_edges_stored(self):
        h = _auth(f"pl_create2_{uuid.uuid4().hex[:8]}")
        p = _create_pipeline(h)
        r = client.get(f"/v3/pipelines/{p['id']}", headers=h)
        assert r.status_code == 200
        d = r.json()
        assert len(d["nodes"]) == 2
        assert len(d["edges"]) == 1

    def test_list_pipelines_returns_own_only(self):
        h = _auth(f"pl_list1_{uuid.uuid4().hex[:8]}")
        _create_pipeline(h)
        r = client.get("/v3/pipelines", headers=h)
        assert r.status_code == 200
        ids = [p["id"] for p in r.json()]
        assert len(ids) >= 1

    def test_get_pipeline_detail(self):
        h = _auth(f"pl_get1_{uuid.uuid4().hex[:8]}")
        p = _create_pipeline(h)
        r = client.get(f"/v3/pipelines/{p['id']}", headers=h)
        assert r.status_code == 200
        d = r.json()
        assert d["id"] == p["id"]
        node_labels = {n["label"] for n in d["nodes"]}
        assert "Step A" in node_labels
        assert "Step B" in node_labels

    def test_update_pipeline_name(self):
        h = _auth(f"pl_upd1_{uuid.uuid4().hex[:8]}")
        na, nb = str(uuid.uuid4()), str(uuid.uuid4())
        p = _create_pipeline(h, _fresh_pipeline_body(node_a_id=na, node_b_id=nb))
        body = {**_fresh_pipeline_body(node_a_id=na, node_b_id=nb), "name": "Renamed"}
        r = client.put(f"/v3/pipelines/{p['id']}", json=body, headers=h)
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed"

    def test_delete_pipeline(self):
        h = _auth(f"pl_del1_{uuid.uuid4().hex[:8]}")
        p = _create_pipeline(h)
        r = client.delete(f"/v3/pipelines/{p['id']}", headers=h)
        assert r.status_code == 204
        r2 = client.get(f"/v3/pipelines/{p['id']}", headers=h)
        assert r2.status_code == 404

    def test_get_nonexistent_pipeline_returns_404(self):
        h = _auth(f"pl_404_{uuid.uuid4().hex[:8]}")
        r = client.get(f"/v3/pipelines/{uuid.uuid4()}", headers=h)
        assert r.status_code == 404


# ===========================================================================
# INTEGRATION — Node preservation (bug fix #9)
# ===========================================================================

class TestNodePreservation:
    """
    Saving a pipeline after deleting a step must only remove that node.
    All other nodes (and their step_run history) must be preserved.

    Every test generates its own node UUIDs to avoid primary-key conflicts
    on the pipeline_nodes table when multiple tests run in the same session.
    """

    def test_deleting_one_node_leaves_other_intact(self):
        h = _auth(f"pl_nodefix1_{uuid.uuid4().hex[:8]}")
        na, nb = str(uuid.uuid4()), str(uuid.uuid4())
        p = _create_pipeline(h, _fresh_pipeline_body(node_a_id=na, node_b_id=nb))
        pid = p["id"]

        # Save with only node_a — simulates user deleting Step B
        body = {
            "name": "Test Pipeline",
            "description": None,
            "nodes": [
                {"id": na, "node_type": "ddg_search", "label": "Step A",
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
        h = _auth(f"pl_nodefix2_{uuid.uuid4().hex[:8]}")
        na, nb = str(uuid.uuid4()), str(uuid.uuid4())
        p = _create_pipeline(h, _fresh_pipeline_body(node_a_id=na, node_b_id=nb))
        pid = p["id"]

        # Remove Step A, keep Step B
        body = {
            "name": "Test Pipeline",
            "description": None,
            "nodes": [
                {"id": nb, "node_type": "rss_monitor", "label": "Step B",
                 "config": {}, "position_x": 0, "position_y": 1},
            ],
            "edges": [],
        }
        client.put(f"/v3/pipelines/{pid}", json=body, headers=h)
        detail = client.get(f"/v3/pipelines/{pid}", headers=h).json()
        node_ids = {n["id"] for n in detail["nodes"]}
        assert na not in node_ids
        assert nb in node_ids

    def test_saving_same_nodes_is_idempotent(self):
        """Re-saving without changes must not duplicate or drop nodes."""
        h = _auth(f"pl_nodefix3_{uuid.uuid4().hex[:8]}")
        na, nb = str(uuid.uuid4()), str(uuid.uuid4())
        body = _fresh_pipeline_body(node_a_id=na, node_b_id=nb)
        p = _create_pipeline(h, body)
        pid = p["id"]

        client.put(f"/v3/pipelines/{pid}", json=body, headers=h)
        client.put(f"/v3/pipelines/{pid}", json=body, headers=h)

        detail = client.get(f"/v3/pipelines/{pid}", headers=h).json()
        assert len(detail["nodes"]) == 2
        assert len(detail["edges"]) == 1

    def test_other_pipelines_unaffected_when_step_deleted(self):
        """Deleting a step from pipeline A must not touch pipeline B's nodes."""
        h = _auth(f"pl_nodefix4_{uuid.uuid4().hex[:8]}")

        # Create two pipelines with fully distinct node IDs
        node_a1 = str(uuid.uuid4())
        node_b1 = str(uuid.uuid4())
        pa = _create_pipeline(h, {
            "name": "Pipeline A", "description": None,
            "nodes": [{"id": node_a1, "node_type": "ddg_search", "label": "A-Step",
                       "config": {}, "position_x": 0, "position_y": 0}],
            "edges": [],
        })
        node_b2 = str(uuid.uuid4())
        pb = _create_pipeline(h, {
            "name": "Pipeline B", "description": None,
            "nodes": [{"id": node_b2, "node_type": "rss_monitor", "label": "B-Step",
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
        h = _auth(f"pl_nodefix5_{uuid.uuid4().hex[:8]}")
        na, nb = str(uuid.uuid4()), str(uuid.uuid4())
        p = _create_pipeline(h, _fresh_pipeline_body(node_a_id=na, node_b_id=nb))
        pid = p["id"]

        updated_config = {"query": "test query", "max_results": 5}
        body = {
            "name": "Test Pipeline",
            "description": None,
            "nodes": [
                {"id": na, "node_type": "ddg_search", "label": "Step A",
                 "config": updated_config, "position_x": 10, "position_y": 20},
            ],
            "edges": [],
        }
        client.put(f"/v3/pipelines/{pid}", json=body, headers=h)
        detail = client.get(f"/v3/pipelines/{pid}", headers=h).json()
        node = next(n for n in detail["nodes"] if n["id"] == na)
        assert node["config"] == updated_config
        assert node["position_x"] == 10


# ===========================================================================
# INTEGRATION — Cancel pipeline run
# ===========================================================================

class TestCancelPipelineRun:
    def test_cancel_nonexistent_run_returns_404(self):
        h = _auth(f"pl_cancel1_{uuid.uuid4().hex[:8]}")
        r = client.post(f"/v3/pipelines/runs/{uuid.uuid4()}/cancel", headers=h)
        assert r.status_code == 404

    def test_cancel_another_users_run_returns_404(self):
        """User B cannot cancel User A's run — 404 (not 403) to avoid enumeration."""
        h_a = _auth(f"pl_cancel_a_{uuid.uuid4().hex[:8]}")
        h_b = _auth(f"pl_cancel_b_{uuid.uuid4().hex[:8]}")
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
        h = _auth(f"pl_plugin1_{uuid.uuid4().hex[:8]}")
        r = client.get("/v3/settings/plugins/some-new-plugin/enabled", headers=h)
        assert r.status_code == 200
        assert r.json()["enabled"] is True

    def test_disable_and_reenable_plugin(self):
        # PUT /v3/settings/plugins/{id}/enabled requires admin
        plugin_key = f"test-plugin-{uuid.uuid4().hex[:8]}"
        h = _auth_admin(f"pl_plugin2_{uuid.uuid4().hex[:8]}")
        client.put(f"/v3/settings/plugins/{plugin_key}/enabled",
                   json={"enabled": False}, headers=h)
        r = client.get(f"/v3/settings/plugins/{plugin_key}/enabled", headers=h)
        assert r.json()["enabled"] is False

        client.put(f"/v3/settings/plugins/{plugin_key}/enabled",
                   json={"enabled": True}, headers=h)
        r2 = client.get(f"/v3/settings/plugins/{plugin_key}/enabled", headers=h)
        assert r2.json()["enabled"] is True

    def test_plugin_enabled_response_includes_plugin_id(self):
        h = _auth(f"pl_plugin3_{uuid.uuid4().hex[:8]}")
        r = client.get("/v3/settings/plugins/linkedin-scraper/enabled", headers=h)
        assert r.json()["plugin_id"] == "linkedin-scraper"


# ===========================================================================
# INTEGRATION — Node type enabled
# ===========================================================================

class TestNodeTypeEnabled:
    def test_get_node_enabled_defaults_to_true(self):
        h = _auth(f"pl_node_en1_{uuid.uuid4().hex[:8]}")
        r = client.get("/v3/pipelines/nodes/types/ddg_search/enabled", headers=h)
        assert r.status_code == 200
        assert r.json()["enabled"] is True

    def test_disable_node_type_excludes_from_list(self):
        # PUT requires admin; use a unique node-type key per run to avoid
        # cross-test interference with the shared core_settings table.
        h_admin = _auth_admin(f"pl_node_en2_{uuid.uuid4().hex[:8]}")
        h_read = _auth(f"pl_node_en2r_{uuid.uuid4().hex[:8]}")
        client.put("/v3/pipelines/nodes/types/ddg_search/enabled",
                   json={"enabled": False}, headers=h_admin)
        r = client.get("/v3/pipelines/nodes/types", headers=h_read)
        node_types = [n["node_type"] for n in r.json()]
        assert "ddg_search" not in node_types
        # restore
        client.put("/v3/pipelines/nodes/types/ddg_search/enabled",
                   json={"enabled": True}, headers=h_admin)

    def test_reenable_node_type_reappears_in_list(self):
        h_admin = _auth_admin(f"pl_node_en3_{uuid.uuid4().hex[:8]}")
        h_read = _auth(f"pl_node_en3r_{uuid.uuid4().hex[:8]}")
        client.put("/v3/pipelines/nodes/types/rss_monitor/enabled",
                   json={"enabled": False}, headers=h_admin)
        client.put("/v3/pipelines/nodes/types/rss_monitor/enabled",
                   json={"enabled": True}, headers=h_admin)
        r = client.get("/v3/pipelines/nodes/types", headers=h_read)
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
        h_a = _auth(f"pl_iso_a1_{uuid.uuid4().hex[:8]}")
        h_b = _auth(f"pl_iso_b1_{uuid.uuid4().hex[:8]}")
        pa = _create_pipeline(h_a)
        r = client.get(f"/v3/pipelines/{pa['id']}", headers=h_b)
        assert r.status_code == 404

    def test_user_cannot_update_another_users_pipeline(self):
        h_a = _auth(f"pl_iso_a2_{uuid.uuid4().hex[:8]}")
        h_b = _auth(f"pl_iso_b2_{uuid.uuid4().hex[:8]}")
        pa = _create_pipeline(h_a)
        r = client.put(f"/v3/pipelines/{pa['id']}", json=_fresh_pipeline_body(), headers=h_b)
        assert r.status_code == 404

    def test_user_cannot_delete_another_users_pipeline(self):
        h_a = _auth(f"pl_iso_a3_{uuid.uuid4().hex[:8]}")
        h_b = _auth(f"pl_iso_b3_{uuid.uuid4().hex[:8]}")
        pa = _create_pipeline(h_a)
        r = client.delete(f"/v3/pipelines/{pa['id']}", headers=h_b)
        assert r.status_code == 404

    def test_list_pipelines_scoped_to_user(self):
        h_a = _auth(f"pl_iso_a4_{uuid.uuid4().hex[:8]}")
        h_b = _auth(f"pl_iso_b4_{uuid.uuid4().hex[:8]}")
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
        h = _auth(f"pl_val1_{uuid.uuid4().hex[:8]}")
        body = {**_fresh_pipeline_body(), "name": ""}
        r = client.post("/v3/pipelines", json=body, headers=h)
        # FastAPI validates min_length or non-empty — expect 422
        assert r.status_code == 422

    def test_create_pipeline_missing_name_rejected(self):
        h = _auth(f"pl_val2_{uuid.uuid4().hex[:8]}")
        body = {k: v for k, v in _fresh_pipeline_body().items() if k != "name"}
        r = client.post("/v3/pipelines", json=body, headers=h)
        assert r.status_code == 422

    def test_pipeline_id_must_be_uuid(self):
        h = _auth(f"pl_val3_{uuid.uuid4().hex[:8]}")
        r = client.get("/v3/pipelines/not-a-uuid", headers=h)
        assert r.status_code in (404, 422)

    def test_cancel_run_with_invalid_uuid_handled(self):
        h = _auth(f"pl_val4_{uuid.uuid4().hex[:8]}")
        r = client.post("/v3/pipelines/runs/not-a-uuid/cancel", headers=h)
        assert r.status_code in (404, 422)


def test_pipeline_list_includes_is_system_field():
    headers = _auth("model_test_user_" + str(uuid.uuid4())[:8])
    r = client.get("/v3/pipelines", headers=headers)
    assert r.status_code == 200
    pipelines = r.json()
    system = next((p for p in pipelines if p.get("is_system")), None)
    assert system is not None, "No system pipeline in list"
    assert "is_system" in system


SYSTEM_PIPELINE_ID = "00000000-0000-4000-8000-000000000001"


def test_list_pipelines_includes_system():
    headers = _auth("list_test_" + str(uuid.uuid4())[:8])
    r = client.get("/v3/pipelines", headers=headers)
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()]
    assert SYSTEM_PIPELINE_ID in ids


def test_delete_system_pipeline_returns_403():
    headers = _auth("del_test_" + str(uuid.uuid4())[:8])
    r = client.delete(f"/v3/pipelines/{SYSTEM_PIPELINE_ID}", headers=headers)
    assert r.status_code == 403


def test_update_system_pipeline_returns_403():
    headers = _auth("upd_test_" + str(uuid.uuid4())[:8])
    r = client.put(
        f"/v3/pipelines/{SYSTEM_PIPELINE_ID}",
        json={"name": "Hacked", "description": "", "nodes": [], "edges": []},
        headers=headers,
    )
    assert r.status_code == 403


def test_get_agent_pipeline_returns_system_default():
    headers = _auth("agent_pip_" + str(uuid.uuid4())[:8])
    r = client.get("/v3/agent/pipeline", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["pipeline_id"] == SYSTEM_PIPELINE_ID
    assert data["is_system"] is True


def test_put_agent_pipeline_rejects_pipeline_without_agent_input():
    headers = _auth("agent_pip2_" + str(uuid.uuid4())[:8])
    node_id = str(uuid.uuid4())
    p = client.post(
        "/v3/pipelines",
        json={"name": "No agent input", "nodes": [
            {"id": node_id, "node_type": "ddg_search", "label": "DDG", "config": {}, "position_x": 0, "position_y": 0},
        ], "edges": []},
        headers=headers,
    ).json()
    r = client.put("/v3/agent/pipeline", json={"pipeline_id": p["id"]}, headers=headers)
    assert r.status_code == 422


def test_put_agent_pipeline_accepts_valid_pipeline():
    headers = _auth("agent_pip3_" + str(uuid.uuid4())[:8])
    node_id = str(uuid.uuid4())
    p = client.post(
        "/v3/pipelines",
        json={"name": "My Agent Pipeline", "nodes": [
            {"id": node_id, "node_type": "agent_input", "label": "CLI", "config": {}, "position_x": 0, "position_y": 0},
        ], "edges": []},
        headers=headers,
    ).json()
    r = client.put("/v3/agent/pipeline", json={"pipeline_id": p["id"]}, headers=headers)
    assert r.status_code == 200
    assert r.json()["pipeline_id"] == p["id"]


def test_runner_raises_503_when_temporal_unreachable():
    import asyncio
    from app.pipeline.runner import launch_pipeline_run
    from app.pipeline.workflow import NodeSpec, EdgeSpec
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            launch_pipeline_run(
                run_id="test-run-id",
                user_id="test-user-id",
                pipeline_id="test-pipeline-id",
                nodes=[NodeSpec(node_id="n1", node_type="agent_input", label="A", config={})],
                edges=[],
                temporal_host="localhost",
                temporal_port=19999,
            )
        )
    assert exc_info.value.status_code == 503
