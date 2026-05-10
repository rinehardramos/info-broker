"""Anchor-and-Pivot meta-strategy module."""

NAME = "anchor_and_pivot"
DISPLAY_NAME = "Anchor & Pivot"
DESCRIPTION = "Identify a high-uniqueness anchor, tier sources by reliability, enforce triangulation before confirming claims."
TRIGGER_SIGNALS = ["investigate", "find", "who is", "profile", "research"]
ENTITY_TYPES = ["all"]
ALWAYS_ON = True

STRATEGY_TEXT = """
=== ANCHOR-AND-PIVOT META-STRATEGY ===

ANCHOR_BEFORE_WIDENING:
  hierarchy: email > phone > username > employer+name > name-alone
  rules:
    - no broad collection until one anchor confirmed
    - every pivot traces to a verified anchor
    - no profile merges without cross-anchor independent verification
    - name-alone = CANDIDATE until corroborated by second anchor attribute
    - anchor = CONFIRMED when >=2 independent sources agree (not same DB mirror)

SOURCE_TIERS: Exhaust higher tiers before descending. Lower-tier claims need higher-tier corroboration to reach CONFIRMED.
  T1: gov databases, corporate registries, court records, licensing boards
  T2: primary documents — filings, contracts, official correspondence
  T3: regulated journalism — established newsrooms, named reporters
  T4: social/self-published — behavioral signal only, not factual
  T5: anonymous/forums — leads only, never evidence without T1-3 corroboration
  promotion: T4/T5 claim elevates only when T1-3 independently confirms same fact

PASSIVE_FIRST (minimum footprint):
  PASSIVE: archives, registries, cached pages, Wayback (zero subject signal)
  SEMI_ACTIVE: live anon queries to public engines (minimal signal)
  ACTIVE_LOW: touches subject infra without auth (SMTP RCPT TO, Shodan; leaves log trace)
  ACTIVE_HIGH: authenticated/interactive contact (burns the option permanently)
  rule: never escalate to ACTIVE_HIGH without explicit operational requirement

TRIANGULATION:
  CONFIRMED = >=2 independent sources agree
  independence test: would both sources have the fact if the other did not exist?
  NOT independent: same press release / registry mirror / wire story
  "consensus" is not triangulation if all sources trace to one originating document
"""
