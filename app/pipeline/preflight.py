"""PreFlight — deterministic requirements validation before IS brain launch.

Three-layer algorithm:
  Layer 1: regex-based extraction (no LLM)
  Layer 2: slot extraction via Haiku (one call, 5s timeout)
  Layer 3: requirements rules → MissingSlot list → ValidationResult
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layer 1 constants
# ---------------------------------------------------------------------------

EVIDENCE_VERBS: set[str] = {
    "saw", "seen", "heard", "watched", "noticed", "found", "spotted",
    "came across", "stumbled upon",
}

PLATFORM_TERMS: set[str] = {
    "youtube", "facebook", "instagram", "tiktok", "netflix", "amazon",
    "prime", "disney", "hbo", "hulu", "apple tv", "peacock", "paramount",
    "ad", "advertisement", "commercial", "streaming", "broadcast",
    "twitter", "x.com",
}

TEMPORAL_TERMS: set[str] = {
    "new", "recent", "recently", "latest", "upcoming", "current",
    "today", "yesterday", "now", "2024", "2025", "2026",
    "this year", "last year", "just", "brand new",
}

REFERENTIAL_PATTERNS: list[str] = [
    r"\b(this|that|the)\s+(ad|advertisement|commercial|show|series|film|movie|video|clip|post|tweet|article|person|guy|girl|woman|man)\b",
    r"\bnew\s+\w+\s+with\b",
    r"\bthe\s+\w+\s+in\b",
]

POLYSEMOUS_TERMS: set[str] = {
    "apple", "amazon", "tesla", "mercury", "mars", "oracle", "java",
    "python", "phoenix", "jaguar", "falcon", "shell", "target", "sprint",
    "palm", "blackberry",
}


# ---------------------------------------------------------------------------
# Layer 1 dataclass + extract()
# ---------------------------------------------------------------------------

@dataclass
class ExtractionResult:
    proper_nouns: list[str] = field(default_factory=list)
    time_expressions: list[str] = field(default_factory=list)
    platform_hints: list[str] = field(default_factory=list)
    first_person_evidence: bool = False
    referential_phrases: list[str] = field(default_factory=list)
    polysemous_term: bool = False
    temporal_signal: bool = False


def extract(query: str) -> ExtractionResult:
    """Layer 1: deterministic regex extraction — no LLM."""
    q_lower = query.lower()
    words = re.findall(r"\b\w+\b", q_lower)
    word_set = set(words)

    # Proper nouns: capitalized words (not at sentence start heuristic — just title-case)
    proper_nouns = re.findall(r"\b[A-Z][a-z]{1,}\b", query)

    # Time expressions
    time_expressions: list[str] = []
    for term in TEMPORAL_TERMS:
        if term in q_lower:
            time_expressions.append(term)

    # Platform hints
    platform_hints: list[str] = []
    for term in PLATFORM_TERMS:
        if term in q_lower:
            platform_hints.append(term)

    # First-person evidence: multi-word phrases first, then single words
    first_person_evidence = False
    for verb in EVIDENCE_VERBS:
        if verb in q_lower:
            first_person_evidence = True
            break

    # Referential phrases
    referential_phrases: list[str] = []
    for pattern in REFERENTIAL_PATTERNS:
        matches = re.findall(pattern, q_lower)
        if matches:
            referential_phrases.extend(
                [m if isinstance(m, str) else " ".join(m) for m in matches]
            )

    # Polysemous term
    polysemous_term = bool(word_set & POLYSEMOUS_TERMS)

    # Temporal signal
    temporal_signal = bool(time_expressions)

    return ExtractionResult(
        proper_nouns=proper_nouns,
        time_expressions=time_expressions,
        platform_hints=platform_hints,
        first_person_evidence=first_person_evidence,
        referential_phrases=referential_phrases,
        polysemous_term=polysemous_term,
        temporal_signal=temporal_signal,
    )


# ---------------------------------------------------------------------------
# Layer 2 dataclass + extract_slots()
# ---------------------------------------------------------------------------

@dataclass
class SlotResult:
    subject_kind: str = "unknown"           # "named" | "described" | "referential" | "unknown"
    subject_value: str | None = None
    subject_confidence: float = 0.0
    subject_ambiguity: str = "low"          # "low" | "medium" | "high"
    provenance_present: bool = False
    provenance_value: str | None = None
    provenance_confidence: float = 0.0
    scope_time: str | None = None
    scope_geo: str | None = None
    scope_platform: str | None = None
    goal_shape: str | None = None           # "identify" | "verify" | "find" | "compare" | "monitor" | "explain"
    goal_confidence: float = 0.0
    has_disambiguator: bool = False
    disambiguator_value: str | None = None
    raw_interpretation: str = "User is trying to research an unspecified topic"
    # Internal: False when Haiku call failed — gates LLM-dependent rules
    _haiku_succeeded: bool = False


_SLOT_PROMPT = """\
You are a slot-filling classifier. Extract structured information from the user query below.
Do NOT answer the query. Do NOT do research. Only fill slots.

