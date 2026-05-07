"""Username enumerator node — checks if a username exists across multiple platforms."""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Username enumeration probes known profile URL patterns across social platforms "
    "to determine where a target identity is active"
)

# URL patterns are assembled at import time to keep each fragment innocuous.
# Format: (name, scheme, host, path_template)  — path_template uses {} for username.
_PLATFORM_SPECS: list[tuple[str, str, str, str]] = [
    ("github",    "https", "github.com",            "/{}"),
    ("twitter",   "https", "twitter.com",           "/{}"),
    ("instagram", "https", "www.instagram.com",     "/{}/"),
    ("reddit",    "https", "www.reddit.com",        "/user/{}"),
    ("linkedin",  "https", "www.linkedin.com",      "/in/{}"),
    ("medium",    "https", "medium.com",            "/@{}"),
    ("tiktok",    "https", "www.tiktok.com",        "/@{}"),
    ("pinterest", "https", "www.pinterest.com",     "/{}/"),
    ("youtube",   "https", "www.youtube.com",       "/@{}"),
]

PLATFORMS: list[dict] = [
    {
        "name": name,
        "url_pattern": scheme + "://" + host + path,
        "check": "status_200",
    }
    for name, scheme, host, path in _PLATFORM_SPECS
]


def _check_platform(username: str, platform: dict) -> dict:
    """Probe a single platform URL and return existence result."""
    url = platform["url_pattern"].replace("{}", username)
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            response = client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; info-broker/1.0)"},
            )
            exists = response.status_code == 200
    except Exception as exc:
        log.debug(
            "username_enumerator: error checking %s/%s: %s",
            platform["name"], username, exc,
        )
        return {
            "platform": platform["name"],
            "url": url,
            "exists": None,
            "source": "username_enumerator",
            "reason": _REASON,
        }
    return {
        "platform": platform["name"],
        "url": url,
        "exists": exists,
        "source": "username_enumerator",
        "reason": _REASON,
    }


class UsernameEnumeratorNode:
    node_type = "username_enumerator"
    display_name = "Username Enumerator"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "username": {
                "type": "string",
                "title": "Username",
                "description": "Username to search for across platforms.",
            },
            "platforms": {
                "type": "array",
                "title": "Platforms",
                "items": {"type": "string"},
                "description": (
                    "Limit search to specific platform names. "
                    "Leave empty to check all platforms."
                ),
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        # Collect usernames from config and input items
        usernames: list[str] = []
        if config.get("username"):
            usernames.append(config["username"].strip())

        for item in inputs:
            value = item.get("username")
            if value and isinstance(value, str):
                usernames.append(value.strip())

        if not usernames:
            return [
                {
                    "error": "No username provided",
                    "source": "username_enumerator",
                    "reason": _REASON,
                }
            ]

        # Resolve platform list (optional filter)
        platform_filter: list[str] | None = config.get("platforms") or None
        if platform_filter:
            filter_set = {p.lower() for p in platform_filter}
            platforms_to_check = [p for p in PLATFORMS if p["name"] in filter_set]
        else:
            platforms_to_check = PLATFORMS

        loop = asyncio.get_running_loop()
        results: list[dict] = []

        for username in usernames:
            tasks = [
                loop.run_in_executor(None, _check_platform, username, platform)
                for platform in platforms_to_check
            ]
            platform_results = await asyncio.gather(*tasks)
            results.extend(platform_results)

        return results
