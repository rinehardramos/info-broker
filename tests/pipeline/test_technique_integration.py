"""Integration: multi-search + technique catalog + IS brain prompt."""
from app.pipeline.nodes import NodeRegistry
from app.pipeline.techniques import TECHNIQUES, format_techniques_for_prompt
from app.is_prompt import build_prompt


def test_multi_search_discoverable():
    NodeRegistry.auto_discover()
    node = NodeRegistry.get("multi_search")
    assert node.category == "source"


def test_techniques_reference_registered_nodes():
    """All tools referenced in techniques should be registered nodes."""
    NodeRegistry.auto_discover()
    registered = {n.node_type for n in NodeRegistry.all()}
    for tech in TECHNIQUES:
        for tool in tech["tool_sequence"]:
            assert tool in registered, (
                f"Technique '{tech['name']}' references unregistered tool '{tool}'"
            )


def test_techniques_injected_into_prompt():
    techniques = format_techniques_for_prompt()
    prompt = build_prompt(
        query="Find John Doe",
        techniques_section=techniques,
    )
    assert "INVESTIGATION TECHNIQUES" in prompt
    assert "Email Discovery" in prompt or "email_discovery" in prompt
    assert prompt.index("INVESTIGATION TECHNIQUES") < prompt.index("YOUR WORKFLOW")


def test_full_prompt_has_all_layers():
    """Prompt should contain: strategy + techniques + workflow."""
    prompt = build_prompt(
        query="test",
        entity_strategy="=== STRATEGY ===",
        techniques_section="=== TECHNIQUES ===",
        strategies_section="=== SUGGESTED ===",
    )
    s = prompt.index("=== STRATEGY ===")
    t = prompt.index("=== TECHNIQUES ===")
    sg = prompt.index("=== SUGGESTED ===")
    w = prompt.index("YOUR WORKFLOW")
    assert s < t < sg < w, "Prompt layers must be ordered: strategy < techniques < suggested < workflow"
