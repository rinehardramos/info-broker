"""Financial Trail meta-strategy module."""

NAME = "financial_trail"
DISPLAY_NAME = "Financial Trail"
DESCRIPTION = (
    "Follow-the-money methodology drawn from IRE, ICIJ, and IRS CI. Maps money "
    "flows, beneficial ownership chains, document inventories, and procurement "
    "records to surface financial relationships and gaps."
)
TRIGGER_SIGNALS = [
    "money", "financial", "contract", "payment", "fund", "invest", "asset",
    "revenue", "salary", "ownership", "corrupt", "fraud", "sanction",
    "beneficial owner", "shell", "offshore",
]
ENTITY_TYPES = ["all"]
ALWAYS_ON = False

STRATEGY_TEXT = """
=== FINANCIAL TRAIL META-STRATEGY ===

Activate whenever a monetary anchor appears in the query or collected data.
Generate the money-flow hypothesis tree BEFORE biographical work on any subject.

--- FOLLOW THE MONEY (origin: Watergate / ICIJ) ---

Money has two endpoints and leaves records at every transit point.
Sequence:
  1. Identify any monetary anchor: transaction, asset, salary, contract, donation.
  2. Walk UPSTREAM to source — who paid? From what account? Via what vehicle?
  3. Walk DOWNSTREAM to ultimate beneficial owner — who actually controls the
     asset or receives the value?
  4. Enumerate all intermediaries (shells, trusts, nominees) — they are signal,
     not noise. Each intermediary is a pivot point for a new corporate walk.

Cross-jurisdiction rule: follow the corporate registry chain across borders.
Jurisdictional complexity is intentional — enumerate it; do not stop at it.

--- FOLLOW THE DOCUMENT (origin: IRE methodology) ---

Every regulated activity generates a mandatory document. Build a "document
inventory map" — list which document classes SHOULD exist if the claim is true —
then retrieve each.

Document class inventory:
  corporate filings, court dockets, property / title records, licenses, permits,
  procurement records, lobbying disclosures, FOIA records, regulatory filings,
  professional registries, immigration records, vessel / aircraft registries,
  UCC filings, lien records, tax liens, probate records.

Tools: run_sec_edgar, run_opencorporates, run_ph_sec_dti, run_ph_bir,
run_web_crawl on national registries.

Absence of an expected document is a finding. Flag it explicitly.

--- BENEFICIAL OWNERSHIP WALK ---

Walk this chain for every entity in scope:
  Company → directors → shareholders → parent entities → UBO (Ultimate
  Beneficial Owner).

Sources by jurisdiction:
  - run_opencorporates — global corporate registry aggregator
  - UK Companies House — full DOB + nationality of directors, fully public
  - ICIJ Offshore Leaks — offshoreleaks.icij.org (Panama Papers, Pandora Papers,
    FinCEN Files, Offshore Leaks database)
  - run_sec_edgar — US public company officer lists and beneficial ownership
    disclosures (Schedule 13D/G, DEF 14A proxy)

Cross-check every entity name and individual in the chain against OpenSanctions
and run_pep_sanctions_screen. A single sanctioned node taints the chain.

--- FINANCIAL GAP ANALYSIS (IRS CI Net Worth Method, generalized) ---

Compute: declared income vs. observed spend vs. implied lifestyle.
  - Declared income sources: salary filings, public compensation disclosures,
    business revenues from filings.
  - Observed spend signals: property purchases, vehicle registrations, travel
    patterns, lifestyle indicators from social media, luxury brand associations.
  - Unexplained gap = investigation priority. Quantify the gap; assign a
    confidence band; flag as HIGH if gap exceeds 2x declared income.

--- PUBLIC PROCUREMENT INTELLIGENCE ---

Contract awards reveal financial relationships, deal sizes, and strategic
dependencies. Query:
  - run_multi_search("site:usaspending.gov {entity}")
  - run_multi_search("site:ted.europa.eu {entity}")
  - Country-specific portals: PhilGEPS (PH), Contracts Finder (UK),
    SAM.gov (US), DGMARKET (global development).

Analysis targets: award frequency, sole-source vs. competitive bids, contract
value clustering, related-party award patterns (shared directors / addresses
between awardee and contracting officer's known associates).
"""
