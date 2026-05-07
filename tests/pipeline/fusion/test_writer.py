"""Tests for KG observation writer."""
from __future__ import annotations
import asyncio
from unittest.mock import patch, call

from app.pipeline.fusion.writer import write_entities_to_kg, write_relationships_to_kg

def _arun(coro): return asyncio.run(coro)

def test_write_entities_inserts_observations():
    entities = [
        {"name": "John Doe", "type": "person", "attributes": {"role": "VP Sales", "company": "Acme"}},
    ]
    with patch("app.pipeline.fusion.writer.execute") as mock_exec:
        _arun(write_entities_to_kg("run-1", entities, "linkedin_profile"))
    # Should insert one observation per attribute + one for the name itself
    assert mock_exec.call_count >= 2  # name + role + company = 3 observations minimum

def test_write_entities_includes_confidence():
    entities = [{"name": "Test", "type": "person", "attributes": {}}]
    with patch("app.pipeline.fusion.writer.execute") as mock_exec:
        _arun(write_entities_to_kg("run-1", entities, "ph_sec_dti"))
    # ph_sec_dti is A-rated = high confidence
    args = mock_exec.call_args_list[0]
    # confidence param should be high (A-rated source)
    params = args[0][1]  # second arg is the tuple of params
    assert any(isinstance(p, int) and p >= 80 for p in params)

def test_write_entities_empty_list():
    with patch("app.pipeline.fusion.writer.execute") as mock_exec:
        _arun(write_entities_to_kg("run-1", [], "ddg_search"))
    assert mock_exec.call_count == 0

def test_write_relationships_inserts():
    rels = [
        {"from": "John Doe", "to": "Acme Corp", "type": "works_at", "evidence": "LinkedIn profile"},
    ]
    with patch("app.pipeline.fusion.writer.execute") as mock_exec:
        _arun(write_relationships_to_kg("run-1", rels, "linkedin_profile"))
    assert mock_exec.call_count == 1

def test_write_relationships_empty():
    with patch("app.pipeline.fusion.writer.execute") as mock_exec:
        _arun(write_relationships_to_kg("run-1", [], "ddg_search"))
    assert mock_exec.call_count == 0

def test_write_relationships_includes_source():
    rels = [{"from": "A", "to": "B", "type": "associates_with", "evidence": "co-mentioned"}]
    with patch("app.pipeline.fusion.writer.execute") as mock_exec:
        _arun(write_relationships_to_kg("run-1", rels, "facebook_pages"))
    sql = mock_exec.call_args_list[0][0][0]
    assert "relationship_observations" in sql
    params = mock_exec.call_args_list[0][0][1]
    assert "facebook_pages" in params
