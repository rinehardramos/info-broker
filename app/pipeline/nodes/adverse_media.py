"""Adverse media monitoring node — systematic negative news search across crime, fraud, and scandal categories."""

from __future__ import annotations

import asyncio
import logging

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

ADVERSE_CATEGORIES = [
    "fraud",
    "corruption",
    "lawsuit",
    "arrest",
    "scandal",
    "investigation",
    "sanction",
    "embezzlement",
    "money_laundering",
]

_REASON = (
    "Adverse media search surfaces negative news — criminal activity, fraud, corruption, and legal disputes — "
    "critical for due diligence and risk assessment"
)

# Related terms per category to broaden query coverage
_CATEGORY_TERMS: dict[str, list[str]] = {
    "fraud": ["fraud", "scam", "deception", "misrepresentation"],
    "corruption": ["corruption", "bribery", "kickback", "graft"],
    "lawsuit": ["lawsuit", "sued", "litigation", "court case"],
    "arrest": ["arrested", "charged", "indicted", "detained"],
    "scandal": ["scandal", "controversy", "misconduct", "accused"],
    "investigation": ["investigation", "probe", "inquiry", "scrutiny"],
    "sanction": ["sanction", "blacklist", "banned", "prohibited"],
    "embezzlement": ["embezzlement", "misappropriation", "theft"],
    "money_laundering": ["money laundering", "financial crime", "illicit funds"],
}


def _search_adverse_media(name: str, categories: list[str]) -> list[dict]:
    """Search for adverse media hits across the given categories via DdgPlugin.

    Limits to 3 categories per call to avoid rate limiting.
    Returns list of {title, category, snippet, source_url}.
    """
    from app.search_engine.plugins.ddg import DdgPlugin

    results: list[dict] = []
    limited_categories = categories[:3]
    plugin = DdgPlugin()

    for category in limited_categories:
        terms = _CATEGORY_TERMS.get(category, [category])
        terms_str = " OR ".join(f'"{t}"' for t in terms)
        query = f'"{name}" ({terms_str})'

        try:
            # Run the async search synchronously (this function is called via run_in_executor)
            loop = asyncio.new_event_loop()
            try:
                hits = loop.run_until_complete(plugin.search(query, max_results=5))
            finally:
                loop.close()

            for hit in hits:
                results.append(
                    {
                        "title": hit.title,
                        "category": category,
                        "snippet": hit.snippet or "",
                        "source_url": hit.url or "",
                    }
                )
        except Exception as exc:
            log.warning("adverse_media: error searching category %r: %s", category, exc)

    return results


class AdverseMediaNode:
    node_type = "adverse_media"
    display_name = "Adverse Media"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "title": "Person / Entity Name",
                "description": "Full name of the person or entity to screen.",
            },
            "categories": {
                "type": "array",
                "items": {"type": "string"},
                "title": "Categories",
                "description": "Adverse media categories to search. Defaults to all categories.",
                "default": ADVERSE_CATEGORIES,
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        # Resolve name from config then inputs
        name = (config.get("name") or "").strip()
        if not name:
            for item in inputs:
                candidate = (item.get("name") or item.get("full_name") or "").strip()
                if candidate:
                    name = candidate
                    break

        if not name:
            return [
                {
                    "error": "No name provided for adverse media search",
                    "source": "adverse_media",
                    "reason": _REASON,
                }
            ]

        categories: list[str] = config.get("categories") or ADVERSE_CATEGORIES

        loop = asyncio.get_running_loop()
        hits: list[dict] = await loop.run_in_executor(
            None, _search_adverse_media, name, categories
        )

        if not hits:
            return [
                {
                    "name": name,
                    "hits": [],
                    "summary": "No adverse media found",
                    "source": "adverse_media",
                    "reason": _REASON,
                }
            ]

        return [
            {
                **hit,
                "name": name,
                "source": "adverse_media",
                "reason": _REASON,
            }
            for hit in hits
        ]
