"""Company investigation strategy module."""

ENTITY_TYPE = "company"

STRATEGY = """
=== COMPANY INVESTIGATION STRATEGY ===

--- PIR TEMPLATE ---

PIR: What is this company's legal identity, jurisdiction, ownership, and current operational status?
MANDATORY: Legal entity record in at least one jurisdiction | Active or dissolved status confirmed
SUPPORTING: Ownership chain identified | Key personnel verified | Products/services confirmed
REJECT IF: Entity cannot be found in any jurisdiction after searching primary + alternate registries

--- HYPOTHESIS TABLE ---

H1 (primary jurisdiction): Company is registered in its most obvious jurisdiction
  search: run_opencorporates("[company name]") | run_ph_sec_dti | run_apollo_search

H2 (parent / subsidiary): The named entity is a subsidiary — the real answer is the parent
  search: "[company name] parent company" | "[company name] acquired by" | run_opencorporates(parent search)

H3 (entity lineage — renamed or dissolved): Company dissolved and re-registered under a new name
  search: run_entity_lineage first | "[old name] renamed" | "[old name] successor"
  This is a common PH fraud pattern — always run entity lineage for PH subjects.

H_last (foreign subsidiary / shell): Entity is a holding company or shell in a different jurisdiction
  search: "[company name] offshore" | "[company name] BVI/Cayman/Singapore" | run_opencorporates(intl)

execution_model: seed → anchor(legal_entity) → expand → deduplicate → gap_fill

priority_selectors: domain | employer(name) | ticker_symbol | registration_number

--- KEY PIVOT PATTERNS ---

domain → whois_lookup | shodan_search | hunter_io | multi_search(site:domain)
employer → run_opencorporates | run_ph_sec_dti | apollo_zoominfo | linkedin_navigator
ticker_symbol → run_sec_edgar(10-K/10-Q/proxy) | financial APIs
registration_number → run_opencorporates | run_ph_sec_dti
leadership(from above) → apollo_zoominfo | linkedin_navigator | run_hunter_io

hop_depth: max 1 hop for leadership — company → exec names → basic profile (name/title/email). Full PERSON strategy only if explicitly requested.

--- INVESTIGATION PRINCIPLES ---

LEGAL-ENTITY-FIRST: Anchor on registered legal name before trade/brand names.
MULTI-JURISDICTION: Identify ultimate parent + material subsidiaries across registries.
TECH-STACK: run_shodan_search on primary domain reveals exposed services without active probing.
GLASSDOOR-SIGNAL: Employee reviews surface culture, compensation, and leadership sentiment.

--- COMPLETENESS CHECKLIST ---

Before closing, mark each domain CONFIRMED/PARTIAL/NOT_FOUND/NOT_ATTEMPTED:
identity | digital_presence | leadership_team | financials | market_position | technology_stack
"""
