"""Tests for app.security.sanitize_check_detail.

Per spec §Sanitization contract: deny by default. Allowed values:
- int, float, bool
- str ≤ 120 chars (applies to every string, top-level and nested)
- list of allowed values
- dict of allowed values (one level deep)
Forbidden: Exception objects, raw tracebacks, file paths (/, C:\\),
verbatim query/finding content (caller's responsibility), nested dicts beyond one level.
"""
import pytest
from app.security import sanitize_check_detail


def test_allowed_primitives_pass_through():
    inp = {"a": 1, "b": 2.5, "c": True, "d": "hello"}
    assert sanitize_check_detail(inp) == inp


def test_string_truncated_at_120_chars():
    long = "x" * 200
    out = sanitize_check_detail({"k": long})
    assert len(out["k"]) == 120


def test_nested_string_also_truncated():
    long = "y" * 200
    out = sanitize_check_detail({"k": {"nested": long}})
    assert len(out["k"]["nested"]) == 120


def test_list_of_strings_truncated_per_item():
    out = sanitize_check_detail({"k": ["a" * 200, "b" * 200]})
    assert all(len(s) == 120 for s in out["k"])


def test_exception_object_dropped():
    out = sanitize_check_detail({"err": Exception("boom"), "ok": 1})
    assert "err" not in out
    assert out["ok"] == 1


def test_absolute_unix_path_dropped():
    out = sanitize_check_detail({"path": "/home/user/secret.key", "ok": 1})
    assert "path" not in out
    assert out["ok"] == 1


def test_absolute_windows_path_dropped():
    out = sanitize_check_detail({"path": r"C:\Users\admin\creds.json", "ok": 1})
    assert "path" not in out
    assert out["ok"] == 1


def test_nested_dict_beyond_one_level_dropped():
    out = sanitize_check_detail({"l1": {"l2": {"l3": "too deep"}}})
    # l1 itself is one-level-deep dict; nested l2 dict should be dropped
    # leaving an empty l1 dict (or l1 dropped entirely — either is acceptable)
    if "l1" in out:
        assert "l2" not in out["l1"]


def test_unknown_type_dropped():
    class Custom:
        pass
    out = sanitize_check_detail({"obj": Custom(), "ok": 1})
    assert "obj" not in out
    assert out["ok"] == 1


def test_empty_dict_returns_empty():
    assert sanitize_check_detail({}) == {}


def test_none_returns_empty():
    assert sanitize_check_detail(None) == {}
