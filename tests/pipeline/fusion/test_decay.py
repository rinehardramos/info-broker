"""Tests for perishability/decay model."""
from datetime import datetime, timedelta, timezone
from app.pipeline.fusion.decay import (
    get_shelf_life, calculate_decay, apply_decay_to_findings,
    SHELF_LIVES,
)

def test_shelf_lives_defined():
    assert len(SHELF_LIVES) >= 8
    assert "phone" in SHELF_LIVES
    assert "email" in SHELF_LIVES
    assert "criminal_record" in SHELF_LIVES

def test_shelf_life_phone():
    sl = get_shelf_life("phone")
    assert sl["days"] == 180  # 6 months
    assert sl["decay"] == "exponential"

def test_shelf_life_criminal():
    sl = get_shelf_life("criminal_record")
    assert sl["days"] >= 3650  # 10+ years
    assert sl["decay"] == "none"

def test_shelf_life_unknown():
    sl = get_shelf_life("unknown_type")
    assert sl["days"] == 365  # default 1 year
    assert sl["decay"] == "linear"

def test_decay_fresh_data():
    """Data collected today should have no decay."""
    now = datetime.now(timezone.utc)
    result = calculate_decay(90, now, "email")
    assert result == 90  # No decay

def test_decay_half_life():
    """Data at half its shelf life should be partially decayed."""
    now = datetime.now(timezone.utc)
    three_months_ago = now - timedelta(days=90)  # Half of email shelf life (180 days)
    result = calculate_decay(90, three_months_ago, "email")
    assert 40 < result < 90  # Decayed but not zero

def test_decay_expired():
    """Data past its shelf life should be heavily decayed."""
    now = datetime.now(timezone.utc)
    one_year_ago = now - timedelta(days=365)
    result = calculate_decay(90, one_year_ago, "email")
    assert result < 30  # Heavily decayed

def test_decay_permanent():
    """Criminal records don't decay."""
    now = datetime.now(timezone.utc)
    ten_years_ago = now - timedelta(days=3650)
    result = calculate_decay(90, ten_years_ago, "criminal_record")
    assert result == 90  # No decay

def test_decay_never_negative():
    result = calculate_decay(50, datetime(2020, 1, 1, tzinfo=timezone.utc), "phone")
    assert result >= 0

def test_apply_decay_enriches_findings():
    now = datetime.now(timezone.utc)
    findings = [
        {"content": "Phone: +1234567890", "source": "phone_osint",
         "confidence": 80, "collected_at": now.isoformat()},
        {"content": "Criminal record: none", "source": "pep_sanctions_screen",
         "confidence": 90, "collected_at": (now - timedelta(days=365)).isoformat()},
    ]
    result = apply_decay_to_findings(findings)
    assert len(result) == 2
    # Phone (recent) should keep most confidence
    assert result[0]["decayed_confidence"] >= 70
    # Criminal record (1 year old but permanent) should keep all confidence
    assert result[1]["decayed_confidence"] == 90
    # Both should have shelf_life info
    assert "shelf_life_days" in result[0]
    assert "decay_function" in result[0]
