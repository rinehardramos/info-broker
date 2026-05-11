"""GitHub repo stats node — stars, forks, commit velocity, contributors, and releases via GitHub REST API."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "GitHub repo metrics (stars, forks, weekly commit velocity, contributor count, release cadence) "
    "are leading indicators of OSS adoption — critical for competitive intelligence on developer tools"
)
_GITHUB_API = "https://api.github.com"


def _auth_headers(token: str | None = None) -> dict:
    token = token or os.getenv("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


class GithubRepoStatsNode:
    node_type = "github_repo_stats"
    display_name = "GitHub Repo Stats"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "title": "Repository",
                "description": "Full repo name (e.g. 'mem0ai/mem0') or list of repos separated by commas.",
            },
            "include_commit_activity": {
                "type": "boolean",
                "title": "Include Commit Activity",
                "description": "Fetch weekly commit counts for the last 52 weeks (slower, may be cached by GitHub).",
                "default": True,
            },
            "max_contributors": {
                "type": "integer",
                "title": "Max Contributors",
                "default": 5,
                "minimum": 1,
                "maximum": 100,
                "description": "Number of top contributors to return.",
            },
            "max_releases": {
                "type": "integer",
                "title": "Max Releases",
                "default": 5,
                "minimum": 1,
                "maximum": 20,
            },
            "github_token": {
                "type": "string",
                "title": "GitHub Token",
                "description": "Optional. Leave blank to use GITHUB_TOKEN env var.",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        repo_raw = (config.get("repo") or "").strip()
        if not repo_raw:
            for item in inputs:
                r = item.get("repo") or item.get("full_name") or item.get("name") or ""
                if r and "/" in str(r):
                    repo_raw = str(r).strip()
                    break

        if not repo_raw:
            log.warning("github_repo_stats: no repo provided")
            return [{"error": "No repo provided (expected 'owner/name')", "source": "github_repo_stats", "reason": _REASON}]

        token = config.get("github_token") or None
        include_commits = bool(config.get("include_commit_activity", True))
        max_contrib = min(int(config.get("max_contributors", 5)), 100)
        max_releases = min(int(config.get("max_releases", 5)), 20)

        repos = [r.strip() for r in repo_raw.split(",") if "/" in r.strip()]
        if not repos:
            return [{"error": f"Invalid repo format: {repo_raw!r} — expected 'owner/name'", "source": "github_repo_stats", "reason": _REASON}]

        loop = asyncio.get_running_loop()
        results = []
        for repo in repos:
            result = await loop.run_in_executor(
                None, _fetch_repo_stats, repo, token, include_commits, max_contrib, max_releases
            )
            results.append(result)
        return results


def _fetch_repo_stats(
    repo: str,
    token: str | None,
    include_commits: bool,
    max_contrib: int,
    max_releases: int,
) -> dict:
    headers = _auth_headers(token)

    with httpx.Client(timeout=30.0, headers=headers) as client:
        # Core repo metadata
        try:
            r = client.get(f"{_GITHUB_API}/repos/{repo}")
            if r.status_code == 404:
                return {"error": f"Repo not found: {repo}", "source": "github_repo_stats", "reason": _REASON}
            if r.status_code == 403:
                return {"error": "GitHub rate limit exceeded", "source": "github_repo_stats", "reason": _REASON}
            r.raise_for_status()
            meta = r.json()
        except httpx.HTTPStatusError as exc:
            log.warning("github_repo_stats: HTTP error for %s: %s", repo, exc)
            return {"error": str(exc), "source": "github_repo_stats", "reason": _REASON}
        except Exception as exc:
            log.warning("github_repo_stats: error for %s: %s", repo, exc)
            return {"error": str(exc), "source": "github_repo_stats", "reason": _REASON}

        result: dict = {
            "repo": meta.get("full_name") or repo,
            "description": meta.get("description") or "",
            "stars": meta.get("stargazers_count") or 0,
            "forks": meta.get("forks_count") or 0,
            "watchers": meta.get("subscribers_count") or 0,
            "open_issues": meta.get("open_issues_count") or 0,
            "language": meta.get("language") or "",
            "topics": meta.get("topics") or [],
            "created_at": meta.get("created_at") or "",
            "pushed_at": meta.get("pushed_at") or "",
            "license": (meta.get("license") or {}).get("spdx_id") or "",
            "url": meta.get("html_url") or f"https://github.com/{repo}",
            "source": "github_repo_stats",
            "reason": _REASON,
        }

        # Weekly commit activity (last 52 weeks)
        if include_commits:
            try:
                rc = client.get(f"{_GITHUB_API}/repos/{repo}/stats/commit_activity", timeout=20.0)
                if rc.status_code == 200:
                    weeks = rc.json() or []
                    # Sum last 4 weeks for recent velocity
                    recent_4w = sum(w.get("total", 0) for w in weeks[-4:]) if weeks else 0
                    recent_12w = sum(w.get("total", 0) for w in weeks[-12:]) if weeks else 0
                    result["commits_last_4w"] = recent_4w
                    result["commits_last_12w"] = recent_12w
            except Exception:
                pass  # Stats endpoints can return 202 (computing) — non-fatal

        # Top contributors
        try:
            rc = client.get(f"{_GITHUB_API}/repos/{repo}/contributors", params={"per_page": max_contrib, "anon": "false"})
            if rc.status_code == 200:
                contribs = rc.json() or []
                result["contributors"] = [
                    {"login": c.get("login", ""), "contributions": c.get("contributions", 0)}
                    for c in contribs[:max_contrib]
                ]
                result["contributor_count"] = len(contribs)
        except Exception:
            pass

        # Recent releases
        try:
            rr = client.get(f"{_GITHUB_API}/repos/{repo}/releases", params={"per_page": max_releases})
            if rr.status_code == 200:
                releases = rr.json() or []
                result["recent_releases"] = [
                    {
                        "tag": rel.get("tag_name", ""),
                        "name": rel.get("name", ""),
                        "published_at": rel.get("published_at", ""),
                        "prerelease": rel.get("prerelease", False),
                    }
                    for rel in releases[:max_releases]
                ]
        except Exception:
            pass

    return result
