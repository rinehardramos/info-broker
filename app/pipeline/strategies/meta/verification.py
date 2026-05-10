"""OSINT Verification meta-strategy module."""

NAME = "osint_verification"
DISPLAY_NAME = "OSINT Verification"
DESCRIPTION = "Media artifact verification, geolocation, source reliability rating, and media forensics."
TRIGGER_SIGNALS = [
    "verify", "confirm", "fake", "authentic", "real", "disinformation",
    "propaganda", "manipulated", "geolocation", "photo", "video", "image",
    "media", "coordinated", "bot", "inauthentic", "influence operation",
]
ENTITY_TYPES = ["all"]
ALWAYS_ON = False

STRATEGY_TEXT = """
=== OSINT VERIFICATION META-STRATEGY ===

GEOLOCATION (hypothesis-test sequence):
  1. identify place-bearing observables: skyline, signage, vegetation, shadow angle, road markings
  2. generate candidate location -> list observables that SHOULD be true there
  3. verify each: Google Earth | Sentinel Hub | Yandex Maps | Mapillary | OSM | Wikimapia
  4. reject candidate on FIRST verified observable failure (no averaging mismatches)
  confidence: GEOLOCATED (all verified) | PROBABLE (>=3 verified, none falsified) | CANDIDATE | UNVERIFIED

MEDIA_FORENSICS:
  - reverse image search (run_face_search, TinEye, Yandex) -> find earliest occurrence
  - EXIF: run_exif_extractor (treat GPS/timestamps as CANDIDATE — strippable/spoofable)
  - visual checks: inconsistent shadow direction | compression artifact mismatches | noise pattern inconsistencies
  # Note: chronolocation (shadow-angle dating, weather archive) canonical home: temporal_analysis.py
  # Note: CIB/sock puppet detection canonical home: platform_social_intel.py

ADMIRALTY_CODE [applies under due_diligence entity_type]:
  source: A=completely reliable | B=usually reliable | C=fairly reliable | D=not usually reliable | E=unreliable | F=cannot judge
  info:   1=confirmed independent | 2=probably true | 3=possibly true | 4=doubtful | 5=improbable | 6=cannot judge
  rule: only A1 and B1 drive conclusions; C3 and below need >=B2 corroboration; never publish E/F without explicit confidence qualification
"""
