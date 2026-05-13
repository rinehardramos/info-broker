from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.routers.v3.auth import require_admin


def test_require_admin_raises_403_for_non_admin():
    non_admin_user = {"id": "u1", "username": "testuser", "is_admin": False}
    with pytest.raises(HTTPException) as exc:
        require_admin(non_admin_user)
    assert exc.value.status_code == 403


def test_require_admin_passes_for_admin():
    admin_user = {"id": "u1", "username": "admin", "is_admin": True}
    result = require_admin(admin_user)
    assert result["is_admin"] is True


def test_require_admin_raises_403_when_field_missing():
    user_without_field = {"id": "u1", "username": "testuser"}
    with pytest.raises(HTTPException) as exc:
        require_admin(user_without_field)
    assert exc.value.status_code == 403
