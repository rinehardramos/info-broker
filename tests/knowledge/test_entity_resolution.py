from __future__ import annotations

from unittest.mock import patch

from app.knowledge.entity_resolution import normalize_entity_type, resolve_entity_ref


# ---------------------------------------------------------------------------
# normalize_entity_type
# ---------------------------------------------------------------------------


def test_normalize_type_company():
    assert normalize_entity_type("company") == "organization"


def test_normalize_type_org():
    assert normalize_entity_type("org") == "organization"


def test_normalize_type_person_lowercase():
    assert normalize_entity_type("person") == "person"


def test_normalize_type_person_uppercase():
    assert normalize_entity_type("PERSON") == "person"


def test_normalize_type_unknown_passthrough():
    assert normalize_entity_type("location") == "location"


# ---------------------------------------------------------------------------
# resolve_entity_ref — no alias match returns original ref
# ---------------------------------------------------------------------------


def test_exact_ref_match_no_alias():
    """When fetch_one returns None for both lookups, original ref is returned."""
    with patch("app.knowledge.entity_resolution.fetch_one", return_value=None):
        result = resolve_entity_ref(
            "person::john-doe", "person", "John Doe"
        )
    assert result == "person::john-doe"


# ---------------------------------------------------------------------------
# resolve_entity_ref — alias match returns canonical ref
# ---------------------------------------------------------------------------


def test_alias_match_returns_canonical():
    """When fetch_one finds an alias, the canonical_ref is returned."""
    canonical = "person::john-doe-ceo"
    with patch(
        "app.knowledge.entity_resolution.fetch_one",
        return_value={"canonical_ref": canonical},
    ):
        result = resolve_entity_ref(
            "person::john-doe", "person", "John Doe"
        )
    assert result == canonical
