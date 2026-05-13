# app/pipeline/strategies/orchestrator.py
"""Research query orchestrator — classifies queries into research categories."""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)

# Category signal words, checked in priority order.
# NOTE: specific entity-type signals come before generic "person" signals so
# that queries like "Due diligence on Acme Corp" resolve to "due_diligence",
# not "person".  "profile " is kept before generation signals so that
# "Build a complete profile of Jane Smith" still resolves to "person".
_CATEGORY_SIGNALS: list[tuple[str, list[str]]] = [
    # --- Media identification (checked before all other categories) ---
    ("media_identification", [
        "what show ", "what movie ", "what series ", "which show ", "which movie ",
        "identify this show", "identify this movie", "what am i watching",
        "new series with", "new series on", "new series ", "new show with", "new show on",
        "girl in ", "guy in ", "man in ",
        "actress from", "actor from", "who plays",
        "what is this series", "what is this show", "what is this movie",
    ]),
    # --- Place / route / navigation (checked before generic person) ---
    ("place", [
        "route to ", "route from ", "directions to ", "directions from ",
        "how to get to ", "how to get from ", "how do i get to ",
        "walking from ", "walking to ", "walk from ", "walk to ",
        "shortcut from ", "shortcut to ", "fastest way to ", "fastest way from ",
        "commute from ", "commute to ", "on foot from ", "by foot ",
        "path from ", "path to ", "navigate to ", "navigate from ",
        "how far is ", "distance from ", "paano makarating ", "papunta sa ",
        "tawid ", "eskinita ", "bliss hulo", "bliss mandaluyong",
    ]),
    # --- Specific Retrieval variants (checked before generic person) ---
    ("due_diligence", ["due diligence", "kyc", "aml", "compliance check", "background check",
                       "risk assessment", "sanctions", "pep screen", "know your customer"]),
    ("company",       ["company profile", "competitor", "market analysis", "business registry",
                       "company investigation", "corporate profile", "company lookup"]),
    ("researcher",    ["papers", "publications", "academic", "citations", "scholar",
                       "research papers", "journal articles", "google scholar"]),
    ("lead",          ["find leads", "lead generation", "prospect list", "contact list",
                       "outreach", "sales leads", "prospecting", "build a prospect"]),
    # --- Specific knowledge-category variants (checked before broad categories) ---
    ("root_cause_analysis",  ["root cause", "5 whys", "fishbone", "incident analysis"]),
    ("systems_analysis",     ["feedback loop", "system dynamics", "leverage point"]),
    ("systematic_review",    ["systematic review", "meta-analysis", "literature review", "prisma"]),
    ("strategic_assessment", ["swot", "five forces", "pestle", "strategic analysis"]),
    ("decision_analysis",    ["decision matrix", "which option", "trade-off analysis", "choose between"]),
    ("product_innovation",   ["new product", "product design", "user needs"]),
    ("scientific_discovery", ["hypothesis", "experiment", "discover", "scientific"]),
    ("engineering_rd",       ["trl", "prototype", "readiness level", "engineering design"]),
    ("technology_forecast",  ["technology radar", "tech trend", "emerging tech"]),
    ("market_forecast",      ["market size", "tam", "market growth", "demand forecast"]),
    # --- Generic person / knowledge signals ---
    ("person", ["profile "]),
    ("generation", ["build a ", "create a ", "design a ", "invent ", "develop a ", "make a new ", "implement a "]),
    ("explanation", ["why ", "root cause", "diagnose", "how does", "explain why", "what caused", "debug"]),
    ("prediction", ["predict", "forecast", "trend", "future of", "what will", "where is .* going", "outlook"]),
    ("synthesis", ["review ", "summarize ", "compare ", "evaluate ", "assess ", "analyze the evidence", "state of "]),
    ("person", ["investigate", "find ", "background check", "who is", "look up", "research "]),
]


def classify_query(query: str) -> str:
    """Classify a research query into a category.

    Returns one of: "person", "generation", "explanation", "prediction", "synthesis".
    Defaults to "person" (Retrieval) for ambiguous queries.
    """
    if not query:
        return "person"

    q = query.lower().strip()

    for category, signals in _CATEGORY_SIGNALS:
        for signal in signals:
            if signal in q:
                return category

    return "person"  # Default: Retrieval


