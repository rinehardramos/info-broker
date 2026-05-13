from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.routers.v3.db import execute, fetch_all, fetch_one
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


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Raise 403 if the authenticated user is not an admin."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
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




@router.get("/users", dependencies=[Depends(require_admin)])
def list_users(current_user: dict = Depends(get_current_user)) -> list[dict]:
    """List all users. Admin only."""
    rows = fetch_all(
        """SELECT id, username, email, is_admin, is_active, org_id, created_at
           FROM ui_users
           ORDER BY created_at DESC""",
        (),
    )
    return [dict(r) for r in rows]


@router.patch("/users/{user_id}", dependencies=[Depends(require_admin)])
def update_user(
    user_id: str,
    body: dict,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Update user is_admin or is_active. Admin only."""
    if str(user_id) == str(current_user["id"]) and body.get("is_admin") is False:
        raise HTTPException(status_code=400, detail="Cannot remove your own admin status")

    allowed = {k: v for k, v in body.items() if k in ("is_admin", "is_active")}
    if not allowed:
        raise HTTPException(status_code=422, detail="Only is_admin and is_active are patchable")

    set_clause = ", ".join(f"{k} = %s" for k in allowed)
    values = list(allowed.values()) + [user_id]
    row = fetch_one(
        f"UPDATE ui_users SET {set_clause} WHERE id = %s RETURNING id, username, is_admin, is_active",
        tuple(values),
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(row)
