from __future__ import annotations

import asyncio
import logging
import uuid

from app.search_engine import db
from app.search_engine.grading import score_result
from app.search_engine.plugins import PluginRegistry
from app.search_engine.plugins.base import PluginResult, SearchPlugin
from app.search_engine import qdrant as qdrant_module

log = logging.getLogger(__name__)

_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
        _registry.auto_discover()
    return _registry


def _deduplicate_results(results: list[PluginResult]) -> list[PluginResult]:
    seen_urls: set[str] = set()
    deduped: list[PluginResult] = []
    for r in results:
        if r.url is None:
            deduped.append(r)
            continue
        normalized = r.url.rstrip("/").lower()
        if normalized not in seen_urls:
            seen_urls.add(normalized)
            deduped.append(r)
    return deduped


class AsyncioSearchExecutor:
    def __init__(self) -> None:
        self._tasks: dict[uuid.UUID, asyncio.Task] = {}

    async def submit(self, *, query: str, config: dict, user_id: uuid.UUID) -> uuid.UUID:
        job_id = await db.create_job(user_id=user_id, query=query, config=config)
        task = asyncio.create_task(self._execute(job_id, query, config, user_id))
        self._tasks[job_id] = task
        return job_id

    async def cancel(self, job_id: uuid.UUID) -> bool:
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            await db.update_job_status(job_id, "cancelled")
            return True
        return False

    async def _execute(self, job_id: uuid.UUID, query: str, config: dict, user_id: uuid.UUID) -> None:
        try:
            await db.update_job_status(job_id, "running")
            registry = get_registry()
            requested_plugins = config.get("plugins")
            if requested_plugins:
                plugins = [p for p in registry.available() if p.name in requested_plugins]
            else:
                plugins = registry.available()
            if not plugins:
                await db.update_job_status(job_id, "failed", error="no plugins available")
                return
            max_parallel = config.get("max_parallel") or len(plugins)
            max_budget = config.get("max_budget", 5)
            per_plugin_limit = max(1, max_budget // len(plugins))
            sem = asyncio.Semaphore(max_parallel)

            async def run_plugin(plugin: SearchPlugin) -> list[PluginResult]:
                async with sem:
                    return await plugin.search(query, max_results=per_plugin_limit)

            all_results_nested = await asyncio.gather(
                *[run_plugin(p) for p in plugins], return_exceptions=True,
            )
            all_results: list[PluginResult] = []
            for result_or_exc in all_results_nested:
                if isinstance(result_or_exc, BaseException):
                    log.warning("Plugin raised: %s", result_or_exc)
                    continue
                all_results.extend(result_or_exc)

            deduped = _deduplicate_results(all_results)[:max_budget]

            for plugin_result in deduped:
                scores = score_result(
                    query=query, title=plugin_result.title,
                    snippet=plugin_result.snippet, url=plugin_result.url,
                    published_at=plugin_result.published_at,
                )
                result_id = await db.insert_result(
                    job_id=job_id,
                    plugin=plugin_result.source_name.lower().replace(" ", "_"),
                    title=plugin_result.title, url=plugin_result.url,
                    published_at=plugin_result.published_at,
                    heuristic_scores=scores,
                )
                try:
                    qdrant_module.upsert_result(
                        result_id=result_id, job_id=job_id, user_id=user_id,
                        plugin=plugin_result.source_name, title=plugin_result.title,
                        url=plugin_result.url, snippet=plugin_result.snippet,
                        full_text=plugin_result.full_text,
                    )
                except Exception as exc:
                    log.warning("Qdrant upsert failed for %s: %s", result_id, exc)

            await db.update_job_status(job_id, "completed")
        except asyncio.CancelledError:
            await db.update_job_status(job_id, "cancelled")
            raise
        except Exception as exc:
            log.exception("Search job %s failed", job_id)
            await db.update_job_status(job_id, "failed", error=str(exc))
        finally:
            self._tasks.pop(job_id, None)
