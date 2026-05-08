"""Perishability and temporal confidence decay for research findings."""

from __future__ import annotations
import math
from datetime import datetime, timezone

# Data type shelf lives and decay functions
# Based on investigation strategy spec Section 5.5
SHELF_LIVES: dict[str, dict] = {
    "phone": {"days": 180, "decay": "exponential"},
    "email": {"days": 180, "decay": "exponential"},
    "social_media": {"days": 90, "decay": "linear"},
    "employment": {"days": 365, "decay": "step"},
    "company_registration": {"days": 1825, "decay": "linear"},  # 5 years
    "criminal_record": {"days": 36500, "decay": "none"},  # permanent
    "address": {"days": 365, "decay": "linear"},
    "breach_data": {"days": 36500, "decay": "none"},  # permanent (historical fact)
    "sanctions": {"days": 180, "decay": "exponential"},
    "financial": {"days": 90, "decay": "exponential"},
}

# Map source tools to data types for shelf life lookup
_SOURCE_TO_TYPE: dict[str, str] = {
    "phone_osint": "phone",
    "messaging_check": "phone",
    "smtp_verifier": "email",
    "email_enumerator": "email",
    "hunter_io": "email",
    "hibp_lookup": "breach_data",
    "linkedin_profile": "employment",
    "apollo_zoominfo": "employment",
    "facebook_pages": "social_media",
    "instagram_profile": "social_media",
    "twitter_search": "social_media",
    "ph_sec_dti": "company_registration",
    "opencorporates": "company_registration",
    "sec_edgar": "company_registration",
    "pep_sanctions_screen": "criminal_record",
    "adverse_media": "sanctions",
    "crypto_tracer": "financial",
    "whois_lookup": "company_registration",
    "reverse_lookup": "email",
    "username_enumerator": "social_media",
}

_DEFAULT_SHELF_LIFE = {"days": 365, "decay": "linear"}


def get_shelf_life(data_type: str) -> dict:
    """Get shelf life config for a data type."""
    return SHELF_LIVES.get(data_type, _DEFAULT_SHELF_LIFE)


def calculate_decay(
    base_confidence: int,
    collected_at: datetime,
    data_type: str,
) -> int:
    """Calculate decayed confidence based on age and data type.

    Returns confidence integer (0-100), never negative.
    """
    shelf = get_shelf_life(data_type)
    decay_fn = shelf["decay"]
    shelf_days = shelf["days"]

    if decay_fn == "none":
        return base_confidence

    now = datetime.now(timezone.utc)
    if collected_at.tzinfo is None:
        collected_at = collected_at.replace(tzinfo=timezone.utc)

    age_days = (now - collected_at).total_seconds() / 86400
    # Treat data collected within the last second as fresh (avoids float skew)
    if age_days < 1 / 86400:
        return base_confidence

    ratio = age_days / shelf_days  # 0 = fresh, 1 = at shelf life, >1 = expired

    if decay_fn == "exponential":
        # Exponential decay: confidence * e^(-ratio)
        # At half shelf life (ratio=0.5): factor ~= 0.607 (keeps >60% confidence)
        # At full shelf life (ratio=1):   factor ~= 0.368
        # At 2x shelf life (ratio=2):     factor ~= 0.135
        factor = math.exp(-ratio)
    elif decay_fn == "step":
        # Step decay: full confidence until shelf life, then drop to 30%
        factor = 1.0 if ratio < 1.0 else 0.3
    else:  # linear
        factor = max(0.0, 1.0 - ratio)

    decayed = int(base_confidence * factor)
    return max(0, decayed)


def apply_decay_to_findings(findings: list[dict]) -> list[dict]:
    """Enrich findings with decayed confidence based on age and source type."""
    results = []
    for f in findings:
        source = f.get("source", f.get("source_tool", "unknown"))
        data_type = _SOURCE_TO_TYPE.get(source, "unknown")
        shelf = get_shelf_life(data_type)

        base_conf = f.get("confidence", 50)

        # Parse collected_at
        collected_str = f.get("collected_at") or f.get("observed_at")
        if collected_str:
            try:
                if isinstance(collected_str, str):
                    collected = datetime.fromisoformat(collected_str.replace("Z", "+00:00"))
                else:
                    collected = collected_str
            except (ValueError, TypeError):
                collected = datetime.now(timezone.utc)
        else:
            collected = datetime.now(timezone.utc)  # Assume fresh if no timestamp

        decayed = calculate_decay(base_conf, collected, data_type)

        results.append({
            **f,
            "decayed_confidence": decayed,
            "shelf_life_days": shelf["days"],
            "decay_function": shelf["decay"],
            "data_type": data_type,
        })

    return results
