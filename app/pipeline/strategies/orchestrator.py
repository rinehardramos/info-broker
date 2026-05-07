# app/pipeline/strategies/orchestrator.py
"""Research query orchestrator — classifies queries into research categories."""

from __future__ import annotations

# Category signal words, checked in priority order.
# NOTE: "profile " is listed before generation signals so that queries like
# "Build a complete profile of Jane Smith" resolve to "person", not "generation".
_CATEGORY_SIGNALS: list[tuple[str, list[str]]] = [
    ("person", ["profile "]),
    ("generation", ["build a ", "create a ", "design a ", "invent ", "develop a ", "make a new ", "implement a "]),
    ("explanation", ["why ", "root cause", "diagnose", "how does", "explain why", "what caused", "debug"]),
    ("prediction", ["predict", "forecast", "trend", "future of", "what will", "where is .* going", "outlook"]),
    ("synthesis", ["review ", "summarize ", "compare ", "evaluate ", "assess ", "analyze the evidence", "state of "]),
    ("person", ["investigate", "find ", "background check", "who is", "look up", "research "]),
]


def classify_query(query: str) -> str:
    """Classify a research query into a category.

    Returns one of: "person", "generation", "explanation", "prediction", "synthesis".
    Defaults to "person" (Retrieval) for ambiguous queries.
    """
    if not query:
        return "person"

    q = query.lower().strip()

    for category, signals in _CATEGORY_SIGNALS:
        for signal in signals:
            if signal in q:
                return category

    return "person"  # Default: Retrieval
