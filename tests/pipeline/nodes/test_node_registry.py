"""Test new OSINT nodes are registered."""
from app.pipeline.nodes import NodeRegistry

def test_smtp_verifier_registered():
    NodeRegistry.auto_discover()
    assert NodeRegistry.get("smtp_verifier").node_type == "smtp_verifier"

def test_hibp_lookup_registered():
    NodeRegistry.auto_discover()
    assert NodeRegistry.get("hibp_lookup").node_type == "hibp_lookup"

def test_reverse_lookup_registered():
    NodeRegistry.auto_discover()
    assert NodeRegistry.get("reverse_lookup").node_type == "reverse_lookup"

def test_email_enumerator_registered():
    NodeRegistry.auto_discover()
    assert NodeRegistry.get("email_enumerator").node_type == "email_enumerator"
