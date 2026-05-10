"""Meta-strategy compiler — selects and injects relevant generic investigation strategies.

Strategies are entity-agnostic and complement the entity-specific strategies.
The compiler selects always-on strategies plus query-triggered ones,
capping the total injected text to avoid prompt bloat.
"""

from __future__ import annotations

import importlib
import logging
import pathlib
import re

log = logging.getLogger(__name__)

_META_DIR = pathlib.Path(__file__).parent

# Load all strategy modules lazily
_modules: dict | None = None


def _load_modules() -> dict:
    global _modules
    if _modules is not None:
        return _modules
    _modules = {}
    for py_file in sorted(_META_DIR.glob("*.py")):
        if py_file.name in ("__init__.py", "compiler.py"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"meta.{py_file.stem}", py_file)
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            if hasattr(mod, "NAME") and hasattr(mod, "STRATEGY_TEXT"):
                _modules[mod.NAME] = mod
        except Exception:
            pass
    return _modules


_FINANCIAL_SIGNALS = {
    "money", "financial", "contract", "payment", "fund", "invest", "asset",
    "revenue", "salary", "ownership", "corrupt", "fraud", "sanction",
    "beneficial owner", "shell", "offshore", "wire transfer", "laundering",
    "procurement", "budget", "invoice", "transaction", "bribe", "kickback",
}

_NETWORK_SIGNALS = {
    "network", "ring", "scheme", "conspiracy", "associates", "connections",
    "organization", "syndicate", "cartel", "group", "board", "directors",
    "related parties", "shell companies", "coordination", "nexus",
    "co-conspirator", "accomplice", "partner", "affiliate",
}

_TEMPORAL_SIGNALS = {
    "when", "timeline", "history", "sequence", "before", "after", "date",
    "chronology", "event", "incident", "change", "version", "scrubbed",
    "deleted", "edited", "modified", "archived", "wayback", "historical",
}

_HYPOTHESIS_SIGNALS = {
    "is it true", "verify", "confirm", "disprove", "evidence", "claim",
    "allegation", "accurate", "real", "fake", "legitimate", "authentic",
    "validate", "check", "true or false", "alleged", "unconfirmed",
}

_VERIFICATION_SIGNALS = {
    "fake", "authentic", "real", "disinformation", "propaganda", "manipulated",
    "geolocation", "photo", "video", "image", "media", "coordinated",
    "bot", "inauthentic", "influence operation", "sock puppet", "astroturf",
    "deepfake", "misattributed", "misleading",
}

_SCOPE_SIGNALS = {
    "not found", "no results", "low confidence", "common name", "diaspora",
    "migration", "overseas", "expat", "abroad", "widen", "expand",
    "emigrant", "immigrant", "ofw", "foreign worker", "international",
}

_BI_SIGNALS = {
    "company", "competitor", "market", "industry", "revenue", "growth",
    "strategy", "product", "funding", "startup", "enterprise", "b2b",
    "saas", "technology stack", "hiring", "job posting", "valuation",
    "market share", "competitive", "acquisition", "ipo",
}

_PLATFORM_SIGNALS = {
    "social media", "facebook", "instagram", "twitter", "tiktok", "linkedin",
    "reddit", "telegram", "influencer", "online presence", "digital footprint",
    "platform", "audience", "followers", "community", "viral", "bot",
    "content", "post", "profile", "account",
}

_SIGNAL_MAP = {
    "financial_trail": _FINANCIAL_SIGNALS,
    "network_analysis": _NETWORK_SIGNALS,
    "temporal_analysis": _TEMPORAL_SIGNALS,
    "hypothesis_testing": _HYPOTHESIS_SIGNALS,
    "osint_verification": _VERIFICATION_SIGNALS,
    "scope_expansion": _SCOPE_SIGNALS,
    "business_intelligence": _BI_SIGNALS,
    "platform_social_intel": _PLATFORM_SIGNALS,
}

# Max strategies to inject (besides always-on) to keep prompt size reasonable
_MAX_TRIGGERED = 3


def _query_matches(query_lower: str, signals: set[str]) -> bool:
    return any(sig in query_lower for sig in signals)


def build_meta_strategies_section(
    query: str,
    entity_type: str = "",
    confidence: float = 1.0,
) -> str:
    """Select and format relevant meta-strategies.

    Primary: RAG retrieval from Qdrant (top-K relevant rules, ~1500 tokens).
    Fallback: static selection (always-on + signal-triggered, all text).

    Args:
        query: The research query.
        entity_type: Classified entity type (person, company, etc.).
        confidence: Current investigation confidence (0–1); low triggers scope_expansion.
    """
    # Try RAG retrieval first
    try:
        from app.pipeline.strategies.meta.rule_store import retrieve_rules
        rag_result = retrieve_rules(query, entity_type, max_tokens=1500)
        if rag_result and len(rag_result) > 50:  # Non-trivial result
            return rag_result
    except Exception as exc:
        log.debug("RAG rule retrieval failed, using static fallback: %s", exc)

    # Fallback: existing static logic (unchanged)
    modules = _load_modules()
    if not modules:
        return ""

    q = query.lower()
    selected: list[str] = []

    # 1. Always-on strategies first
    for name, mod in modules.items():
        if getattr(mod, "ALWAYS_ON", False):
            selected.append(name)

    # 2. Low-confidence → always trigger scope_expansion for person investigations
    if confidence < 0.5 and entity_type in ("person", ""):
        if "scope_expansion" not in selected and "scope_expansion" in modules:
            selected.append("scope_expansion")

    # 3. Query-triggered strategies
    triggered: list[tuple[int, str]] = []
    for name, signals in _SIGNAL_MAP.items():
        if name in selected:
            continue
        mod = modules.get(name)
        if not mod:
            continue
        # Count matching signals (for ranking)
        hits = sum(1 for sig in signals if sig in q)
        if hits > 0:
            triggered.append((-hits, name))  # negative for sort asc

    triggered.sort()
    for _, name in triggered[:_MAX_TRIGGERED]:
        selected.append(name)

    # 4. Entity-type hints
    if entity_type == "person" and "scope_expansion" not in selected and "scope_expansion" in modules:
        # Person investigations always benefit from knowing the widening protocol
        if len(selected) - sum(1 for n in selected if getattr(modules.get(n), "ALWAYS_ON", False)) < _MAX_TRIGGERED:
            selected.append("scope_expansion")

    # Ensure tactics always comes first
    if "universal_tactics" in selected:
        selected.remove("universal_tactics")
        selected.insert(0, "universal_tactics")

    if not selected:
        return ""

    parts: list[str] = ["## INVESTIGATION META-STRATEGIES\n"]
    parts.append("Apply these cross-domain strategies throughout the investigation:\n")

    for name in selected:
        mod = modules.get(name)
        if not mod:
            continue
        text = getattr(mod, "STRATEGY_TEXT", "").strip()
        if text:
            parts.append(text)
            parts.append("")  # blank line between strategies

    return "\n".join(parts)
