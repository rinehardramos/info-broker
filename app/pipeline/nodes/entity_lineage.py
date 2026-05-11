"""Entity lineage tracker — finds predecessor entities, name changes, and corporate history.

Works globally with jurisdiction-aware registry targeting. Pure computation; no external calls.
"""

from __future__ import annotations

import logging

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Corporate suffix libraries
# ---------------------------------------------------------------------------

_GLOBAL_SUFFIXES = [
    "Inc.", "Inc", "Corp.", "Corp", "Corporation", "Incorporated",
    "Ltd.", "Ltd", "Limited", "LLC", "L.L.C.", "LLP", "L.L.P.",
    "Holdings", "Holdings Inc.", "Holdings Ltd.", "Holdings Corp.",
    "Group", "Group Inc.", "Group Ltd.", "Group Holdings",
    "International", "International Inc.", "International Ltd.",
    "Enterprises", "Enterprises Inc.", "Enterprises Ltd.",
    "Solutions", "Solutions Inc.", "Solutions Ltd.",
    "Services", "Services Inc.", "Services Ltd.",
    "Trading", "Trading Ltd.", "Trading Inc.",
    "& Co.", "& Associates", "& Partners",
    # European forms
    "GmbH", "AG", "S.A.", "S.L.", "B.V.", "N.V.", "A/S", "ApS",
    "S.p.A.", "S.r.l.", "SARL", "SAS", "SA",
    # Commonwealth
    "Pty Ltd", "Pty. Ltd.", "Pty", "PLC", "plc",
    # PH-specific
    "OPC", "One Person Corporation",
    # SG-specific
    "Pte Ltd", "Pte. Ltd.",
]

_JURISDICTION_SUFFIXES: dict[str, list[str]] = {
    "ph": ["Inc.", "Corp.", "Holdings Inc.", "Holdings Corp.", "OPC", "Enterprises Inc.", "Trading Inc.", "Solutions Inc."],
    "us": ["Inc.", "Corp.", "LLC", "LLP", "Ltd.", "Holdings Inc.", "Holdings LLC"],
    "uk": ["Ltd.", "Limited", "PLC", "plc", "LLP", "Holdings Ltd.", "Group Ltd."],
    "au": ["Pty Ltd", "Pty. Ltd.", "Ltd.", "Limited", "Holdings Pty Ltd"],
    "sg": ["Pte Ltd", "Pte. Ltd.", "Ltd.", "Limited", "Holdings Pte Ltd"],
    "de": ["GmbH", "AG", "KG", "GmbH & Co. KG"],
    "fr": ["SA", "SAS", "SARL", "SCI"],
}

# ---------------------------------------------------------------------------
# Registry search templates per jurisdiction
# ---------------------------------------------------------------------------

_REGISTRY_QUERIES: dict[str, list[str]] = {
    "ph": [
        '"{company}" site:sec.gov.ph OR site:dti.gov.ph',
        '"{company}" "formerly" OR "predecessor" SEC Philippines',
        '"{company}" dissolved revoked cancelled SEC Philippines',
        '"{company}" merger acquisition Philippines SEC',
    ],
    "us": [
        '"{company}" site:sec.gov EDGAR',
        '"{company}" "formerly known as" OR "name change" SEC EDGAR',
        '"{company}" dissolved revoked "secretary of state"',
        '"{company}" merger acquisition "form 8-K" OR "form S-4"',
    ],
    "uk": [
        '"{company}" site:find-and-update.company-information.service.gov.uk',
        '"{company}" "formerly known as" Companies House UK',
        '"{company}" dissolved struck off Companies House',
        '"{company}" merger acquisition Companies House',
    ],
    "au": [
        '"{company}" site:asic.gov.au',
        '"{company}" "formerly known as" ASIC Australia',
        '"{company}" deregistered wound up ASIC',
        '"{company}" merger acquisition Australia ASIC',
    ],
    "sg": [
        '"{company}" site:acra.gov.sg OR site:bizfile.gov.sg',
        '"{company}" "formerly known as" ACRA Singapore',
        '"{company}" struck off wound up Singapore ACRA',
        '"{company}" merger acquisition Singapore',
    ],
}

_DEFAULT_REGISTRY_QUERIES = [
    '"{company}" "formerly known as" OR "previously known as" OR "renamed from"',
    '"{company}" dissolved OR revoked OR "struck off" OR "wound up" company registration',
    '"{company}" merger acquisition takeover corporate restructure',
    '"{company}" predecessor successor "formerly" company history',
]


# ---------------------------------------------------------------------------
# Jurisdiction auto-detection
# ---------------------------------------------------------------------------

