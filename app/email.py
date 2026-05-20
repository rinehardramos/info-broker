"""Email service for transactional sends via Resend.

Minimal wrapper used today for verification emails. Add new
`send_*` helpers here as needs grow rather than scattering Resend
calls across routers.
"""
from __future__ import annotations

import os
from typing import Final

import resend

_API_KEY: Final[str] = os.getenv("RESEND_API_KEY", "")
_FROM:    Final[str] = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")
_APP_URL: Final[str] = os.getenv("APP_URL", "http://localhost:5173")


def send_verification_email(to_email: str, token: str) -> None:
    """Send an email-verification link to `to_email`.

    Raises RuntimeError if RESEND_API_KEY isn\'t configured so callers
    can return a clear 503 rather than a generic 500.
    """
    if not _API_KEY:
        raise RuntimeError("RESEND_API_KEY not configured")
    resend.api_key = _API_KEY
    link = f"{_APP_URL}/verify-email?token={token}"
    html = (
        '<div style="font-family:system-ui,-apple-system,sans-serif;'
        'max-width:480px;margin:0 auto;padding:24px;color:#111">'
        '<h2 style="margin:0 0 12px">Verify your info-broker email</h2>'
        '<p>Click the button below to confirm this address. The link '
        'expires in 24 hours.</p>'
        f'<p style="margin:20px 0"><a href="{link}" '
        'style="display:inline-block;padding:10px 18px;background:#7c3aed;'
        'color:#fff;text-decoration:none;border-radius:6px;font-weight:600">'
        'Verify email</a></p>'
        '<p style="color:#666;font-size:12px">Or paste this URL into your browser:<br>'
        f'<a href="{link}">{link}</a></p>'
        '</div>'
    )
    resend.Emails.send({
        "from": _FROM,
        "to": [to_email],
        "subject": "Verify your info-broker email",
        "html": html,
    })
