from __future__ import annotations
from contextlib import contextmanager

from app.routers.v3.auth import _pwd


def _make_request():
    from starlette.requests import Request
    scope = {
        "type": "http", "method": "POST",
        "path": "/v3/auth/change-password",
        "headers": [], "query_string": b"",
        "server": ("testserver", 80), "client": ("127.0.0.1", 0),
    }
    return Request(scope)


def _make_response():
    """Empty fastapi Response — slowapi's rate-limit decorator requires one."""
    from fastapi import Response
    return Response()


@contextmanager
def _noop_rate_limit():
    from app.lib.rate_limit import limiter
    orig = limiter._inject_headers
    limiter._inject_headers = lambda *a, **kw: None
    try:
        yield
    finally:
        limiter._inject_headers = orig


def test_new_user_hash_is_argon2():
    h = _pwd.hash("CorrectHorse9!Battery")
    assert h.startswith("$argon2id$"), f"expected argon2id hash, got {h[:20]}"


def test_bcrypt_hash_still_verifies():
    from passlib.hash import bcrypt
    assert _pwd.verify("password123", bcrypt.hash("password123")) is True


def test_bcrypt_hash_needs_update():
    from passlib.hash import bcrypt
    assert _pwd.needs_update(bcrypt.hash("password123")) is True


def test_argon2_hash_does_not_need_update():
    assert _pwd.needs_update(_pwd.hash("CorrectHorse9!Battery")) is False


def test_auto_upgrade_on_login(monkeypatch):
    from passlib.hash import bcrypt as _bcrypt
    import app.routers.v3.auth as auth_mod

    old_hash = _bcrypt.hash("password123")
    user_row = {"id": "uid-1", "username": "u", "password_hash": old_hash, "is_active": True}
    updates = []
    monkeypatch.setattr(auth_mod, "fetch_one", lambda sql, params: dict(user_row))
    monkeypatch.setattr(auth_mod, "execute", lambda sql, params: updates.append((sql, params)))

    from app.routers.v3.models import LoginRequest
    auth_mod.login(LoginRequest(username="u", password="password123"))

    assert any("UPDATE ui_users SET password_hash" in sql for sql, _ in updates)
    new_hash = [p[0] for sql, p in updates if "UPDATE ui_users SET password_hash" in sql][0]
    assert new_hash.startswith("$argon2id$")


def test_change_password_rejects_weak():
    from pydantic import ValidationError
    from app.routers.v3.auth import ChangePasswordIn
    try:
        ChangePasswordIn(current_password="anything", new_password="short")
        assert False, "expected ValidationError"
    except ValidationError:
        pass


def test_change_password_rejects_wrong_current(monkeypatch):
    import pytest
    import app.routers.v3.auth as auth_mod
    from app.routers.v3.auth import ChangePasswordIn, change_password
    from fastapi import HTTPException

    row = {"id": "uid-1", "password_hash": _pwd.hash("OldPass9!Strong")}
    monkeypatch.setattr(auth_mod, "fetch_one", lambda sql, params: dict(row))
    monkeypatch.setattr(auth_mod, "execute", lambda sql, params: None)

    body = ChangePasswordIn(current_password="WrongCurrent9!", new_password="NewPass9!Strong")
    with _noop_rate_limit():
        with pytest.raises(HTTPException) as exc:
            change_password(request=_make_request(), response=_make_response(), body=body, user={"id": "uid-1"})
    assert exc.value.status_code == 401


def test_change_password_rejects_same(monkeypatch):
    import pytest
    import app.routers.v3.auth as auth_mod
    from app.routers.v3.auth import ChangePasswordIn, change_password
    from fastapi import HTTPException

    row = {"id": "uid-1", "password_hash": _pwd.hash("OldPass9!Strong")}
    monkeypatch.setattr(auth_mod, "fetch_one", lambda sql, params: dict(row))
    monkeypatch.setattr(auth_mod, "execute", lambda sql, params: None)

    body = ChangePasswordIn(current_password="OldPass9!Strong", new_password="OldPass9!Strong")
    with _noop_rate_limit():
        with pytest.raises(HTTPException) as exc:
            change_password(request=_make_request(), response=_make_response(), body=body, user={"id": "uid-1"})
    assert exc.value.status_code == 400


def test_change_password_success(monkeypatch):
    import app.routers.v3.auth as auth_mod
    from app.routers.v3.auth import ChangePasswordIn, change_password

    row = {"id": "uid-1", "password_hash": _pwd.hash("OldPass9!Strong")}
    updates = []
    monkeypatch.setattr(auth_mod, "fetch_one", lambda sql, params: dict(row))
    monkeypatch.setattr(auth_mod, "execute", lambda sql, params: updates.append((sql, params)))

    body = ChangePasswordIn(current_password="OldPass9!Strong", new_password="NewPass9!Strong")
    with _noop_rate_limit():
        result = change_password(request=_make_request(), response=_make_response(), body=body, user={"id": "uid-1"})

    assert result == {"ok": True}
    assert any("UPDATE ui_users SET password_hash" in sql for sql, _ in updates)
    new_hash = [p[0] for sql, p in updates if "UPDATE ui_users SET password_hash" in sql][0]
    assert new_hash.startswith("$argon2id$")
