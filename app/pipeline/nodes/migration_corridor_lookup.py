"""Migration corridor lookup node — returns top destination countries for a given origin country by migrant stock."""

from __future__ import annotations

import logging

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Migration corridors reveal where diaspora communities settle — essential for"
    " geographic widening when a locale search is low-yield in person investigations"
)

# IOM Migration Data Portal — bilateral migrant stock endpoint
_IOM_API_URL = "https://gmdac.iom.int/api/data/migrant-stock"

# Hardcoded top corridors by origin country (fallback when API unavailable).
# Format: { "ISO2": [("DEST_ISO2", rank_weight, "search_tip"), ...] }
_CORRIDOR_FALLBACK: dict[str, list[tuple[str, int, str]]] = {
    "PH": [
        ("SA", 2500000, "Search PHL OFW records, OEC on DMW website"),
        ("AE", 700000, "Search UAE GDRFA records, Zawya profiles"),
        ("US", 4100000, "Search h1bdata.info, PACER, USAJobs for Filipino names"),
        ("QA", 400000, "Search Qatar MOI portal"),
        ("KW", 250000, "Search expat forums, OFW Facebook groups"),
        ("MY", 700000, "Search MyCoID, SSM registry"),
        ("SG", 200000, "Search ACRA, LinkedInSG"),
        ("IT", 280000, "Search AIRE registry, Italian comuni"),
        ("CA", 900000, "Search IRCC records, LinkedIn Canada"),
        ("AU", 400000, "Search ABN lookup, ASIC, LinkedIn Australia"),
    ],
    "IN": [
        ("US", 4500000, "Search h1bdata.info, PACER, LinkedIn US"),
        ("AE", 3400000, "Search UAE GDRFA, Zawya"),
        ("PK", 1600000, "Historical partition — check NADRA adjacent records"),
        ("SA", 2600000, "Search Saudi Iqama records"),
        ("GB", 1900000, "Search Companies House, Gazette, UKVI"),
        ("CA", 1600000, "Search IRCC, LinkedIn Canada"),
        ("AU", 800000, "Search ABN, ASIC"),
        ("MY", 1500000, "Search SSM, MyCoID"),
        ("KW", 900000, "Search Kuwait MOI"),
        ("QA", 650000, "Search Qatar MOI"),
    ],
    "CN": [
        ("US", 5000000, "Search h1bdata.info, PACER, LinkedIn US"),
        ("CA", 1700000, "Search IRCC, LinkedIn Canada"),
        ("AU", 1400000, "Search ABN, ASIC"),
        ("SG", 1200000, "Search ACRA"),
        ("MY", 2000000, "Search SSM, MyCoID"),
        ("GB", 700000, "Search Companies House"),
        ("JP", 800000, "Search Japan MOJ, Touki registry"),
        ("KR", 1000000, "Search Korean court records"),
        ("DE", 250000, "Search Bundesanzeiger, Handelsregister"),
        ("IT", 320000, "Search CCIAA, PEC registry"),
    ],
    "MX": [
        ("US", 11500000, "Search h1bdata.info, PACER, LinkedIn US"),
        ("CA", 100000, "Search IRCC"),
        ("ES", 500000, "Search BOE, Registro Civil"),
        ("DE", 100000, "Search Handelsregister"),
        ("GB", 50000, "Search Companies House"),
        ("FR", 80000, "Search BODACC"),
        ("AU", 30000, "Search ABN"),
        ("AR", 200000, "Search AFIP, IGJ"),
        ("BR", 50000, "Search Receita Federal, Junta Comercial"),
        ("CO", 70000, "Search CCB, RUES"),
    ],
    "NG": [
        ("US", 400000, "Search h1bdata.info, PACER"),
        ("GB", 230000, "Search Companies House, Gazette"),
        ("CA", 100000, "Search IRCC"),
        ("GH", 800000, "Search Ghana Registrar General"),
        ("ZA", 70000, "Search CIPC"),
        ("IT", 80000, "Search CCIAA"),
        ("DE", 50000, "Search Handelsregister"),
        ("AE", 60000, "Search UAE GDRFA, Zawya"),
        ("FR", 70000, "Search BODACC"),
        ("AU", 50000, "Search ABN, ASIC"),
    ],
}

# Destination-specific investigation tips
_DEST_TIPS: dict[str, str] = {
    "US": "h1bdata.info for visa petitions; PACER for court records; USCIS FOIA for immigration",
    "GB": "Companies House; London Gazette; UKVI; ACAS tribunal decisions",
    "CA": "IRCC Express Entry; provincial corporate registries; LinkedIn Canada",
    "AU": "ABN Lookup; ASIC; LinkedIn Australia; state land title registries",
    "SG": "ACRA Bizfile; CorpPass; LinkedIn Singapore",
    "AE": "UAE GDRFA; Zawya company search; DED Dubai",
    "SA": "MHRSD Saudi; Zawya; SASO",
    "QA": "Qatar MOI; QFC entity search",
    "KW": "Kuwait MOI; KDIPA",
    "MY": "SSM MyCoID; LinkedIn Malaysia",
    "DE": "Handelsregister; Bundesanzeiger; XING",
    "FR": "BODACC; Infogreffe; Societe.com",
    "IT": "CCIAA Registro Imprese; PEC; AIRE for Italian diaspora",
    "ES": "BOE; BORME; Registro Civil",
    "JP": "Japan MOJ; Touki registry; LinkedIn Japan",
    "KR": "Korean Supreme Court registry; LinkedIn Korea",
    "PH": "SEC CHED; DTI; PRC license lookup",
}


