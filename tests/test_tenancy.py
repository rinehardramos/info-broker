from __future__ import annotations
import pytest


def test_org_scope_clause_superadmin_empty():
    from app.routers.v3.tenancy import org_scope_clause
    clause, params = org_scope_clause({"id": "u1", "org_id": "o1", "is_admin": True})
    assert clause == ""
    assert params == []


def test_org_scope_clause_regular_user():
    from app.routers.v3.tenancy import org_scope_clause
    clause, params = org_scope_clause({"id": "u1", "org_id": "o1", "is_admin": False})
    assert clause == "AND org_id = %s"
    assert params == ["o1"]


def test_user_a_cannot_see_org_b_in_sql():
    from app.routers.v3.tenancy import org_scope_clause
    user_a = {"id": "ua", "org_id": "org-a", "is_admin": False}
    clause, params = org_scope_clause(user_a)
    sql = f"SELECT * FROM research_sources WHERE id = %s {clause}"
    assert "org_id = %s" in sql
    assert params == ["org-a"]


def test_superadmin_gets_no_clause():
    from app.routers.v3.tenancy import org_scope_clause
    admin = {"id": "ux", "org_id": "org-x", "is_admin": True}
    clause, params = org_scope_clause(admin)
    sql = f"SELECT * FROM pipelines WHERE id = %s {clause}"
    assert "org_id" not in sql
    assert params == []
