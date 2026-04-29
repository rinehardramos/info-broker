from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


class RssMonitorNode:
    node_type = "rss_monitor"
    display_name = "RSS Monitor"
    category = "source"
    config_schema = {
        "type": "object",
        "properties": {
            "feed_url": {"type": "string", "format": "uri", "title": "Feed URL"},
            "max_items": {"type": "integer", "title": "Max Items", "default": 20, "minimum": 1, "maximum": 100},
        },
        "required": ["feed_url"],
    }

    async def execute(self, config: dict, inputs: list, context) -> list[dict]:
        import requests
        from xml.etree import ElementTree as ET

        feed_url = config.get("feed_url", "")
        max_items = int(config.get("max_items", 20))

        loop = asyncio.get_running_loop()
        items = await loop.run_in_executor(None, self._fetch_and_parse, feed_url, max_items)
        return items

    def _fetch_and_parse(self, feed_url: str, max_items: int) -> list[dict]:
        import requests
        from xml.etree import ElementTree as ET

        try:
            resp = requests.get(feed_url, timeout=15)
            resp.raise_for_status()
        except Exception as exc:
            log.warning("RssMonitorNode: failed to fetch %r: %s", feed_url, exc)
            return []

        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as exc:
            log.warning("RssMonitorNode: XML parse error: %s", exc)
            return []

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items: list[dict] = []

        # RSS 2.0
        for entry in root.findall(".//item")[:max_items]:
            title = (entry.findtext("title") or "").strip()
            url = (entry.findtext("link") or "").strip()
            snippet = (entry.findtext("description") or "").strip()
            pub_date = entry.findtext("pubDate")
            items.append({"title": title, "url": url, "snippet": snippet, "published_at": pub_date, "source": "rss"})

        # Atom
        if not items:
            for entry in root.findall("atom:entry", ns)[:max_items]:
                title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
                link_el = entry.find("atom:link", ns)
                url = (link_el.get("href") if link_el is not None else "") or ""
                snippet = (entry.findtext("atom:summary", namespaces=ns) or "").strip()
                pub_date = entry.findtext("atom:updated", namespaces=ns)
                items.append({"title": title, "url": url, "snippet": snippet, "published_at": pub_date, "source": "rss"})

        return items
