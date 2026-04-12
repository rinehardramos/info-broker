from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Header, HTTPException

DUMMY_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
ALGORITHM = "HS256"
ISSUER = "info-broker-dev"


def _get_secret() -> str:
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        raise ValueError("JWT_SECRET environment variable is not set")
    return secret


def create_token(*, username: str, expiry_hours: float | None = None) -> str:
    """Return a signed HS256 JWT for the stub user."""
    secret = _get_secret()
    if expiry_hours is None:
        expiry_hours = float(os.environ.get("JWT_EXPIRY_HOURS", "24"))
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": str(DUMMY_USER_ID),
        "username": username,
        "iss": ISSUER,
        "iat": now,
        "exp": now + timedelta(hours=expiry_hours),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT, returning the payload dict."""
    secret = _get_secret()
    return jwt.decode(token, secret, algorithms=[ALGORITHM], issuer=ISSUER)


async def require_jwt(
    authorization: str = Header(..., alias="Authorization"),
) -> dict:
    """FastAPI dependency — validates the Bearer token and returns the payload."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization[len("Bearer "):]
    try:
        return decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
