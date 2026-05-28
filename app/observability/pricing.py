"""PricingResolver — in-process cache for llm_pricing Postgres rows."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus
from uuid import UUID

log = logging.getLogger(__name__)


def _to_asyncpg_dsn(dsn: str) -> str:
    """Convert a libpq keyword-pair DSN to a postgresql:// URL for asyncpg.

    asyncpg 0.29+ requires a URL-scheme DSN; it rejects the libpq
    ``key=value`` form.  If ``dsn`` already starts with ``postgresql://`` or
    ``postgres://`` it is returned unchanged.
    """
    if dsn.lstrip().startswith(("postgresql://", "postgres://")):
        return dsn

    # Parse key=value pairs (handles quoted values with spaces)
    params: dict[str, str] = {}
    for token in dsn.split():
        if "=" in token:
            k, _, v = token.partition("=")
            params[k.strip()] = v.strip()

    host = params.get("host", "localhost")
    port = params.get("port", "5432")
    user = params.get("user", "")
    password = params.get("password", "")
    dbname = params.get("dbname", "")

    userinfo = quote_plus(user)
    if password:
        userinfo = f"{userinfo}:{quote_plus(password)}"
    return f"postgresql://{userinfo}@{host}:{port}/{dbname}"


@dataclass(frozen=True)
class PriceSnapshot:
    pricing_id: UUID
    model_id: str
    provider: str
    input_usd_per_1m: float
    output_usd_per_1m: float
    cache_creation_usd_per_1m: float | None
    cache_read_usd_per_1m: float | None

    def cost_for(self, usage: dict[str, Any]) -> tuple[float, str, UUID]:
        input_tok = int(usage.get("input_tokens") or 0)
        output_tok = int(usage.get("output_tokens") or 0)
        cache_create_tok = int(usage.get("cache_creation_input_tokens") or 0)
        cache_read_tok = int(usage.get("cache_read_input_tokens") or 0)

        cost = (input_tok / 1_000_000) * self.input_usd_per_1m
        cost += (output_tok / 1_000_000) * self.output_usd_per_1m
        if self.cache_creation_usd_per_1m is not None:
            cost += (cache_create_tok / 1_000_000) * self.cache_creation_usd_per_1m
        if self.cache_read_usd_per_1m is not None:
            cost += (cache_read_tok / 1_000_000) * self.cache_read_usd_per_1m

        return (cost, "estimated", self.pricing_id)


class PricingResolver:
    def __init__(self, db_dsn: str, *, ttl_seconds: int = 60) -> None:
        self._dsn = db_dsn
        self._asyncpg_dsn = _to_asyncpg_dsn(db_dsn)
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[PriceSnapshot | None, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, model_id: str) -> PriceSnapshot | None:
        async with self._lock:
            cached, fetched_at = self._cache.get(model_id, (None, 0.0))
            if fetched_at and (time.monotonic() - fetched_at) < self._ttl:
                return cached
            snap = await self._fetch(model_id)
            self._cache[model_id] = (snap, time.monotonic())
            return snap

    async def _fetch(self, model_id: str) -> PriceSnapshot | None:
        try:
            import asyncpg
        except ImportError:
            log.error("pricing: asyncpg not installed")
            return None

        try:
            conn = await asyncpg.connect(dsn=self._asyncpg_dsn)
            try:
                row = await conn.fetchrow(
                    """
                    SELECT id, model_id, provider,
                           input_usd_per_1m::float8       AS input_usd_per_1m,
                           output_usd_per_1m::float8      AS output_usd_per_1m,
                           cache_creation_usd_per_1m::float8 AS cache_creation_usd_per_1m,
                           cache_read_usd_per_1m::float8  AS cache_read_usd_per_1m
                    FROM llm_pricing
                    WHERE model_id = $1 AND effective_from <= now()
                    ORDER BY effective_from DESC
                    LIMIT 1
                    """,
                    model_id,
                )
            finally:
                await conn.close()
        except Exception as exc:
            log.warning("pricing: PG fetch failed for %r: %s", model_id, exc)
            return None

        if row is None:
            return None

        return PriceSnapshot(
            pricing_id=UUID(str(row["id"])),
            model_id=row["model_id"],
            provider=row["provider"],
            input_usd_per_1m=float(row["input_usd_per_1m"]),
            output_usd_per_1m=float(row["output_usd_per_1m"]),
            cache_creation_usd_per_1m=(
                float(row["cache_creation_usd_per_1m"])
                if row["cache_creation_usd_per_1m"] is not None else None
            ),
            cache_read_usd_per_1m=(
                float(row["cache_read_usd_per_1m"])
                if row["cache_read_usd_per_1m"] is not None else None
            ),
        )

    def invalidate(self, model_id: str) -> None:
        self._cache.pop(model_id, None)

    def invalidate_all(self) -> None:
        self._cache.clear()