# ---------------------------------------------------------------------------
# Complexity scoring signals — (score_delta, list[signal_substrings])
# ---------------------------------------------------------------------------
_COMPLEXITY_SIGNALS: list[tuple[int, list[str]]] = [
    (-2, ["email of", "phone of", "address of"]),
    (-1, ["what is", "look up", "who is"]),  # "find " removed — "find X with description" is NOT simple
    (+2, ["vs", "versus", "compare "]),
    (+2, ["investigate", "analyze", "research ", "root cause"]),
    (+3, ["and also", " and "]),
    (+1, ["why ", "because"]),
    (+1, ["predict", "forecast", "what will"]),
    # Appearance-description queries are always complex (must identify brand → ambassador → person)
    (+4, ["mole", "tattoo", "hair color", "eye shape", "cheekbone", "cheek bone", "skin tone",
          "with curly", "with straight", "with long hair", "with short hair"]),
    # Entertainment/celebrity identification without a name = complex multi-step reasoning
    (+3, ["commercial", "advertisement", "in the ad", "in the commercial", "in the video",
          "kpop", "k-pop", "idol", "actress", "actor in", "singer in", "model in"]),
    # Non-English cultural context signals complexity
    (+2, ["korean", "japanese", "chinese", "thai", "filipino", "vietnamese", "bollywood",
          "telenovela", "anime", "hallyu", "kdrama"]),
]


def classify_complexity(query: str) -> tuple[str, int]:
    """Score *query* for research complexity and return a (tier, score) pair.

    Scoring rules
    -------------
    - Single entity markers ("email of", "phone of", "address of")  -2 each
    - Simple lookup verbs ("what is", "find ", "look up", "who is") -1 each
    - Multi-entity/comparison ("vs", "versus", "compare ")          +2 each
    - Open-ended verbs ("investigate", "analyze", "research ")      +2 each
    - Multi-domain conjunctions ("and also", " and ")               +3 each
    - Causal ("why ", "root cause", "because")                      +1 each
    - Predictive ("predict", "forecast", "what will")               +1 each
    - Long query (> 50 words)                                        +1

    Returns ``("simple", score)`` when score <= 0, ``("complex", score)`` otherwise.
    """
    if not query:
        return ("simple", 0)

    q = query.lower().strip()
    score = 0

    for delta, signals in _COMPLEXITY_SIGNALS:
        for signal in signals:
            if signal in q:
                score += delta

    if len(q.split()) > 50:
        score += 1

    tier = "simple" if score <= 0 else "complex"
    return (tier, score)


# ---------------------------------------------------------------------------
# Cross-category transition protocol
# ---------------------------------------------------------------------------

# Compound query patterns: keywords that indicate multi-category intent
_COMPOUND_PATTERNS: list[tuple[str, list[str]]] = [
    # "Build/Create X" with research context → Synthesis/Retrieval + Generation
    (r"(?:build|create|design|develop)\s+.*(?:cure|solution|system|tool|product)",
     ["synthesis", "generation"]),
    # "Why X and how to fix" → Explanation + Generation
    (r"why\s+.*(?:and|then)\s+(?:how|fix|solve|improve)",
     ["explanation", "generation"]),
    # "State of X and where going" → Synthesis + Prediction
    (r"(?:state of|status of|current)\s+.*(?:where|future|going|next|trend)",
     ["synthesis", "prediction"]),
    # "Should we X" → Retrieval + Synthesis
    (r"should\s+we\s+.*(?:acquire|invest|buy|choose|adopt)",
     ["person", "synthesis"]),
    # "Analyze X and recommend" → Synthesis + Generation
    (r"(?:analyze|assess)\s+.*(?:recommend|suggest|propose)",
     ["synthesis", "generation"]),
]

