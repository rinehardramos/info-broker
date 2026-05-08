# app/pipeline/strategies/orchestrator.py
"""Research query orchestrator — classifies queries into research categories."""

from __future__ import annotations

# Category signal words, checked in priority order.
# NOTE: specific entity-type signals come before generic "person" signals so
# that queries like "Due diligence on Acme Corp" resolve to "due_diligence",
# not "person".  "profile " is kept before generation signals so that
# "Build a complete profile of Jane Smith" still resolves to "person".
_CATEGORY_SIGNALS: list[tuple[str, list[str]]] = [
    # --- Specific Retrieval variants (checked before generic person) ---
    ("due_diligence", ["due diligence", "kyc", "aml", "compliance check", "background check",
                       "risk assessment", "sanctions", "pep screen", "know your customer"]),
    ("company",       ["company profile", "competitor", "market analysis", "business registry",
                       "company investigation", "corporate profile", "company lookup"]),
    ("researcher",    ["papers", "publications", "academic", "citations", "scholar",
                       "research papers", "journal articles", "google scholar"]),
    ("lead",          ["find leads", "lead generation", "prospect list", "contact list",
                       "outreach", "sales leads", "prospecting", "build a prospect"]),
    # --- Generic person / knowledge signals ---
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


# ---------------------------------------------------------------------------
# Complexity scoring signals — (score_delta, list[signal_substrings])
# ---------------------------------------------------------------------------
_COMPLEXITY_SIGNALS: list[tuple[int, list[str]]] = [
    (-2, ["email of", "phone of", "address of"]),
    (-1, ["what is", "find ", "look up", "who is"]),
    (+2, ["vs", "versus", "compare "]),
    (+2, ["investigate", "analyze", "research ", "root cause"]),
    (+3, ["and also", " and "]),
    (+1, ["why ", "because"]),
    (+1, ["predict", "forecast", "what will"]),
]


def classify_complexity(query: str) -> tuple[str, int]:
    """Score *query* for research complexity and return a (tier, score) pair.

    Scoring rules
    -------------
    - Single entity markers ("email of", "phone of", "address of")  -2 each
    - Simple lookup verbs ("what is", "find ", "look up", "who is") -1 each
    - Multi-entity/comparison ("vs", "versus", "compare ")          +2 each
    - Open-ended verbs ("investigate", "analyze", "research ")      +2 each
    - Multi-domain conjunctions ("and also", " and ")               +3 each
    - Causal ("why ", "root cause", "because")                      +1 each
    - Predictive ("predict", "forecast", "what will")               +1 each
    - Long query (> 50 words)                                        +1

    Returns ``("simple", score)`` when score <= 0, ``("complex", score)`` otherwise.
    """
    if not query:
        return ("simple", 0)

    q = query.lower().strip()
    score = 0

    for delta, signals in _COMPLEXITY_SIGNALS:
        for signal in signals:
            if signal in q:
                score += delta

    if len(q.split()) > 50:
        score += 1

    tier = "simple" if score <= 0 else "complex"
    return (tier, score)
