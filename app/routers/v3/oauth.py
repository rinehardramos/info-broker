"""Google + GitHub OAuth login.

Authorization-code flow with server-side token exchange. Tokens are NOT
stored — we use the provider's userinfo response to find-or-create a
ui_users row, then return our own JWT to the frontend by redirecting to
`/auth/callback#access_token=...&refresh_token=...`.

Secrets resolution order:
  1. core_settings table (admin can rotate via /settings → Core Settings)
  2. environment variables

Required env vars (or core_settings keys):
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
  GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET
  OAUTH_REDIRECT_BASE (defaults to http://localhost:8000 in dev) — the
    public URL of the backend. Provider must whitelist
    {base}/v3/auth/{provider}/callback as a redirect URI.
"""
from __future__ import annotations

import logging
import os
import secrets
import urllib.parse
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.routers.v3.auth import _make_access_token, _make_refresh_token
from app.routers.v3.db import execute, fetch_one

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v3/auth", tags=["v3-auth-oauth"])

# Frontend route that reads access_token / refresh_token from the URL
# fragment and stores them in sessionStore. Set FRONTEND_OAUTH_CALLBACK
# to override (e.g. production https URL).
_FRONTEND_CALLBACK = os.getenv("FRONTEND_OAUTH_CALLBACK", "http://localhost:5173/auth/callback")
_BACKEND_BASE = os.getenv("OAUTH_REDIRECT_BASE", "http://localhost:8000")

# In-memory state store: state token → provider. Short-lived; only valid
# until callback returns. Multi-process deployments should swap this for
# Redis or a signed cookie.
_STATE_STORE: dict[str, str] = {}


def _get_secret(key: str) -> Optional[str]:
    """Look up an OAuth secret in core_settings first, env var as fallback."""
    try:
        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = %s AND value IS NOT NULL AND value <> ''",
            (key.lower(),),
        )
        if row and row.get("value"):
            v = str(row["value"])
            # Ignore obvious placeholders/sentinels
            if v and "REDACTED" not in v and not v.startswith("change-me"):
                return v
    except Exception as exc:
        log.debug("core_settings lookup for %s failed: %s", key, exc)
    return os.getenv(key.upper()) or None


def _complete_oauth_login(
    provider: str,
    sub: str,
    email: str,
    name: str | None,
    avatar_url: str | None,
) -> tuple[str, str]:
    """Find or create a ui_users row for this OAuth identity, return JWT pair."""
    if not email:
        raise HTTPException(status_code=400, detail="OAuth provider did not return an email")
    email = email.strip().lower()

    # 1. Match by oauth_provider + oauth_sub (stable across email changes)
    row = fetch_one(
        "SELECT id FROM ui_users WHERE oauth_provider = %s AND oauth_sub = %s",
        (provider, sub),
    )
    user_id: Optional[str] = str(row["id"]) if row else None

    # 2. Fallback: match by email and adopt the identity
    if not user_id:
        row = fetch_one(
            "SELECT id FROM ui_users WHERE LOWER(email) = %s AND is_active = true",
            (email,),
        )
        if row:
            user_id = str(row["id"])
            execute(
                "UPDATE ui_users SET oauth_provider = %s, oauth_sub = %s, avatar_url = COALESCE(%s, avatar_url) WHERE id = %s",
                (provider, sub, avatar_url, user_id),
            )

    # 3. Create — auto-create personal org (org_id = new UUID; user is admin
    #    of their own personal org). Org admins can later invite this user
    #    into a shared org via the existing admin invite flow.
    if not user_id:
        user_id = str(uuid.uuid4())
        personal_org_id = str(uuid.uuid4())
        # Username defaults to the email local-part with a numeric suffix to
        # avoid collisions; admins can rename later.
        base_username = email.split("@", 1)[0][:96] or f"user-{user_id[:8]}"
        username = base_username
        suffix = 1
        while fetch_one("SELECT 1 FROM ui_users WHERE username = %s", (username,)):
            suffix += 1
            username = f"{base_username}-{suffix}"
            if suffix > 50:
                username = f"user-{user_id[:8]}"
                break

        execute(
            """
            INSERT INTO ui_users (
                id, username, email, password_hash,
                is_active, is_admin, role,
                org_id, oauth_provider, oauth_sub, avatar_url
            ) VALUES (%s, %s, %s, NULL, true, false, 'admin', %s, %s, %s, %s)
            """,
            (user_id, username, email, personal_org_id, provider, sub, avatar_url),
        )
        log.info(
            "oauth: created new user via %s — id=%s email=%s personal_org=%s",
            provider, user_id, email, personal_org_id,
        )

    return _make_access_token(user_id), _make_refresh_token(user_id)


def _build_callback_url(provider: str) -> str:
    return f"{_BACKEND_BASE.rstrip('/')}/v3/auth/{provider}/callback"


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------

_GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
_GOOGLE_SCOPES = "openid email profile"