# Selector type transformation map: (from_category, to_category) → type mappings
_SELECTOR_TRANSFORMS: dict[tuple[str, str], dict[str, str]] = {
    # Retrieval → Generation: findings become prior art
    ("person", "generation"): {"finding": "prior_art", "entity": "constraint"},
    ("company", "generation"): {"finding": "prior_art", "entity": "constraint"},
    ("lead", "generation"): {"finding": "prior_art"},
    # Retrieval → Synthesis: findings become evidence
    ("person", "synthesis"): {"finding": "evidence", "entity": "study"},
    ("company", "synthesis"): {"finding": "evidence"},
    # Synthesis → Generation: gaps become problems
    ("synthesis", "generation"): {"finding": "prior_art", "gap": "problem_statement", "claim": "constraint"},
    # Explanation → Generation: causes become constraints
    ("explanation", "generation"): {"root_cause": "constraint", "finding": "prior_art", "cause": "constraint"},
    ("root_cause_analysis", "generation"): {"root_cause": "constraint", "finding": "prior_art"},
    # Generation → Explanation: solutions become hypotheses
    ("generation", "explanation"): {"candidate_solution": "hypothesis", "finding": "evidence"},
    ("product_innovation", "explanation"): {"candidate_solution": "hypothesis"},
    # Prediction → Generation: forecasts become constraints
    ("prediction", "generation"): {"forecast": "constraint", "trend": "constraint", "finding": "prior_art"},
}


def _get_broad_category(specific: str) -> str:
    """Map a specific strategy to its broad category."""
    _MAP = {
        "person": "person", "lead": "person", "researcher": "person",
        "company": "person", "due_diligence": "person",
        "generation": "generation", "product_innovation": "generation",
        "scientific_discovery": "generation", "engineering_rd": "generation",
        "prediction": "prediction", "technology_forecast": "prediction",
        "market_forecast": "prediction",
        "explanation": "explanation", "root_cause_analysis": "explanation",
        "systems_analysis": "explanation",
        "synthesis": "synthesis", "systematic_review": "synthesis",
        "strategic_assessment": "synthesis", "decision_analysis": "synthesis",
    }
    return _MAP.get(specific, specific)


def classify_query_sequence(query: str) -> list[str]:
    """Classify a query into a sequence of categories for compound research tasks.

    Returns a list of category keys. Single-category queries return a 1-element list.
    Compound queries return 2+ categories in execution order.
    """
    import re

    q = query.lower().strip()

    # Check compound patterns first
    for pattern, categories in _COMPOUND_PATTERNS:
        if re.search(pattern, q, re.IGNORECASE):
            # Resolve each category hint to what classify_query would return for
            # a representative query, keeping the hint as-is when it already is
            # a valid broad category key.
            resolved = []
            for cat_hint in categories:
                if cat_hint in ("synthesis", "generation", "explanation", "prediction", "person"):
                    resolved.append(cat_hint)
                else:
                    resolved.append(classify_query(cat_hint))
            return resolved

    # Fall back to single category
    return [classify_query(query)]


def transform_selectors(
    findings: list[dict],
    from_category: str,
    to_category: str,
) -> list[dict]:
    """Transform selector types when transitioning between research categories.

    Maps finding types from the source category to appropriate types in the
    target category. E.g., a "finding" from Retrieval becomes "prior_art" in Generation.
    """
    if from_category == to_category:
        return findings  # No transformation needed

    # Look up exact transformation map first
    transform_map = _SELECTOR_TRANSFORMS.get((from_category, to_category), {})

    # Fall back to broad-category mapping when no exact match exists
    if not transform_map:
        broad_from = _get_broad_category(from_category)
        broad_to = _get_broad_category(to_category)
        if broad_from != broad_to:
            transform_map = _SELECTOR_TRANSFORMS.get((broad_from, broad_to), {})

    if not transform_map:
        # Default: safe pass-through with "finding" → "prior_art"
        transform_map = {"finding": "prior_art"}

    results = []
    for f in findings:
        original_type = f.get("type", "finding")
        new_type = transform_map.get(original_type, original_type)
        results.append({**f, "type": new_type})

    return results


# ---------------------------------------------------------------------------
# LLM-based sub-strategy classifier
# ---------------------------------------------------------------------------