def _detect_jurisdiction(company_name: str, domain: str) -> str:
    """Infer jurisdiction from domain TLD or company name cues."""
    if domain:
        tld = domain.rsplit(".", 1)[-1].lower()
        tld_map = {"ph": "ph", "uk": "uk", "co": None, "au": "au", "sg": "sg",
                   "de": "de", "fr": "fr", "nz": "nz", "ca": "ca"}
        if tld in tld_map and tld_map[tld]:
            return tld_map[tld]
        if domain.endswith(".com.ph"):
            return "ph"
        if domain.endswith(".co.uk"):
            return "uk"
        if domain.endswith(".com.au"):
            return "au"
        if domain.endswith(".com.sg"):
            return "sg"

    # Name cue: OPC is PH-specific
    if any(s in company_name for s in ["OPC", "SEC Philippines"]):
        return "ph"
    if "Pty Ltd" in company_name or "Pty." in company_name:
        return "au"
    if "Pte Ltd" in company_name or "Pte." in company_name:
        return "sg"

    return "global"


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def run_entity_lineage(
    company_name: str = "",
    jurisdiction: str = "",
    domain: str = "",
    address: str = "",
    directors: list[str] | None = None,
    years_back: int = 10,
) -> dict:
    """Generate entity lineage investigation queries for any company globally.

    Parameters
    ----------
    company_name:
        Primary company name to investigate.
    jurisdiction:
        Two-letter code or 'global': ph, us, uk, au, sg, de, fr.
        Auto-detected from domain TLD if not provided.
    domain:
        Company website domain — used for Wayback Machine checks.
    address:
        Known registered address — used for address cross-reference.
    directors:
        Known directors/officers — used for cross-reference across companies.
    years_back:
        Years of history to investigate (default 10).

    Returns
    -------
    dict with lineage_search_queries, investigation_notes, wayback_targets, name_variants.
    """
    if directors is None:
        directors = []

    company = company_name.strip()
    if not company:
        return {
            "error": "No company_name provided",
            "lineage_search_queries": [],
            "investigation_notes": [],
        }

    jur = (jurisdiction or _detect_jurisdiction(company, domain)).lower()
    base_name = _strip_corp_suffix(company, jur)
    name_variants = _generate_name_variants(base_name, company, jur)

    queries: list[str] = []

    # --- Universal queries (work regardless of jurisdiction) ---
    for tmpl in _DEFAULT_REGISTRY_QUERIES:
        queries.append(tmpl.format(company=company))

    # --- Jurisdiction-specific registry queries ---
    registry_tmpls = _REGISTRY_QUERIES.get(jur, [])
    for tmpl in registry_tmpls:
        q = tmpl.format(company=company)
        if q not in queries:
            queries.append(q)

    # --- Base name search (stripped of suffix) ---
    if base_name and base_name.lower() != company.lower():
        if jur in ("ph",):
            queries.append(f'"{base_name}" Philippines company registration SEC DTI')
        elif jur == "us":
            queries.append(f'"{base_name}" company registration SEC EDGAR state')
        elif jur == "uk":
            queries.append(f'"{base_name}" Companies House registration UK')
        else:
            queries.append(f'"{base_name}" company registration history')

    # --- Domain history ---
    if domain:
        clean = domain.strip().lstrip("https://").lstrip("http://").rstrip("/")
        queries.append(f'site:{clean} company history "about" "founded"')

    # --- Address cross-reference ---
    if address:
        addr = address.strip()
        queries.append(f'"{addr}" company registration')
        queries.append(f'"{addr}" registered office')

    # --- Director cross-reference ---
    for director in directors[:3]:
        d = director.strip()
        if d:
            if jur == "ph":
                queries.append(f'"{d}" director officer Philippines SEC registration')
                queries.append(f'"{d}" incorporator trustee Philippines SEC EPRS')
            elif jur == "uk":
                queries.append(f'"{d}" director Companies House UK company')
            elif jur == "us":
                queries.append(f'"{d}" director officer SEC EDGAR company registration')
            else:
                queries.append(f'"{d}" director officer company registration')

    # --- Build investigation notes ---
    notes = [
        f"Jurisdiction detected: {jur.upper() if jur != 'global' else 'Global (no specific registry)'}",
        f"Search for predecessor / name-change records: {queries[0]}",
        f"Check dissolution / revocation history: {queries[1]}",
        f"Check merger and acquisition records: {queries[2]}",
    ]

    if jur == "ph":
        notes.append("PH-specific: Use run_ph_sec_dti to get official SEC registration details first.")
        notes.append("Entity hopping is common in PH — check if dissolved entities share directors/address with target.")
    elif jur == "us":
        notes.append("US: Check SEC EDGAR for 8-K filings announcing name changes or mergers.")
        notes.append("US: State-level registrations may differ from SEC — check Delaware/state of incorporation.")
    elif jur == "uk":
        notes.append("UK: Companies House 'filing history' shows all name changes as CH01 filings.")
        notes.append("UK: 'Struck off' companies can be restored — check for restoration applications.")
    elif jur == "au":
        notes.append("AU: ASIC historical extract shows deregistered companies and name changes.")
    elif jur == "sg":
        notes.append("SG: ACRA BizFile shows all company name change history in business profile.")

    if domain:
        notes.append(
            f"Run run_wayback_machine on {domain} to detect historical name, ownership, or "
            "content changes — particularly 'About' pages and footer copy."
        )
    else:
        notes.append(
            "No domain provided — find official website first, then run run_wayback_machine."
        )

    if address:
        notes.append(
            f"Address cross-reference: search for other companies at '{address}' — "
            "shared address is a key shell company / entity hopping indicator."
        )

    if directors:
        notes.append(
            "Director cross-reference: trace all companies each director is or was involved in. "
            "Overlapping directorships across dissolved → active entities is a red flag."
        )

    notes.append(
        "Entity hopping pattern: if a dissolved entity and the target share ≥2 of "
        "{directors, address, phone, trade name} — flag as HIGH RISK predecessor relationship."
    )

    return {
        "company_name": company,
        "jurisdiction": jur,
        "base_name": base_name,
        "name_variants": name_variants,
        "lineage_search_queries": queries,
        "investigation_notes": notes,
        "wayback_targets": [domain.strip()] if domain else [],
        "years_investigated": years_back,
        "source": "entity_lineage",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_corp_suffix(name: str, jurisdiction: str = "global") -> str:
    """Remove corporate suffixes to get the base trade name."""
    n = name.strip()
    suffixes = _JURISDICTION_SUFFIXES.get(jurisdiction, []) + _GLOBAL_SUFFIXES
    suffixes_ordered = sorted(set(suffixes), key=len, reverse=True)
    for suffix in suffixes_ordered:
        if n.lower().endswith(f" {suffix.lower()}") or n.lower().endswith(f",{suffix.lower()}"):
            stripped = n[: len(n) - len(suffix)].strip().rstrip(",").strip()
            if stripped:
                return stripped
    return n


def _generate_name_variants(base_name: str, original: str, jurisdiction: str = "global") -> list[str]:
    """Generate name variants by attaching jurisdiction-appropriate suffixes."""
    if not base_name:
        return [original]

    suffixes = _JURISDICTION_SUFFIXES.get(jurisdiction, ["Inc.", "Ltd.", "Corp.", "LLC", "Holdings Ltd."])
    variants: list[str] = [original]
    seen = {original.lower()}

    for suffix in suffixes:
        candidate = f"{base_name} {suffix}"
        if candidate.lower() not in seen:
            seen.add(candidate.lower())
            variants.append(candidate)

    return variants


# ---------------------------------------------------------------------------
# Pipeline node class
# ---------------------------------------------------------------------------

class EntityLineageNode:
    node_type = "entity_lineage"
    display_name = "Entity Lineage Tracker"
    category = "lookup"

    config_schema = {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
                "title": "Company Name",
                "description": "Primary company name to investigate.",
            },
            "jurisdiction": {
                "type": "string",
                "title": "Jurisdiction",
                "description": "Two-letter code: ph, us, uk, au, sg, de, fr, or leave blank for auto-detect.",
                "default": "",
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
                "description": "Registered address for cross-reference with other entities.",
                "default": "",
            },
            "directors": {
                "type": "array",
                "items": {"type": "string"},
                "title": "Known Directors (optional)",
                "description": "Director/officer names to cross-reference across companies.",
                "default": [],
            },
            "years_back": {
                "type": "integer",
                "title": "Years of History",
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
        jurisdiction = (config.get("jurisdiction") or "").strip()
        domain = (config.get("domain") or "").strip()
        address = (config.get("address") or "").strip()
        directors = config.get("directors") or []
        years_back = config.get("years_back") or 10

        if not company:
            for item in inputs:
                company = (item.get("company_name") or item.get("name") or "").strip()
                domain = domain or (item.get("domain") or "").strip()
                address = address or (item.get("address") or "").strip()
                directors = directors or (item.get("directors") or [])
                if company:
                    break

        result = run_entity_lineage(
            company_name=company,
            jurisdiction=jurisdiction,
            domain=domain,
            address=address,
            directors=directors,
            years_back=years_back,
        )
        return [result]