@router.get("/google/login")
def google_login():
    client_id = _get_secret("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=503, detail="Google login is not configured")

    state = secrets.token_urlsafe(24)
    _STATE_STORE[state] = "google"
    params = {
        "client_id": client_id,
        "redirect_uri": _build_callback_url("google"),
        "response_type": "code",
        "scope": _GOOGLE_SCOPES,
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return RedirectResponse(f"{_GOOGLE_AUTHORIZE}?{urllib.parse.urlencode(params)}")


@router.get("/google/callback")
async def google_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    err = request.query_params.get("error")
    if err:
        log.warning("google callback error: %s", err)
        return RedirectResponse(f"{_FRONTEND_CALLBACK}#error={urllib.parse.quote(err)}")
    if not code or not state or _STATE_STORE.pop(state, None) != "google":
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    client_id = _get_secret("GOOGLE_CLIENT_ID")
    client_secret = _get_secret("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="Google login is not configured")

    async with httpx.AsyncClient(timeout=15) as cx:
        tok = await cx.post(
            _GOOGLE_TOKEN,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": _build_callback_url("google"),
                "grant_type": "authorization_code",
            },
        )
        if tok.status_code != 200:
            log.warning("google token exchange failed: %s %s", tok.status_code, tok.text[:300])
            raise HTTPException(status_code=502, detail="Google token exchange failed")
        access = tok.json().get("access_token")
        if not access:
            raise HTTPException(status_code=502, detail="Google did not return an access token")

        ui = await cx.get(_GOOGLE_USERINFO, headers={"Authorization": f"Bearer {access}"})
        if ui.status_code != 200:
            raise HTTPException(status_code=502, detail="Google userinfo failed")
        profile = ui.json()

    sub = profile.get("sub", "")
    email = profile.get("email", "")
    name = profile.get("name") or profile.get("given_name") or None
    picture = profile.get("picture")

    at, rt = _complete_oauth_login("google", sub, email, name, picture)
    return RedirectResponse(f"{_FRONTEND_CALLBACK}#access_token={at}&refresh_token={rt}")


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------

_GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
_GITHUB_USER = "https://api.github.com/user"
_GITHUB_EMAILS = "https://api.github.com/user/emails"
_GITHUB_SCOPES = "read:user user:email"


@router.get("/github/login")
def github_login():
    client_id = _get_secret("GITHUB_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=503, detail="GitHub login is not configured")

    state = secrets.token_urlsafe(24)
    _STATE_STORE[state] = "github"
    params = {
        "client_id": client_id,
        "redirect_uri": _build_callback_url("github"),
        "scope": _GITHUB_SCOPES,
        "state": state,
        "allow_signup": "true",
    }
    return RedirectResponse(f"{_GITHUB_AUTHORIZE}?{urllib.parse.urlencode(params)}")


@router.get("/github/callback")
async def github_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    err = request.query_params.get("error")
    if err:
        log.warning("github callback error: %s", err)
        return RedirectResponse(f"{_FRONTEND_CALLBACK}#error={urllib.parse.quote(err)}")
    if not code or not state or _STATE_STORE.pop(state, None) != "github":
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    client_id = _get_secret("GITHUB_CLIENT_ID")
    client_secret = _get_secret("GITHUB_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="GitHub login is not configured")

    async with httpx.AsyncClient(timeout=15) as cx:
        tok = await cx.post(
            _GITHUB_TOKEN,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": _build_callback_url("github"),
            },
            headers={"Accept": "application/json"},
        )
        if tok.status_code != 200:
            log.warning("github token exchange failed: %s %s", tok.status_code, tok.text[:300])
            raise HTTPException(status_code=502, detail="GitHub token exchange failed")
        access = tok.json().get("access_token")
        if not access:
            raise HTTPException(status_code=502, detail="GitHub did not return an access token")

        hdrs = {"Authorization": f"Bearer {access}", "Accept": "application/vnd.github+json"}
        user_resp = await cx.get(_GITHUB_USER, headers=hdrs)
        if user_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="GitHub user lookup failed")
        profile = user_resp.json()

        # GitHub primary email may be private — fetch /user/emails if missing
        email = profile.get("email")
        if not email:
            emails_resp = await cx.get(_GITHUB_EMAILS, headers=hdrs)
            if emails_resp.status_code == 200:
                emails = emails_resp.json() or []
                primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
                email = (primary or (emails[0] if emails else {})).get("email", "")

    sub = str(profile.get("id", ""))
    name = profile.get("name") or profile.get("login") or None
    avatar = profile.get("avatar_url")

    at, rt = _complete_oauth_login("github", sub, email or "", name, avatar)
    return RedirectResponse(f"{_FRONTEND_CALLBACK}#access_token={at}&refresh_token={rt}")


# ---------------------------------------------------------------------------
# Health / config check (used by frontend to enable/disable buttons)
# ---------------------------------------------------------------------------

@router.get("/providers")
def providers_status() -> dict:
    """Tell the frontend which SSO providers are configured."""
    return {
        "google": bool(_get_secret("GOOGLE_CLIENT_ID") and _get_secret("GOOGLE_CLIENT_SECRET")),
        "github": bool(_get_secret("GITHUB_CLIENT_ID") and _get_secret("GITHUB_CLIENT_SECRET")),
    }
