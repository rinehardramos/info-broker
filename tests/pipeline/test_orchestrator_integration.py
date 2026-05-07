"""Integration: orchestrator + all strategies + compiler."""
from app.pipeline.strategies import get_strategy
from app.pipeline.strategies.orchestrator import classify_query

def test_all_strategies_loadable():
    """All 5 category strategies can be loaded."""
    for key in ["person", "generation", "explanation", "prediction", "synthesis"]:
        strategy = get_strategy(key)
        assert len(strategy) > 100, f"Strategy for {key} is empty or too short"

def test_orchestrator_routes_to_loadable_strategy():
    """Every query classification maps to a loadable strategy."""
    queries = [
        "Find everything about John Doe",
        "Build a new authentication system",
        "Why is our system slow?",
        "What trends will shape AI in 2027?",
        "Review all evidence on climate change",
    ]
    for q in queries:
        category = classify_query(q)
        strategy = get_strategy(category)
        assert len(strategy) > 100, f"Query '{q}' -> category '{category}' has no strategy"
