"""info-broker FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI

from app.routers import profiles, research, search

app = FastAPI(
    title="info-broker",
    version="0.3.0",
    description=(
        "Information-gathering and OSINT research service. Derived from "
        "auto-marketer-project with marketing/outreach code removed."
    ),
)


@app.get("/healthz", tags=["health"])
def healthz() -> dict:
    return {"status": "ok"}


app.include_router(profiles.router)
app.include_router(research.router)
app.include_router(search.router)
