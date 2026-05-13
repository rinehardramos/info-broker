from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone


def _make_token(payload: dict) -> str:
    from app.routers.v3.auth import _ALGO, _SECRET
    from jose import jwt
    return jwt.encode(payload, _SECRET, algorithm=_ALGO)


def _call_get_current_user(token: str):
    from app.routers.v3.auth import get_current_user
    from fastapi.security import HTTPAuthorizationCredentials
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    return get_current_user(credentials=creds)


def test_token_without_exp_rejected():
    from fastapi import HTTPException
    token = _make_token({"sub": "u1", "iat": 1, "type": "access"})
    with pytest.raises((HTTPException, Exception)):
        _call_get_current_user(token)


def test_expired_token_rejected():
    from fastapi import HTTPException
    past = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
    token = _make_token({"sub": "u1", "iat": past - 10, "exp": past, "type": "access"})
    with pytest.raises((HTTPException, Exception)):
        _call_get_current_user(token)
