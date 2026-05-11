"""PH entity lineage tracker — finds predecessor entities, name changes, and corporate history.

Pure computation; no external API calls.
"""

from __future__ import annotations

import logging

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Philippine companies frequently restructure via dissolution and re-registration under a new name "
    "(entity hopping) to evade creditors, regulatory sanctions, or adverse records. "
    "Tracing predecessor entities, name changes, director cross-references, and shared addresses "
    "is a mandatory first step for any PH company investigation."
)

# Common PH corporate suffixes used in name variant generation
_PH_CORP_SUFFIXES = [
    "Inc.", "Corp.", "Corporation", "Incorporated",
    "Holdings", "Holdings Inc.", "Holdings Corp.",
    "OPC", "One Person Corporation",
    "Enterprises", "Enterprises Inc.",
    "Trading", "Trading Inc.",
    "Solutions", "Solutions Inc.",
    "International", "International Inc.",
    "Group", "Group Inc.",
    "& Co.", "& Associates",
]


def run_ph_entity_lineage(
    company_name: str = "",
    domain: str = "",
    address: str = "",
    directors: list[str] | None = None,
    years_back: int = 10,
) -> dict:
    """Generate PH corporate lineage investigation queries.

    Parameters
    ----------
    company_name:
        The primary company name to investigate.
    domain:
        Website domain (optional) — used for Wayback Machine checks.
    address:
        Known registered address (optional) — used for address cross-reference.
    directors:
        Known directors or officers (optional) — used for director cross-reference.
    years_back:
        Number of years of history to investigate (default 10).

    Returns
    -------
    dict with keys:
        - ``company_name``: normalized input company name
        - ``lineage_search_queries``: list of search query strings
        - ``investigation_notes``: ordered list of investigation guidance strings
        - ``wayback_targets``: list of domains to check in Wayback Machine
        - ``years_investigated``: years_back value
        - ``name_variants``: list of name variant strings (suffix permutations)
        - ``source``: node identifier
        - ``reason``: explanation of why this node is important
    """
    if directors is None:
        directors = []

    company = company_name.strip()
    if not company:
        return {
            "company_name": "",
            "lineage_search_queries": [],
            "investigation_notes": [],
            "wayback_targets": [],
            "years_investigated": years_back,
            "name_variants": [],
            "error": "No company_name provided",
            "source": "ph_entity_lineage",
            "reason": _REASON,
        }

    queries: list[str] = []

    # --- 1. Name-change / predecessor searches ---
    queries.append(
        f'"{company}" "formerly known as" OR "previously known as" OR "renamed from"'
        f' site:sec.gov.ph OR site:dti.gov.ph'
    )
    queries.append(
        f'"{company}" merger acquisition consolidation Philippines SEC'
    )
    queries.append(
        f'"{company}" "formerly" OR "predecessor" OR "successor" SEC registration Philippines'
    )

    # --- 2. Dissolution / revocation checks ---
    queries.append(
        f'"{company}" dissolved OR revoked OR cancelled OR suspended SEC Philippines'
    )

    # --- 3. Name variant permutations (strip suffix, try alternatives) ---
    base_name = _strip_corp_suffix(company)
    name_variants = _generate_name_variants(base_name, company)

    if base_name and base_name.lower() != company.lower():
        queries.append(
            f'"{base_name}" Philippines SEC registration company'
        )

    # --- 4. Corporate structure ---
    queries.append(f'"{company}" subsidiary parent company Philippines')
    queries.append(f'"{company}" affiliated companies Philippines holding structure')

    # --- 5. Domain history (if provided) ---
    if domain:
        clean_domain = domain.strip().lstrip("https://").lstrip("http://").rstrip("/")
        queries.append(f'site:{clean_domain} company history about')

    # --- 6. Address cross-search (if provided) ---
    if address:
        queries.append(
            f'"{address.strip()}" company registration Philippines SEC DTI'
        )
        queries.append(
            f'"{address.strip()}" registered office Philippines'
        )

    # --- 7. Director cross-search (limit to 3) ---
    for director in directors[:3]:
        d = director.strip()
        if d:
            queries.append(
                f'"{d}" director officer Philippines company SEC registration'
            )
            queries.append(
                f'"{d}" incorporator trustee Philippines SEC EPRS'
            )

    # --- Build investigation notes ---
    notes: list[str] = [
        f"Search for predecessor / name-change records: {queries[0]}",
        f"Check SEC merger and acquisition records: {queries[1]}",
        f"Check dissolution / revocation history: {queries[3]}",
    ]

    if domain:
        notes.append(
            f"Run run_wayback_machine on {domain} to detect historical name changes "
            "or ownership pivots visible in site headers, About pages, or footer copy."
        )
    else:
        notes.append(
            "No domain provided — search the web for the company's official website, "
            "then run run_wayback_machine to check historical content."
        )

    if address:
        addr_query_idx = 6 if domain else 5
        notes.append(
            f"Address cross-reference — check for other companies at same registered address: "
            f"{queries[addr_query_idx]}"
        )
    else:
        notes.append(
            "No address provided — retrieve registered address from SEC filing first "
            "(run run_ph_sec_dti), then re-run address cross-reference."
        )

    if directors:
        notes.append(
            f"Director cross-reference — search for other companies involving: "
            + ", ".join(directors[:3])
            + ". Use SEC EPRS (https://eprs.sec.gov.ph) for authoritative director-company links."
        )
    else:
        notes.append(
            "No directors provided — extract from SEC filing (run run_ph_sec_dti), "
            "then re-run director cross-reference queries."
        )

    notes.append(
        "Entity hopping pattern: if a dissolved entity and the target share directors, "
        "address, or phone — flag as HIGH RISK shell/successor relationship."
    )

    return {
        "company_name": company,
        "lineage_search_queries": queries,
        "investigation_notes": notes,
        "wayback_targets": [domain.strip()] if domain else [],
        "years_investigated": years_back,
        "name_variants": name_variants,
        "source": "ph_entity_lineage",
        "reason": _REASON,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_corp_suffix(name: str) -> str:
    """Remove common PH corporate suffixes to get the base trade name."""
    n = name.strip()
    suffixes_ordered = sorted(_PH_CORP_SUFFIXES, key=len, reverse=True)
    for suffix in suffixes_ordered:
        if n.lower().endswith(suffix.lower()):
            stripped = n[: len(n) - len(suffix)].strip().rstrip(",").strip()
            if stripped:
                return stripped
    return n


def _generate_name_variants(base_name: str, original: str) -> list[str]:
    """Generate name variant strings by attaching PH corporate suffixes to base_name."""
    if not base_name:
        return [original]

    primary_suffixes = [
        "Inc.", "Corp.", "Holdings Inc.", "Holdings Corp.",
        "OPC", "Enterprises Inc.", "Trading Inc.", "Solutions Inc.",
    ]
    variants: list[str] = [original]
    seen = {original.lower()}

    for suffix in primary_suffixes:
        candidate = f"{base_name} {suffix}"
        if candidate.lower() not in seen:
            seen.add(candidate.lower())
            variants.append(candidate)

    return variants


# ---------------------------------------------------------------------------
# Node class (pipeline integration)
# ---------------------------------------------------------------------------

class PhEntityLineageNode:
    node_type = "ph_entity_lineage"
    display_name = "PH Entity Lineage Tracker"
    category = "lookup"

    config_schema = {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
                "title": "Company Name",
                "description": "Primary company name to investigate for corporate lineage.",
            },
            "domain": {
                "type": "string",
                "title": "Website Domain (optional)",
                "description": "Company website domain for Wayback Machine history checks.",
                "default": "",
            },
            "address": {
                "type": "string",
                "title": "Known Address (optional)",
                "description": "Registered address to cross-reference with other entities.",
                "default": "",
            },
            "directors": {
                "type": "array",
                "items": {"type": "string"},
                "title": "Known Directors (optional)",
                "description": "Director/officer names to cross-reference across other PH companies.",
                "default": [],
            },
            "years_back": {
                "type": "integer",
                "title": "Years of History to Check",
                "description": "How many years of corporate history to investigate.",
                "default": 10,
            },
        },
        "required": ["company_name"],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        company = (config.get("company_name") or "").strip()
        domain = (config.get("domain") or "").strip()
        address = (config.get("address") or "").strip()
        directors = config.get("directors") or []
        years_back = config.get("years_back") or 10

        # Fall back to pipeline inputs if config is empty
        if not company:
            for item in inputs:
                company = (
                    item.get("company_name") or item.get("name") or ""
                ).strip()
                domain = domain or (item.get("domain") or "").strip()
                address = address or (item.get("address") or "").strip()
                directors = directors or (item.get("directors") or [])
                if company:
                    break

        result = run_ph_entity_lineage(
            company_name=company,
            domain=domain,
            address=address,
            directors=directors,
            years_back=years_back,
        )
        return [result]


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    result = run_ph_entity_lineage(
        company_name="Apex Holdings Inc.",
        domain="apexholdings.com.ph",
        address="123 Ayala Ave, Makati City",
        directors=["Juan Cruz", "Maria Santos"],
    )
    print(json.dumps(result, indent=2))
