from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.routers.v3.db import execute, fetch_one
from app.routers.v3.models import LoginRequest, RefreshRequest, TokenResponse

router = APIRouter(prefix="/v3/auth", tags=["v3-auth"])

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer()

_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
_ALGO = "HS256"
_ACCESS_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "1"))
_REFRESH_DAYS = int(os.getenv("JWT_REFRESH_DAYS", "30"))


def _make_access_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=_ACCESS_HOURS)
    return jwt.encode({"sub": user_id, "exp": exp, "type": "access"}, _SECRET, algorithm=_ALGO)


def _make_refresh_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=_REFRESH_DAYS)
    token = str(uuid.uuid4())
    execute(
        "INSERT INTO ui_sessions (user_id, refresh_token, expires_at) VALUES (%s, %s, %s)",
        (user_id, token, exp),
    )
    return token


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, _SECRET, algorithms=[_ALGO])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not an access token")
    user = fetch_one("SELECT * FROM ui_users WHERE id = %s AND is_active = true", (payload["sub"],))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    user = fetch_one("SELECT * FROM ui_users WHERE username = %s AND is_active = true", (body.username,))
    if not user or not _pwd.verify(body.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(
        access_token=_make_access_token(str(user["id"])),
        refresh_token=_make_refresh_token(str(user["id"])),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest):
    session = fetch_one(
        "SELECT * FROM ui_sessions WHERE refresh_token = %s AND expires_at > now()",
        (body.refresh_token,),
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")
    execute("DELETE FROM ui_sessions WHERE refresh_token = %s", (body.refresh_token,))
    user_id = str(session["user_id"])
    return TokenResponse(
        access_token=_make_access_token(user_id),
        refresh_token=_make_refresh_token(user_id),
    )