These signals were detected in the query (regex layer):
{extraction_hints}

User query: {query}

Return ONLY valid JSON with these exact fields:
{{
  "subject_kind": "named" | "described" | "referential" | "unknown",
  "subject_value": string or null,
  "subject_confidence": 0.0-1.0,
  "subject_ambiguity": "low" | "medium" | "high",
  "provenance_present": true | false,
  "provenance_value": string or null,
  "provenance_confidence": 0.0-1.0,
  "scope_time": string or null,
  "scope_geo": string or null,
  "scope_platform": string or null,
  "goal_shape": "identify" | "verify" | "find" | "compare" | "monitor" | "explain" | null,
  "goal_confidence": 0.0-1.0,
  "has_disambiguator": true | false,
  "disambiguator_value": string or null,
  "raw_interpretation": "User is trying to [X] about [Y]"
}}

Rules:
- Leave string fields null if confidence < 0.7
- subject_kind "named" = explicit name given; "described" = described but not named; "referential" = "this ad", "that show" etc; "unknown" = unclear
- provenance_present = true only if the query mentions WHERE the user encountered the subject (platform, medium, context)
- has_disambiguator = true if query has enough detail to narrow down the subject unambiguously
"""


def _extraction_hints(extraction: ExtractionResult) -> str:
    parts = []
    if extraction.proper_nouns:
        parts.append(f"proper_nouns={extraction.proper_nouns}")
    if extraction.time_expressions:
        parts.append(f"time_expressions={extraction.time_expressions}")
    if extraction.platform_hints:
        parts.append(f"platform_hints={extraction.platform_hints}")
    if extraction.first_person_evidence:
        parts.append("first_person_evidence=True")
    if extraction.referential_phrases:
        parts.append(f"referential_phrases={extraction.referential_phrases}")
    if extraction.polysemous_term:
        parts.append("polysemous_term=True")
    return ", ".join(parts) if parts else "(none detected)"


def _get_gemini_key() -> str:
    """Load Gemini API key from env or core_settings DB."""
    key = os.getenv("GEMINI_API_KEY", "")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one("SELECT value FROM core_settings WHERE key = 'gemini_api_key'", ())
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return ""


def extract_slots(query: str, extraction: ExtractionResult) -> SlotResult:
    """Layer 2: one fast LLM call to fill slots. Uses Gemini Flash if available, else Anthropic. Non-fatal."""
    default = SlotResult()
    prompt = _SLOT_PROMPT.format(
        extraction_hints=_extraction_hints(extraction),
        query=query,
    )

    # Try Gemini via llm_providers (project's primary LLM provider)
    gemini_key = _get_gemini_key()
    if gemini_key:
        try:
            from openai import OpenAI as _OpenAI
            client = _OpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=gemini_key,
            )
            resp = client.chat.completions.create(
                model="gemini-2.5-flash",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = (resp.choices[0].message.content or "").strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            data = json.loads(raw)
            return SlotResult(
                subject_kind=data.get("subject_kind", "unknown"),
                subject_value=data.get("subject_value"),
                subject_confidence=float(data.get("subject_confidence", 0.0)),
                subject_ambiguity=data.get("subject_ambiguity", "low"),
                provenance_present=bool(data.get("provenance_present", False)),
                provenance_value=data.get("provenance_value"),
                provenance_confidence=float(data.get("provenance_confidence", 0.0)),
                scope_time=data.get("scope_time"),
                scope_geo=data.get("scope_geo"),
                scope_platform=data.get("scope_platform"),
                goal_shape=data.get("goal_shape"),
                goal_confidence=float(data.get("goal_confidence", 0.0)),
                has_disambiguator=bool(data.get("has_disambiguator", False)),
                disambiguator_value=data.get("disambiguator_value"),
                raw_interpretation=data.get("raw_interpretation", "User is trying to research an unspecified topic"),
                _haiku_succeeded=True,
            )
        except Exception as exc:
            log.warning("PreFlight Gemini slot extraction failed (non-fatal): %s", exc)

    # Fallback: Anthropic Haiku
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key, timeout=5.0)
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            data = json.loads(raw)
            return SlotResult(
                subject_kind=data.get("subject_kind", "unknown"),
                subject_value=data.get("subject_value"),
                subject_confidence=float(data.get("subject_confidence", 0.0)),
                subject_ambiguity=data.get("subject_ambiguity", "low"),
                provenance_present=bool(data.get("provenance_present", False)),
                provenance_value=data.get("provenance_value"),
                provenance_confidence=float(data.get("provenance_confidence", 0.0)),
                scope_time=data.get("scope_time"),
                scope_geo=data.get("scope_geo"),
                scope_platform=data.get("scope_platform"),
                goal_shape=data.get("goal_shape"),
                goal_confidence=float(data.get("goal_confidence", 0.0)),
                has_disambiguator=bool(data.get("has_disambiguator", False)),
                disambiguator_value=data.get("disambiguator_value"),
                raw_interpretation=data.get("raw_interpretation", "User is trying to research an unspecified topic"),
                _haiku_succeeded=True,
            )
        except Exception as exc:
            log.warning("PreFlight Anthropic slot extraction failed (non-fatal): %s", exc)

    log.warning("PreFlight: no LLM available for slot extraction, using Layer-1-only mode")
    return default


# ---------------------------------------------------------------------------
# Layer 3 — MissingSlot + check_requirements()
# ---------------------------------------------------------------------------

@dataclass
class MissingSlot:
    slot: str
    priority: int
    question: str
    options: list[str] = field(default_factory=list)


def check_requirements(
    query: str,
    extraction: ExtractionResult,
    slots: SlotResult,
    prior_slots: "SlotResult | None" = None,
) -> list[MissingSlot]:
    """Layer 3: evaluate rules and return any MissingSlot entries.

    Args:
        prior_slots: Slots resolved in a previous turn of the same session.
            Any slot already filled there will not trigger a repeat question.
    """
    missing: list[MissingSlot] = []

    # Rule 1 (priority 1): first-person evidence or referential phrase but no provenance.
    # Specific platform names from Layer 1 are a sufficient provenance signal even without Haiku.
    # Generic medium terms like "ad", "commercial" don't tell us WHERE — only named platforms do.
    _NAMED_PLATFORMS = {
        "youtube", "facebook", "instagram", "tiktok", "netflix", "amazon",
        "prime", "disney", "hbo", "hulu", "apple tv", "peacock", "paramount",
        "twitter", "x.com",
    }
    _layer1_platform_provenance = bool(
        set(extraction.platform_hints) & _NAMED_PLATFORMS
    )
    _has_provenance = slots.provenance_present or _layer1_platform_provenance
    # Skip Rule 1 if provenance was already established in a prior turn.
    _prior_provenance = prior_slots is not None and prior_slots.provenance_present
    if (extraction.first_person_evidence or extraction.referential_phrases) and not _has_provenance and not _prior_provenance:
        missing.append(MissingSlot(
            slot="provenance",
            priority=1,
            question="Where did you see or hear this?",
            options=[
                "YouTube",
                "Facebook/Instagram/TikTok",
                "Netflix/Amazon/streaming",
                "TV broadcast",
                "Cinema",
                "Other",
            ],
        ))

    # Rules 2, 3, 4, 6 depend on Haiku slot output — skip when Haiku was unavailable
    if slots._haiku_succeeded:
        # Skip Rules 2 & 3 if a disambiguator was already provided in a prior turn.
        _prior_disambiguator = prior_slots is not None and prior_slots.has_disambiguator

        # Rule 2 (priority 2): described subject with no disambiguator, goal is identify or unknown
        if (
            slots.subject_kind == "described"
            and not slots.has_disambiguator
            and not _prior_disambiguator
            and slots.goal_shape in ("identify", None)
        ):
            missing.append(MissingSlot(
                slot="disambiguator",
                priority=2,
                question="Can you give any other identifying details?",
                options=[
                    "I know the brand or product",
                    "I know which show or film",
                    "I only have the description",
                    "Skip",
                ],
            ))

        # Rule 3 (priority 2): polysemous term with medium/high ambiguity, no disambiguator
        if (
            extraction.polysemous_term
            and slots.subject_ambiguity in ("medium", "high")
            and not slots.has_disambiguator
            and not _prior_disambiguator
        ):
            subject_label = slots.subject_value or "this"
            missing.append(MissingSlot(
                slot="polysemous_disambig",
                priority=2,
                question=f"Which '{subject_label}' do you mean?",
                options=["The company/brand", "The product", "The person", "Other"],
            ))

        # Rule 4 (priority 3): goal unknown or low-confidence.
        # Skip if goal was established in a prior turn.
        _prior_goal = prior_slots is not None and prior_slots.goal_shape is not None
        if not _prior_goal and (slots.goal_shape is None or slots.goal_confidence < 0.6):
            subject_label = slots.subject_value or "this"
            missing.append(MissingSlot(
                slot="goal",
                priority=3,
                question=f"What do you need to know about {subject_label}?",
                options=[
                    "Identify what/who it is",
                    "Find more information",
                    "Verify a claim",
                    "Compare with alternatives",
                ],
            ))

    # Rule 5 (priority 3): temporal signal but scope_time not resolved (Haiku-dependent).
    # Skip if scope_time was already established in a prior turn.
    _prior_scope_time = prior_slots is not None and prior_slots.scope_time is not None
    if slots._haiku_succeeded and extraction.temporal_signal and slots.scope_time is None and not _prior_scope_time:
        missing.append(MissingSlot(
            slot="scope_time",
            priority=3,
            question="Is this about something current or recent?",
            options=[
                "Very recent (2025–2026)",
                "A few years ago (2020–2024)",
                "Historical",
                "Not sure",
            ],
        ))

    # Rule 6 (priority 2): compare goal but no comparison target in query (Haiku-dependent)
    if slots._haiku_succeeded and (
        slots.goal_shape == "compare"
        and slots.subject_kind == "named"
        and slots.subject_value
        and "vs" not in query.lower()
        and " and " not in query.lower()
    ):
        missing.append(MissingSlot(
            slot="comparison_target",
            priority=2,
            question="What would you like to compare this with?",
            options=[
                "A specific competitor",
                "Industry average",
                "A previous version",
                "Other",
            ],
        ))

    return missing


# ---------------------------------------------------------------------------
# ValidationResult + validate()
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    tier: int                               # 1, 2, or 3
    blocking: bool                          # True for tier 2
    missing: list[MissingSlot]
    first_question: str | None
    first_question_options: list[str] | None
    slots: SlotResult
    extraction: ExtractionResult
    confidence: float                       # 0-1 overall completeness
    disclaimer: str | None


def _compute_confidence(slots: SlotResult, missing: list[MissingSlot]) -> float:
    """Heuristic: start at slots.subject_confidence, penalise for each missing slot.

    When Haiku was unavailable, use 0.7 as a neutral base so Layer-1-only
    passes still reach Tier 1 (spec: "treat as Tier 1" when Haiku fails).
    """
    if not slots._haiku_succeeded:
        base = 0.7
    else:
        base = slots.subject_confidence if slots.subject_confidence > 0 else 0.5
    # Priority-1 gaps are heavier
    penalty = sum(0.3 if m.priority == 1 else 0.15 for m in missing)
    return max(0.0, min(1.0, base - penalty))


def validate(query: str, prior_slots: SlotResult | None = None) -> ValidationResult:
    """Run all three PreFlight layers and return a ValidationResult.

    Args:
        prior_slots: Slot result from a previous turn in the same session.
            Already-filled slots will not trigger repeat clarification questions.
    """
    extraction = extract(query)
    slots = extract_slots(query, extraction)
    missing = check_requirements(query, extraction, slots, prior_slots=prior_slots)
    missing.sort(key=lambda m: m.priority)

    confidence = _compute_confidence(slots, missing)

    if missing:
        tier = 2
        blocking = True
        disclaimer = None
    elif confidence < 0.6:
        tier = 3
        blocking = False
        disclaimer = (
            f"I interpreted this as: {slots.raw_interpretation}. "
            f"If that's not right, please clarify."
        )
    else:
        tier = 1
        blocking = False
        disclaimer = None

    return ValidationResult(
        tier=tier,
        blocking=blocking,
        missing=missing,
        first_question=missing[0].question if missing else None,
        first_question_options=missing[0].options if missing else None,
        slots=slots,
        extraction=extraction,
        confidence=confidence,
        disclaimer=disclaimer,
    )
