"""Technique → API-key metadata + pre-run missing-key detection (Phase 2, #75).

This is the data + logic behind the pre-run missing-key decision gate. Given a
strategy_id, it enumerates the techniques the strategy will prefer, looks up
which of those require an API key, and checks the encrypted vault
(:func:`app.lib.api_keys.resolve_api_key`) to find which keys are NOT yet
configured for the calling user/org.

Design notes
------------
- Enumeration is *precise*: only techniques reachable via each phase's explicit
  ``preferred_tactic_id`` (plus that tactic's ``required_techniques``) are
  considered. We deliberately do NOT scan every phase-compatible tactic, because
  the leads-enrichment tactic is compatible with the generic ``gather`` phase and
  would otherwise surface enrichment keys for unrelated strategies (e.g.
  generic_search) that will never call those tools.
- Techniques NOT present in :data:`TECHNIQUE_KEY_META` are treated as needing no
  key (e.g. ``web_search``, ``opencorporates_owner``, ``phone_osint`` are free).
- SECURITY: this module only ever handles key *names* and public setup metadata.
  It never returns, logs, or transmits a decrypted key value. The only signal it
  reads from the vault is presence (resolve returns a value vs. None).
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.pipeline.catalogs.loader import load_catalog

log = logging.getLogger(__name__)

_CATALOG_BASE = Path(__file__).resolve().parent / "registries"

# technique_id → public metadata for the key it needs. key_name follows the
# lowercase-snake_case convention the nodes use with resolve_api_key().
TECHNIQUE_KEY_META: dict[str, dict[str, str]] = {
    "hunter_email_search": {
        "key_name": "hunter_io_api_key",
        "display_name": "Hunter.io (email finder)",
        "setup_url": "https://hunter.io/api-keys",
        "setup_instructions": (
            "Create a free Hunter.io account, open Dashboard → API, and copy the "
            "API key. The free tier allows 25 searches/month."
        ),
    },
    "apollo_contact": {
        "key_name": "apollo_api_key",
        "display_name": "Apollo.io (contact enrichment)",
        "setup_url": "https://developer.apollo.io/keys/",
        "setup_instructions": (
            "Sign in to Apollo.io, go to Settings → Integrations → API, and "
            "generate an API key. A free plan is available."
        ),
    },
    "whois_owner": {
        "key_name": "whoisxml_api_key",
        "display_name": "WhoisXML API (domain/owner lookup)",
        "setup_url": "https://whois.whoisxmlapi.com/",
        "setup_instructions": (
            "Register at whoisxmlapi.com and copy your API key from the My "
            "Products / API page. The free tier includes 500 lookups."
        ),
    },
    "pipl_people": {
        "key_name": "pipl_api_key",
        "display_name": "Pipl (people search)",
        "setup_url": "https://pipl.com/api",
        "setup_instructions": (
            "Request a Pipl API key from pipl.com/api (paid product) and paste "
            "the key here."
        ),
    },
    "apify_listings_search": {
        "key_name": "apify_api_token",
        "display_name": "Apify (Zillow / listings scraper)",
        "setup_url": "https://console.apify.com/account/integrations",
        "setup_instructions": (
            "Create an Apify account, open Settings → Integrations, and copy your "
            "Personal API token. The free plan includes monthly usage credits."
        ),
    },
}


def _enumerate_technique_ids(strategy_id: str, *, required_only: bool = False) -> set[str]:
    """Return the technique ids a strategy will prefer.

    Walks each phase's ``preferred_tactic_id``. With ``required_only=True`` it
    returns ONLY that tactic's ``required_techniques`` — used by the pre-run gate
    so a key is surfaced before launch only when it's genuinely required (no free
    path); optional accelerator techniques in ``produces`` are NOT pre-gated (the
    reactive mid-run gate offers those if the brain actually calls one). Returns
    an empty set for unknown strategies.
    """
    try:
        strategies = load_catalog("strategy", _CATALOG_BASE / "strategies")
        tactics = load_catalog("tactic", _CATALOG_BASE / "tactics")
    except Exception:
        log.warning("technique_keys: catalog load failed", exc_info=True)
        return set()

    strat = strategies.get(strategy_id)
    if strat is None:
        return set()

    tech_ids: set[str] = set()
    for phase in strat.phases:
        tactic_id = getattr(phase, "preferred_tactic_id", None)
        if not tactic_id:
            continue
        tactic = tactics.get(tactic_id)
        if tactic is None:
            continue
        required = getattr(tactic, "required_techniques", []) or []
        tech_ids.update(required)
        if not required_only:
            tech_ids.update(task.technique_id for task in tactic.produces)
    return tech_ids


# node_type → the technique whose key metadata applies. Used by the reactive
# mid-run gate (#76), which sees node_type (not technique_id) on the node-execute
# path. Only nodes that actually call resolve_api_key with a real key appear here
# (pipl_people has no node implementation, so it's intentionally absent).
_NODE_TO_TECHNIQUE: dict[str, str] = {
    "hunter_io": "hunter_email_search",
    "apollo_zoominfo": "apollo_contact",
    "whois_lookup": "whois_owner",
    "apify_actor": "apify_listings_search",
}


def node_missing_key(
    node_type: str,
    *,
    user_id: str | None,
    org_id: str | None,
) -> dict[str, str] | None:
    """For the reactive mid-run gate: if *node_type* needs an API key that is NOT
    configured in the vault, return its descriptor
    ``{node_type, key_name, display_name, setup_url, setup_instructions}``; else
    None. Never returns a key value. Fail-open (returns None) on any error so a
    vault hiccup can't break node execution.
    """
    tid = _NODE_TO_TECHNIQUE.get(node_type)
    if tid is None:
        return None
    meta = TECHNIQUE_KEY_META.get(tid)
    if meta is None:
        return None
    from app.lib.api_keys import resolve_api_key

    try:
        if resolve_api_key(meta["key_name"], user_id=user_id, org_id=org_id) is not None:
            return None
    except Exception:
        log.debug("node_missing_key: resolve failed node_type=%r", node_type, exc_info=True)
        return None
    return {"node_type": node_type, **meta}


def check_missing_keys_for_strategy(
    strategy_id: str,
    *,
    user_id: str | None,
    org_id: str | None,
) -> list[dict[str, str]]:
    """Return descriptors for key-requiring techniques whose key is NOT configured.

    Resolution presence is checked via the scoped vault (user→org→global→
    core_settings→env). De-duplicated by ``key_name`` so the same key is only
    surfaced once even if multiple techniques share it. Never returns key values.
    """
    from app.lib.api_keys import resolve_api_key

    # Pre-run gate: only REQUIRED techniques (no free path) are gated. Optional
    # keyed accelerators are surfaced reactively mid-run, not pre-gated — keys
    # must never block a strategy that has a free path (e.g. real_estate_leads
    # requires only web_search).
    technique_ids = _enumerate_technique_ids(strategy_id, required_only=True)
    missing: list[dict[str, str]] = []
    seen_keys: set[str] = set()

    for tid in technique_ids:
        meta = TECHNIQUE_KEY_META.get(tid)
        if meta is None:
            continue  # technique needs no key
        key_name = meta["key_name"]
        if key_name in seen_keys:
            continue
        try:
            present = resolve_api_key(key_name, user_id=user_id, org_id=org_id) is not None
        except Exception:
            # A vault/db hiccup must not strand the run — treat as present
            # (fail-open) so the gate never blocks on infrastructure errors.
            log.debug("technique_keys: resolve failed key_name=%r", key_name, exc_info=True)
            present = True
        if not present:
            seen_keys.add(key_name)
            missing.append(
                {
                    "technique_id": tid,
                    "key_name": key_name,
                    "display_name": meta["display_name"],
                    "setup_url": meta["setup_url"],
                    "setup_instructions": meta["setup_instructions"],
                }
            )
    return missing
