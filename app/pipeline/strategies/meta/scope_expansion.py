"""Scope Expansion meta-strategy module."""

NAME = "scope_expansion"
DISPLAY_NAME = "Scope Expansion"
DESCRIPTION = "Net-widening, geographic corridor expansion, and negative-space analysis for stalled investigations."
TRIGGER_SIGNALS = [
    "not found", "no results", "low confidence", "common name", "diaspora",
    "migration", "overseas", "expat", "abroad", "widen", "expand",
]
ENTITY_TYPES = ["all"]
ALWAYS_ON = False

STRATEGY_TEXT = """
=== SCOPE EXPANSION META-STRATEGY ===

ACTIVATION: 3 tool calls with 0 results, OR confidence < 0.5 after 3 locale-specific calls.

NET_WIDENING:
  >=0.75 confidence -> stay, deepen current locale
  0.45-0.75 -> parallel widen top-2 corridor destinations
  0.20-0.45 -> aggressive widen top-5 corridors + re-evaluate name-origin assumption
  <0.20 -> RESET — wrong assumption; pivot on non-name attributes (DOB/phone/email/photo)

BREADTH_FIRST_SURVEY:
  phase_1: shallow pass all source classes (max 30% budget any single source); record yield per source
  phase_2: rank by yield, allocate deep-collection budget to top-K; do not skip phase_1 for early hits

GEOGRAPHIC_WIDENING (person):
  step_0: re-evaluate name origin (romanization artifacts):
    Tan=Hokkien/PH/SG | Chan=Cantonese/HK | Chen=Mandarin/CN | Tran/Nguyen=VN | Khan=PK/IN/AF/BD
  step_1 corridors (run_migration_corridor_lookup):
    PH->US/UAE/SA/CA/AU/SG | IN->UAE/SA/US/UK/CA | VN->US/JP/AU/KR/DE | CN->US/HK/SG/CA | PK->SA/UAE/UK | NG->US/UK/CA
  step_2: parallel shallow sweep top-3 locales: local social | LinkedIn dork with city | local registry | local-language variant
  step_3 diaspora sources: h1bdata.info | thegazette.co.uk (UK naturalization) | DMW/POEA (PH overseas) | ICIJ Offshore Leaks | researchgate/orcid/academia.edu
  step_4 digital shadow: phone prefix vs country mismatch | messaging platform (Viber=PH, Zalo=VN, WeChat=CN diaspora, Telegram=IR/RU/UA) | posting timezone
  anchor_pivot: IF confidence >=0.6 -> drop widening, deep-dive that country
  stop: anchor >=0.85 with 2 independent corroborations | 3 consecutive rounds yield nothing | budget cap

NEGATIVE_SPACE_ANALYSIS:
  maintain "expected artifact" list; flag each absence explicitly (absence = finding, not failure)
  common name (top-1000 Forebears.io) + zero hits across all expected locale sources -> migration probability >=0.7 -> trigger geographic widening
"""
