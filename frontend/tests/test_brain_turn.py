

def test_init_working_memory_applies_decay_to_old_graded_priors():
    """A user-graded prior observed >shelf_life ago should be decayed before
    auto-seeding it as an established_fact — old data shouldn't be injected
    at full confidence."""
    from datetime import datetime, timezone, timedelta
    from unittest.mock import patch
    from app.memory.models import MemoryResult
    from app.temporal.activities.brain_turn import (
        InitWorkingMemoryInput, init_working_memory,
    )

    old_iso = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    # source_tool 'phone_osint' maps to data_type='phone' with 180-day exponential decay
    old_prior = MemoryResult(
        ref="r1", title="Old phone number lookup", content="555-1234",
        source="semantic", score=0.7, run_id="prior-run",
        user_score=1, observed_at=old_iso, source_tool="phone_osint",
    )
    async def _fake_fused_retrieve(*a, **kw):
        return [old_prior]

    inp = InitWorkingMemoryInput(
        run_id=str(uuid4()), user_id=str(uuid4()), query="phone for X",
        past_research=[],
    )
    with patch("app.memory.retriever.fused_retrieve", side_effect=_fake_fused_retrieve), \
         patch("app.temporal.activities.brain_turn._snapshot_to_db"):
        wm_json = asyncio.run(init_working_memory(inp))

    wm = WorkingMemory.model_validate_json(wm_json)
    # cross_run_priors record carries the decay metadata
    p = wm.cross_run_priors[0]
    assert p["data_type"] == "phone"
    assert p["base_confidence"] == 80
    # 200 days at exponential with 180-day shelf = factor ~e^(-1.11) ~ 0.33 → ~26
    assert 0 < p["decayed_confidence"] < 60, p
    # Seeded fact uses the decayed value, not hardcoded 0.9
    assert len(wm.established_facts) == 1
    fact_conf = wm.established_facts[0].confidence
    assert 0 < fact_conf < 0.6
    assert fact_conf == p["decayed_confidence"] / 100.0


def test_init_working_memory_skips_seeding_when_decayed_to_zero():
    """If decay produces confidence==0, don't seed a fact at all (would be
    misleading to inject a 0-confidence established_fact)."""
    from datetime import datetime, timezone, timedelta
    from unittest.mock import patch
    from app.memory.models import MemoryResult
    from app.temporal.activities.brain_turn import (
        InitWorkingMemoryInput, init_working_memory,
    )

    # social_media: 90-day linear decay → 200 days = factor 0 → decayed = 0
    very_old_iso = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    stale_prior = MemoryResult(
        ref="r1", title="Old social", content="x", source="semantic",
        score=0.7, run_id="r", user_score=1,
        observed_at=very_old_iso, source_tool="facebook_pages",
    )
    async def _fake_fused_retrieve(*a, **kw):
        return [stale_prior]

    inp = InitWorkingMemoryInput(
        run_id=str(uuid4()), user_id=str(uuid4()), query="x",
        past_research=[],
    )
    with patch("app.memory.retriever.fused_retrieve", side_effect=_fake_fused_retrieve), \
         patch("app.temporal.activities.brain_turn._snapshot_to_db"):
        wm_json = asyncio.run(init_working_memory(inp))

    wm = WorkingMemory.model_validate_json(wm_json)
    assert wm.cross_run_priors[0]["decayed_confidence"] == 0
    # No seeded fact (would have been confidence=0 — misleading)
    assert wm.established_facts == []
