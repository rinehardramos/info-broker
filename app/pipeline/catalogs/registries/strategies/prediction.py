"""Strategy catalog entry: prediction.

Forecast / outlook queries. Default mode: market_analysis (comparative
trend reasoning over historical data).
"""
from __future__ import annotations

from app.pipeline.catalogs.builders.research_skeleton import build_research_strategy

STRATEGY = build_research_strategy(
    id="prediction",
    default_mode="market_analysis",
    hypothesis_count="competing",
    applies_to={
        "signals": ["predict", "forecast", "trend", "future_of", "what_will", "outlook"],
        "entity_types": [],
    },
    extract={
        "briefing": (
            "Identify: the outcome metric to forecast, the time horizon, the "
            "subject(s), and the drivers the user wants modelled. If the "
            "outcome is implicit (e.g. 'will Bitcoin go up?' → price), name "
            "it explicitly. Note any priors the user is asserting."
        ),
    },
    gather={
        "briefing": (
            "Pull historical data for the outcome metric (time series if "
            "available). Gather current values for each driver. Search for "
            "analogous past situations and how those resolved. Capture data "
            "sources with date ranges."
        ),
    },
    synthesize={
        "briefing": (
            "Provide a directional forecast with an explicit confidence band "
            "(e.g. 'likely +10 to +25% over 12 months, low confidence'). "
            "Identify the top driver of uncertainty and which signal would "
            "tighten the band. Resist false precision when data is sparse."
        ),
        "gate_checks": [
            {"kind": "confidence_band_present", "params": {}},
        ],
    },
)