class MigrationCorridorLookupNode:
    node_type = "migration_corridor_lookup"
    display_name = "Migration Corridor Lookup"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "origin_country": {
                "type": "string",
                "title": "Origin Country",
                "description": "ISO-2 country code (e.g. PH, IN, CN) or country name.",
            },
            "max_destinations": {
                "type": "integer",
                "title": "Max Destinations",
                "default": 10,
                "minimum": 1,
                "maximum": 20,
                "description": "Maximum number of destination countries to return.",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        max_destinations = int(config.get("max_destinations", 10))

        # Collect origin countries from config and inputs
        origins: list[str] = []
        if config.get("origin_country"):
            origins.append(config["origin_country"].strip().upper())

        for item in inputs:
            country = (
                item.get("origin_country")
                or item.get("likely_origin")
                or item.get("country")
                or ""
            ).strip().upper()
            if country and country not in origins:
                origins.append(country)

        if not origins:
            log.warning("migration_corridor_lookup: no origin country provided")
            return [
                {
                    "error": "No origin_country provided",
                    "source": "migration_corridor_lookup",
                    "reason": _REASON,
                }
            ]

        results: list[dict] = []
        for origin in origins:
            result = await _lookup_corridors(origin, max_destinations)
            results.append(result)

        return results


async def _lookup_corridors(origin: str, max_destinations: int) -> dict:
    """Try IOM API first, fall back to hardcoded corridor table."""
    # Normalize country name to ISO-2 if needed (simple length check)
    iso2 = origin if len(origin) == 2 else _country_name_to_iso2(origin)

    # Attempt IOM Migration Data Portal
    iom_result = await _fetch_iom_api(iso2, max_destinations)
    if iom_result and not iom_result.get("error"):
        return iom_result

    # Fall back to hardcoded table
    return _fetch_fallback(iso2, max_destinations)


async def _fetch_iom_api(iso2: str, max_destinations: int) -> dict | None:
    """Query IOM Migration Data Portal for migrant stock corridors."""
    try:
        params = {
            "originCountry": iso2,
            "type": "stock",
            "limit": max_destinations,
            "sort": "value",
            "order": "desc",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                _IOM_API_URL,
                params=params,
                headers={"user-agent": "info-broker/1.0"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
    except Exception as exc:
        log.debug("migration_corridor_lookup: IOM API error for %r: %s", iso2, exc)
        return None

    rows = data.get("data") or data.get("results") or []
    destinations: list[dict] = []
    for row in rows[:max_destinations]:
        dest_iso2 = (row.get("destinationCountry") or row.get("dest_iso2") or "").upper()
        value = row.get("value") or row.get("migrantStock") or 0
        destinations.append(
            {
                "destination": dest_iso2,
                "migrant_stock": value,
                "search_tips": _DEST_TIPS.get(dest_iso2, f"Search corporate/civil registries in {dest_iso2}"),
            }
        )

    return {
        "origin_country": iso2,
        "top_destinations": destinations,
        "source": "iom_api",
        "reason": _REASON,
    }


def _fetch_fallback(iso2: str, max_destinations: int) -> dict:
    """Return hardcoded migration corridor data for the given origin ISO-2."""
    corridors = _CORRIDOR_FALLBACK.get(iso2, [])

    if not corridors:
        # Generic fallback — return a note and common global hubs
        destinations = [
            {
                "destination": dest,
                "migrant_stock": None,
                "search_tips": _DEST_TIPS.get(dest, f"Search corporate/civil registries in {dest}"),
            }
            for dest in ["US", "GB", "CA", "AU", "DE", "AE", "SG", "FR", "IT", "ES"][:max_destinations]
        ]
        return {
            "origin_country": iso2,
            "top_destinations": destinations,
            "source": "fallback_generic",
            "note": f"No specific corridor data for {iso2!r}. Returning global diaspora hubs.",
            "reason": _REASON,
        }

    destinations = [
        {
            "destination": dest_iso2,
            "migrant_stock": stock,
            "search_tips": _DEST_TIPS.get(dest_iso2, tip) if tip else _DEST_TIPS.get(dest_iso2, f"Search registries in {dest_iso2}"),
        }
        for dest_iso2, stock, tip in corridors[:max_destinations]
    ]

    return {
        "origin_country": iso2,
        "top_destinations": destinations,
        "source": "fallback_hardcoded",
        "reason": _REASON,
    }


def _country_name_to_iso2(name: str) -> str:
    """Best-effort map common country names to ISO-2 codes."""
    mapping = {
        "PHILIPPINES": "PH",
        "INDIA": "IN",
        "CHINA": "CN",
        "MEXICO": "MX",
        "NIGERIA": "NG",
        "UNITED STATES": "US",
        "USA": "US",
        "UNITED KINGDOM": "GB",
        "UK": "GB",
        "CANADA": "CA",
        "AUSTRALIA": "AU",
        "SINGAPORE": "SG",
        "GERMANY": "DE",
        "FRANCE": "FR",
        "ITALY": "IT",
        "SPAIN": "ES",
        "JAPAN": "JP",
        "SOUTH KOREA": "KR",
        "KOREA": "KR",
        "MALAYSIA": "MY",
        "BRAZIL": "BR",
        "INDONESIA": "ID",
        "VIETNAM": "VN",
        "PAKISTAN": "PK",
        "BANGLADESH": "BD",
        "GHANA": "GH",
        "SOUTH AFRICA": "ZA",
        "UNITED ARAB EMIRATES": "AE",
        "UAE": "AE",
        "SAUDI ARABIA": "SA",
        "QATAR": "QA",
        "KUWAIT": "KW",
    }
    return mapping.get(name.upper(), name[:2].upper())
