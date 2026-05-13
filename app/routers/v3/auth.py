from __future__ import annotations

import os
import re as _re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, field_validator

from app.routers.v3.db import execute, fetch_all, fetch_one
from app.routers.v3.models import LoginRequest, RefreshRequest, TokenResponse
from app.lib.rate_limit import limiter


def _validate_password_strength(v: str) -> str:
    if len(v) < 12:
        raise ValueError("Password must be at least 12 characters")
    if not _re.search(r"[\d\W]", v):
        raise ValueError("Password must contain at least one digit or special character")
    return v


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _strong(cls, v: str) -> str:
        return _validate_password_strength(v)



router = APIRouter(prefix="/v3/auth", tags=["v3-auth"])

_pwd = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated=["bcrypt"],
    argon2__memory_cost=65536,
    argon2__time_cost=3,
    argon2__parallelism=4,
)
_bearer = HTTPBearer()

_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
_ALGO = "HS256"
_ACCESS_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "1"))
_REFRESH_DAYS = int(os.getenv("JWT_REFRESH_DAYS", "30"))


def _make_access_token(user_id: str) -> str:
    row = fetch_one(
        "SELECT org_id, is_admin, role FROM ui_users WHERE id = %s",
        (user_id,),
    ) or {}
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "org_id": str(row.get("org_id") or ""),
        "is_admin": bool(row.get("is_admin")),
        "role": row.get("role") or "analyst",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=_ACCESS_HOURS)).timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGO)


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
        payload = jwt.decode(
            credentials.credentials,
            _SECRET,
            algorithms=[_ALGO],
            options={"require": ["exp", "iat", "sub"]},
        )
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
    if _pwd.needs_update(user["password_hash"]):
        new_hash = _pwd.hash(body.password)
        execute("UPDATE ui_users SET password_hash = %s WHERE id = %s", (new_hash, user["id"]))
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
        """SELECT id, username, email, is_admin, role, is_active, org_id, created_at
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
    """Update user is_admin, role, or is_active. Admin only."""
    if str(user_id) == str(current_user["id"]) and body.get("is_admin") is False:
        raise HTTPException(status_code=400, detail="Cannot remove your own admin status")

    if "role" in body and body["role"] not in ("admin", "analyst", "viewer"):
        raise HTTPException(status_code=422, detail="role must be admin, analyst, or viewer")

    allowed = {k: v for k, v in body.items() if k in ("is_admin", "is_active", "role")}
    if not allowed:
        raise HTTPException(status_code=422, detail="Only is_admin, role, and is_active are patchable")

    set_clause = ", ".join(f"{k} = %s" for k in allowed)
    values = list(allowed.values()) + [user_id]
    row = fetch_one(
        f"UPDATE ui_users SET {set_clause} WHERE id = %s RETURNING id, username, is_admin, role, is_active",
        tuple(values),
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(row)


@router.post("/change-password")
@limiter.limit("5/minute")
def change_password(
    request: Request,
    body: ChangePasswordIn,
    user: dict = Depends(get_current_user),
) -> dict:
    """Change password. Requires current password. SOC 2 CC6.1."""
    row = fetch_one("SELECT id, password_hash FROM ui_users WHERE id = %s", (user["id"],))
    if not row or not _pwd.verify(body.current_password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid current password")
    if _pwd.verify(body.new_password, row["password_hash"]):
        raise HTTPException(status_code=400, detail="New password must differ from current")
    new_hash = _pwd.hash(body.new_password)
    execute("UPDATE ui_users SET password_hash = %s WHERE id = %s", (new_hash, user["id"]))
    return {"ok": True}
