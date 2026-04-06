"""info-broker FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.lib.rate_limit import limiter
from app.routers import media, profiles, research, search

app = FastAPI(
    title="info-broker",
    version="0.4.0",
    description=(
        "Information-gathering and OSINT research service. Hosts both the OSINT "
        "/profiles surface and the /v1/* media surface (weather, news, songs, "
        "jokes, social mentions) consumed by the playgen-dj microservice."
    ),
)

# slowapi rate limiter — applies the per-key bucket defined in app/lib/rate_limit.py.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.get("/healthz", tags=["health"])
def healthz() -> dict:
    return {"status": "ok"}


app.include_router(profiles.router)
app.include_router(research.router)
app.include_router(search.router)
app.include_router(media.router)
