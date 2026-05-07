"""Email enumerator node — generates candidate email addresses from name patterns and verifies via SMTP."""

from __future__ import annotations

import asyncio
import logging

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Email enumeration generates likely email addresses from name patterns across common providers "
    "and confirms existence via SMTP probing — no message is sent"
)

_DEFAULT_PROVIDERS = [
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "icloud.com",
    "protonmail.com",
]


class EmailEnumeratorNode:
    node_type = "email_enumerator"
    display_name = "Email Enumerator"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "first_name": {
                "type": "string",
                "title": "First Name",
                "description": "Target's first name.",
            },
            "last_name": {
                "type": "string",
                "title": "Last Name",
                "description": "Target's last name.",
            },
            "providers": {
                "type": "array",
                "items": {"type": "string"},
                "title": "Email Providers",
                "description": "List of email domains to test (e.g. gmail.com). Defaults to common providers.",
                "default": [],
            },
            "domain_hints": {
                "type": "array",
                "items": {"type": "string"},
                "title": "Domain Hints",
                "description": "Additional domains to include (e.g. company.com).",
                "default": [],
            },
            "max_candidates": {
                "type": "integer",
                "title": "Max Candidates",
                "default": 30,
                "minimum": 5,
                "maximum": 100,
                "description": "Maximum number of candidate email addresses to verify.",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        # Resolve first/last name from config, then inputs
        first = (config.get("first_name") or "").strip()
        last = (config.get("last_name") or "").strip()

        if not first or not last:
            for item in inputs:
                f = (item.get("first_name") or "").strip()
                l = (item.get("last_name") or "").strip()
                if f and l:
                    first, last = f, l
                    break
                # Fallback: split full_name or name
                full = (item.get("full_name") or item.get("name") or "").strip()
                if full and " " in full:
                    parts = full.split(None, 1)
                    first, last = parts[0], parts[1]
                    break

        if not first or not last:
            log.warning("email_enumerator: could not resolve first/last name from config or inputs")
            return [{"error": "first_name and last_name are required", "source": "email_enumerator", "reason": _REASON}]

        # Gather domains
        domains: list[str] = list(config.get("providers") or [])
        domains.extend(config.get("domain_hints") or [])
        for item in inputs:
            d = (item.get("domain") or "").strip()
            if d:
                domains.append(d)

        max_candidates = int(config.get("max_candidates", 30))
        max_candidates = max(5, min(100, max_candidates))

        candidates = _generate_candidates(first, last, domains)[:max_candidates]

        timeout = 10
        loop = asyncio.get_running_loop()
        results: list[dict] = []
        for email in candidates:
            exists = await loop.run_in_executor(None, _verify_email, email, timeout)
            results.append({
                "email": email,
                "exists": exists,
                "source": "email_enumerator",
                "reason": _REASON,
            })

        return results


def _generate_candidates(first: str, last: str, domains: list[str]) -> list[str]:
    """Generate email candidates from 8 name patterns cross-joined with domains."""
    f = first.lower()
    l = last.lower()
    fi = f[0] if f else ""

    patterns = [
        f"{f}.{l}",       # john.doe
        f"{f}{l}",        # johndoe
        f"{fi}.{l}",      # j.doe
        f"{fi}{l}",       # jdoe
        f"{l}.{f}",       # doe.john
        f"{l}{f}",        # doejohn
        f"{f}_{l}",       # john_doe
        f"{l}_{f}",       # doe_john
    ]

    providers = domains if domains else _DEFAULT_PROVIDERS

    candidates: list[str] = []
    for provider in providers:
        for pattern in patterns:
            candidates.append(f"{pattern}@{provider}")

    return candidates


def _verify_email(email: str, timeout: int) -> bool | None:
    """Verify email existence via MX lookup and SMTP probe."""
    try:
        from app.pipeline.nodes.smtp_verifier import _get_mx_host, _check_smtp

        if "@" not in email:
            return None

        domain = email.split("@", 1)[1].strip()
        mx_host = _get_mx_host(domain)
        if mx_host is None:
            return None

        return _check_smtp(email, mx_host, timeout)
    except Exception as exc:
        log.debug("email_enumerator: verification error for %r: %s", email, exc)
        return None
