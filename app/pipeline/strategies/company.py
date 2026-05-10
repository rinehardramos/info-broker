"""Company investigation strategy module."""

ENTITY_TYPE = "company"

STRATEGY = """
=== COMPANY INVESTIGATION STRATEGY ===

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
