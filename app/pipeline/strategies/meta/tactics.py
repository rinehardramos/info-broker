"""Universal investigation tactics — reusable decision rules for any strategy."""

NAME = "universal_tactics"
DISPLAY_NAME = "Universal Investigation Tactics"
DESCRIPTION = "Cross-cutting decision rules applicable to any investigation type or strategy."
TRIGGER_SIGNALS = []   # always injected via ALWAYS_ON
ENTITY_TYPES = ["all"]
ALWAYS_ON = True

STRATEGY_TEXT = """
=== UNIVERSAL INVESTIGATION TACTICS ===

STRATEGY_COMPOSITION: Mix strategies freely. Override recommendations when judgment says otherwise. Goal = best answer.

BLOCKED_TOOL:
  action: pivot — identify goal, find alternative
  rule: >=2 failures same category = dead_end; mark "Blocked -> pivoted to [X]"
  pivots:
    employment: apollo/linkedin/webdork
    registry: opencorporates/sec_edgar
    email: enumerator/hunter/reverse
    social: username_enum/messaging/facebook

DEAD_END_ACCELERATION: 3 tool calls with 0 results = dead_end. Max 3 calls per dead branch.

QUERY_REFORMULATION: Before dead_end try >=2 variants: add/remove quotes | boolean AND/OR | synonyms | reverse name order.

COST_AWARE_TOOL_SELECTION: passive first (archives/registries) -> semi-active (live anon queries) -> active (authenticated).

CROSS_LANGUAGE_PIVOT: English returns nothing -> try subject's native language + local engine (Baidu/CN, Naver/KR, Yandex/RU).
  mandatory (do not wait for English failure): Korean/K-pop query -> search Korean immediately.

UNCONVENTIONAL_BRANCH [OSINT/investigation only, not simple lookups]:
  state: "UNCONVENTIONAL ANGLE: [what]. WHY: [reasoning]."
  branch_name: unconventional_[description]
  constraint: do not repeat same angle on consecutive runs
"""
