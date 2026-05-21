"""Strategy catalog entry: place.

Place / route / navigation queries. Default mode: data_retrieval (geocoders
and map APIs are structured sources).
"""
from __future__ import annotations

from app.pipeline.catalogs.builders.research_skeleton import build_research_strategy

STRATEGY = build_research_strategy(
    id="place",
    default_mode="data_retrieval",
    hypothesis_count="single",
    applies_to={
        "signals": ["route_to", "directions_to", "how_to_get_to", "distance_from"],
        "entity_types": ["place", "address", "landmark"],
    },
    extract={
        "briefing": (
            "Identify the place(s) in the query: city, neighborhood, landmark, "
            "or address. Classify the user's intent — geocoding only, route "
            "between two places, area context (what's near X), distance "
            "calculation, or local-search around the place. Emit a structured "
            "place spec + intent flag."
        ),
    },
    gather={
        "briefing": (
            "Geocode every place named in the query to (lat, lon). Then "
            "fulfil the user's intent: routing APIs for directions, "
            "reverse-geocoding for area context, Overpass / Wikipedia for "
            "landmark details, places-API for local search. Capture raw "
            "responses with their source."
        ),
        "gate_checks": [
            {"kind": "coordinates_present", "params": {}},
        ],
    },
    synthesize={
        "briefing": (
            "Return the resolved coordinates and the requested derivative "
            "(turn-by-turn route, area description, POI list). Cite the "
            "geocoder/map source per claim."
        ),
    },
)
