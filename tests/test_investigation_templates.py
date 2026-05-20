"""Tests for built-in investigation templates."""
from __future__ import annotations

from app.routers.v3.investigation_templates import (
    INVESTIGATION_TEMPLATES, render_query,
)


def test_templates_have_required_fields():
    """Every template must have stable fields the UI relies on."""
    REQUIRED = {"id", "name", "description", "icon", "category",
                "query_template", "parameters"}
    seen_ids: set[str] = set()
    for tpl in INVESTIGATION_TEMPLATES:
        missing = REQUIRED - tpl.keys()
        assert not missing, f"{tpl.get('id')}: missing {missing}"
        # IDs must be unique (slug-y)
        assert tpl["id"] not in seen_ids
        seen_ids.add(tpl["id"])
        # category must be one of the documented values
        assert tpl["category"] in {"kyc", "due-diligence", "market", "finance",
                                   "identity", "general"}
        # Parameters all have name+label+type
        for p in tpl["parameters"]:
            assert {"name", "label", "type"} <= p.keys()


def test_render_query_substitutes_placeholders():
    rendered = render_query("kyc-individual",
                            {"full_name": "Jane Doe", "employer": "Acme Corp"})
    assert "Jane Doe" in rendered
    assert "Acme Corp" in rendered
    # Placeholders must be substituted (no {{var}} remaining)
    assert "{{" not in rendered


def test_render_query_handles_missing_optional_params():
    """Omitting an optional param should NOT leave the {{var}} placeholder in
    the rendered text — it must be substituted with a clear marker so the
    brain understands the variable was intentionally empty."""
    rendered = render_query("kyc-individual", {"full_name": "Jane Doe"})
    assert "Jane Doe" in rendered
    assert "{{" not in rendered
    assert "(not specified)" in rendered


def test_render_query_unknown_template_raises():
    try:
        render_query("does-not-exist", {})
        raise AssertionError("expected KeyError")
    except KeyError:
        pass


def test_all_query_templates_render_with_empty_params():
    """Smoke check: every template renders with EMPTY params (placeholders all
    substituted to '(not specified)'). Catches typos in {{var}} names."""
    for tpl in INVESTIGATION_TEMPLATES:
        rendered = render_query(tpl["id"], {})
        assert "{{" not in rendered, f"{tpl['id']} has unsubstituted placeholders: {rendered}"
