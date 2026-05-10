"""Integration: strategy injection + new nodes for IS brain."""
from app.is_prompt import build_prompt
from app.pipeline.strategies import get_strategy
from app.pipeline.nodes import NodeRegistry

def test_full_strategy_injection():
    strategy = get_strategy("person")
    prompt = build_prompt(query="Find everything about John Doe", entity_strategy=strategy)
    assert "PERSON INVESTIGATION STRATEGY" in prompt
    assert prompt.index("PERSON INVESTIGATION STRATEGY") < prompt.index("YOUR WORKFLOW")

def test_new_nodes_discoverable():
    NodeRegistry.auto_discover()
    for nt in ["smtp_verifier", "hibp_lookup", "reverse_lookup", "email_enumerator"]:
        assert NodeRegistry.get(nt).category == "enrich"

def test_strategy_mentions_new_tools():
    strategy = get_strategy("person")
    assert "smtp_verifier" in strategy
    assert "hibp_lookup" in strategy
    assert "reverse_lookup" in strategy
