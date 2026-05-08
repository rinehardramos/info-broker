"""Tests for technique catalog."""
from app.pipeline.techniques import TECHNIQUES, format_techniques_for_prompt

def test_techniques_has_entries():
    assert len(TECHNIQUES) >= 10

def test_technique_has_required_fields():
    for t in TECHNIQUES:
        assert "name" in t
        assert "description" in t
        assert "tactic" in t
        assert "tool_sequence" in t, f"Missing tool_sequence in {t['name']}"
        assert "when_to_use" in t
        assert len(t["tool_sequence"]) >= 1

def test_technique_names_unique():
    names = [t["name"] for t in TECHNIQUES]
    assert len(names) == len(set(names)), f"Duplicate technique names: {[n for n in names if names.count(n) > 1]}"

def test_format_produces_readable_text():
    text = format_techniques_for_prompt()
    assert "INVESTIGATION TECHNIQUES" in text
    assert "email_discovery" in text.lower() or "Email Discovery" in text
    assert "run_" in text  # tool references should use run_ prefix
    assert len(text) > 200

def test_format_includes_when_to_use():
    text = format_techniques_for_prompt()
    assert "when" in text.lower()

def test_email_discovery_technique_exists():
    email = next((t for t in TECHNIQUES if t["name"] == "email_discovery"), None)
    assert email is not None
    assert "email_enumerator" in email["tool_sequence"]
    assert "smtp_verifier" in email["tool_sequence"]

def test_web_search_technique_exists():
    web = next((t for t in TECHNIQUES if "search" in t["name"] and "web" in t["name"]), None)
    assert web is not None
    assert "multi_search" in web["tool_sequence"] or "ddg_search" in web["tool_sequence"]

def test_negative_screening_technique_exists():
    neg = next((t for t in TECHNIQUES if "screening" in t["name"] or "negative" in t["name"]), None)
    assert neg is not None
    assert "pep_sanctions_screen" in neg["tool_sequence"]
