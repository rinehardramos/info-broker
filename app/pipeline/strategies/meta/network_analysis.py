"""Network Analysis meta-strategy module."""

NAME = "network_analysis"
DISPLAY_NAME = "Network Analysis"
DESCRIPTION = "Relationship graph mapping, SNA, RICO-style associate expansion, MO pattern matching, link analysis."
TRIGGER_SIGNALS = [
    "network", "ring", "scheme", "conspiracy", "associates", "connections",
    "organization", "syndicate", "cartel", "group", "board", "directors",
    "related parties", "shell companies", "coordination",
]
ENTITY_TYPES = ["all"]
ALWAYS_ON = False

STRATEGY_TEXT = """
=== NETWORK ANALYSIS META-STRATEGY ===

ENTITY_GRAPH_MAPPING: Recommended — map relationship graph before deep-profiling individuals.
  Individual significance = structural position (hub/broker/isolate/peripheral).
  1. enumerate first-degree connections: co-officers, co-defendants, shared-address registrations, family, co-signatories
  2. assign structural roles: Hub=high degree | Broker=bridges clusters | Isolate=cutout | Peripheral=nominees/fronts
  3. profile highest-centrality nodes in depth first

KNOWN_ASSOCIATES_EXPANSION: For each confirmed associate, run same base investigation as primary.
  re-rank after each round: priority = exposure_level x leverage_value x (1 / opsec_strength)
  weakest node (lowest opsec) = highest-yield pivot; networks break at weakest member

MO_PATTERN_MATCHING: Build behavior fingerprint before searching for actors.
  fingerprint: timing pattern | method | target selection | communication channel | payment method
  MO match to known actor = stronger evidence than name match without behavioral corroboration

LINK_ANALYSIS_SEQUENCE:
  1. assemble entities, attributes, events
  2. abstract relationships (who/what/whom/when)
  3. build association matrix (relationship strength per entity pair)
  4. develop link diagram; identify clusters and bridges
  5. layer corporate entities onto person graph
  6. prune low-confidence edges, strengthen high-confidence ones
  tools: run_multi_search("{A}" "{B}" association) | run_opencorporates (shared directors/addresses) | run_apollo_search (org chart) | run_shodan_search (infrastructure overlap)

INTERLOCKING_DIRECTORSHIPS: Shared board seats = ownership/coordination bridge.
  queries: run_multi_search("{person} director board site:companieshouse.gov.uk OR site:opencorporates.com") | run_sec_edgar (proxy filings) | run_opencorporates -> extract officers -> cross-reference
  flag: >=3 directorships per individual | >=2 shared directors between entities (coordination signal)
"""