async def _classify_substrategy_llm(prompt: str) -> str:
    """Call the LLM to select a sub-strategy name.

    Uses Claude Code CLI as primary, Anthropic API as fallback, general_model.
    Returns the raw LLM response text, or empty string on failure.
    """
    import os
    import shutil

    from app.llm_models import general_model

    model = general_model()

    # Primary: Claude Code CLI
    claude_bin = shutil.which("claude") or "/usr/local/bin/claude"
    if os.path.isfile(claude_bin):
        try:
            spawn_env = {**os.environ, "CLAUDE_CODE_HEADLESS": "1"}
            fresh_key = ""
            try:
                from app.routers.v3.db import fetch_one as _fetch
                _row = _fetch("SELECT value FROM core_settings WHERE key = 'anthropic_api_key'", ())
                if _row and _row["value"] and _row["value"].startswith("sk-ant-api"):
                    fresh_key = _row["value"]
            except Exception:
                pass
            if not fresh_key:
                env_key = os.getenv("ANTHROPIC_API_KEY", "")
                if env_key.startswith("sk-ant-api"):
                    fresh_key = env_key
            if fresh_key:
                spawn_env["ANTHROPIC_API_KEY"] = fresh_key
            else:
                spawn_env.pop("ANTHROPIC_API_KEY", None)

            cmd_args = [claude_bin, "--output-format", "text", "--model", model, "--max-turns", "1"]
            if fresh_key:
                cmd_args.append("--bare")
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                env=spawn_env,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode()), timeout=60
            )
            if proc.returncode == 0 and stdout:
                return stdout.decode().strip()
            log.warning("SubstrategyClassifier: Claude Code exit %s, falling back to API", proc.returncode)
        except asyncio.TimeoutError:
            log.warning("SubstrategyClassifier: Claude Code timed out, falling back to API")
        except Exception as exc:
            log.warning("SubstrategyClassifier: Claude Code failed (%s), falling back to API", exc)

    # Fallback: Anthropic API SDK
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        try:
            from app.routers.v3.db import fetch_one
            row = fetch_one("SELECT value FROM core_settings WHERE key = 'anthropic_api_key'", ())
            if row:
                api_key = row["value"]
        except Exception:
            pass

    if not api_key:
        log.warning("SubstrategyClassifier: no Claude Code and no API key, returning empty")
        return ""

    loop = asyncio.get_running_loop()
    client = anthropic.Anthropic(api_key=api_key, max_retries=0)
    fallback_model = general_model()
    for current_model in [model, fallback_model]:
        try:
            response = await loop.run_in_executor(
                None,
                lambda m=current_model: client.messages.create(
                    model=m,
                    max_tokens=64,
                    messages=[{"role": "user", "content": prompt}],
                ),
            )
            return response.content[0].text
        except Exception as exc:
            log.warning("SubstrategyClassifier: API model %s failed: %s", current_model, exc)

    return ""


async def classify_substrategy(category: str, query: str) -> str:
    """Select the most specific sub-strategy for *query* within *category*.

    Loads available sub-strategies from the domain registry, builds a prompt,
    calls the LLM, validates the response, and returns the sub-strategy name.
    Returns "none" when no sub-strategies exist, query is empty, the LLM fails,
    or the LLM returns an unrecognised name.

    Args:
        category: Research category key (e.g. "retrieval", "explanation").
        query:    The research query string.

    Returns:
        A sub-strategy name from the registry, or "none".
    """
    from app.pipeline.strategies.domains.registry import list_substrategies

    if not query:
        return "none"

    substrategies = list_substrategies(category)
    if not substrategies:
        return "none"

    valid_names = {s["name"] for s in substrategies}

    # Build the sub-strategy lines for the prompt
    lines = [f'- {s["name"]}: {s["description"]}' for s in substrategies]
    lines.append("- none: Use the base category strategy (no domain specialization needed)")
    substrategy_block = "\n".join(lines)

    prompt = (
        "Select the most specific research sub-strategy for this query.\n"
        "\n"
        f"Category: {category}\n"
        f"Query: {query}\n"
        "\n"
        "Available sub-strategies:\n"
        f"{substrategy_block}\n"
        "\n"
        'Return ONLY the sub-strategy name (e.g., "due_diligence" or "none"). No explanation.'
    )

    try:
        raw = await _classify_substrategy_llm(prompt)
    except Exception as exc:
        log.warning("classify_substrategy: LLM call failed (%s), returning 'none'", exc)
        return "none"

    # Extract the first token / word that looks like a snake_case name
    import re
    match = re.search(r"\b([a-z][a-z0-9_]*)\b", raw.strip().lower())
    if not match:
        return "none"

    candidate = match.group(1)
    if candidate == "none":
        return "none"
    if candidate in valid_names:
        return candidate

    log.debug("classify_substrategy: LLM returned unknown name %r, returning 'none'", candidate)
    return "none"
