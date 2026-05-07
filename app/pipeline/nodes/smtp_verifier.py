"""SMTP email verifier node — confirms email existence via MX lookup + SMTP probe."""

from __future__ import annotations

import asyncio
import logging
import smtplib

import dns.resolver as dns_resolver

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "SMTP probing confirms whether an email address actually exists on the mail server "
    "by resolving MX records and issuing an RCPT TO command — no message is sent"
)


class SmtpVerifierNode:
    node_type = "smtp_verifier"
    display_name = "SMTP Email Verifier"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "email": {
                "type": "string",
                "title": "Email Address",
                "description": "Email address to verify. Overridden by upstream input items.",
            },
            "timeout_seconds": {
                "type": "integer",
                "title": "Timeout (seconds)",
                "default": 10,
                "minimum": 3,
                "maximum": 30,
                "description": "SMTP connection timeout in seconds.",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        timeout = int(config.get("timeout_seconds", 10))
        timeout = max(3, min(30, timeout))

        # Collect emails: config email first, then one per input item
        emails: list[str] = []
        config_email = (config.get("email") or "").strip()
        if config_email:
            emails.append(config_email)
        for item in inputs:
            addr = (item.get("email") or "").strip()
            if addr:
                emails.append(addr)

        if not emails:
            log.warning("smtp_verifier: no email address provided")
            return [{"error": "No email address provided", "source": "smtp_verifier", "reason": _REASON}]

        loop = asyncio.get_running_loop()
        results: list[dict] = []
        for email in emails:
            result = await loop.run_in_executor(None, _verify_email, email, timeout)
            results.append(result)

        return results


def _verify_email(email: str, timeout: int) -> dict:
    """Resolve MX for the email's domain, then SMTP-probe for existence."""
    if "@" not in email:
        return {"email": email, "exists": None, "error": "Invalid email format", "source": "smtp_verifier", "reason": _REASON}

    domain = email.split("@", 1)[1].strip()
    mx_host = _get_mx_host(domain)

    if mx_host is None:
        return {
            "email": email,
            "exists": None,
            "mx_host": None,
            "method": "smtp",
            "source": "smtp_verifier",
            "reason": _REASON,
        }

    exists = _check_smtp(email, mx_host, timeout)
    return {
        "email": email,
        "exists": exists,
        "mx_host": mx_host,
        "method": "smtp",
        "source": "smtp_verifier",
        "reason": _REASON,
    }


def _get_mx_host(domain: str) -> str | None:
    """Return the highest-priority MX hostname for *domain*, or None on failure."""
    try:
        answers = dns_resolver.resolve(domain, "MX")
        records = sorted(answers, key=lambda r: r.preference)
        return records[0].exchange.to_text().rstrip(".")
    except Exception as exc:
        log.debug("smtp_verifier: MX lookup failed for %r: %s", domain, exc)
        return None


def _check_smtp(email: str, mx_host: str, timeout: int) -> bool | None:
    """Probe *mx_host* via SMTP RCPT TO for *email*.

    Returns:
        True  — server returned 250 (mailbox exists)
        False — server returned >=500 (mailbox rejected)
        None  — inconclusive (timeout, connection refused, greylisting, etc.)
    """
    try:
        with smtplib.SMTP(mx_host, 25, timeout=timeout) as server:
            server.helo("info-broker.local")
            server.mail("verify@info-broker.local")
            code, _ = server.rcpt(email)
            if code == 250:
                return True
            if code >= 500:
                return False
            return None
    except (TimeoutError, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected) as exc:
        log.debug("smtp_verifier: SMTP probe inconclusive for %r via %r: %s", email, mx_host, exc)
        return None
    except Exception as exc:
        log.debug("smtp_verifier: unexpected error probing %r via %r: %s", email, mx_host, exc)
        return None
