"""Tests for media identification strategy + orchestrator routing."""
from app.pipeline.strategies import get_strategy
from app.pipeline.strategies.orchestrator import classify_query


def test_media_identification_strategy_loads():
    s = get_strategy("media_identification")
    assert "MEDIA IDENTIFICATION STRATEGY" in s
    assert "MULTI-HYPOTHESIS" in s
    assert "run_tmdb_search" in s
    assert len(s) > 1000


def test_media_strategy_has_completeness():
    s = get_strategy("media_identification")
    assert "COMPLETENESS CHECKLIST" in s


def test_orchestrator_routes_show_query():
    assert classify_query("new series with girl in spiderman where man has a shotgun") == "media_identification"


def test_orchestrator_routes_what_show():
    assert classify_query("what show is this with the blonde actress?") == "media_identification"


def test_orchestrator_routes_what_movie():
    assert classify_query("what movie has the car chase scene in tokyo?") == "media_identification"


def test_orchestrator_routes_new_series():
    assert classify_query("new series on Netflix with zombies") == "media_identification"


def test_orchestrator_routes_actress_from():
    assert classify_query("actress from spider-man now in a drama series") == "media_identification"


def test_person_query_still_routes_person():
    assert classify_query("Find everything about John Doe") == "person"
