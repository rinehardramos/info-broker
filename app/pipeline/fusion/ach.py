"""Analysis of Competing Hypotheses (ACH) — CIA technique for resolving conflicting findings."""

from __future__ import annotations
import re
from dataclasses import dataclass, field


@dataclass
class ACHResult:
    winner: str
    confidence: str  # "high", "moderate", "low"
    matrix: list[dict]
    diagnostic_evidence: list[int]  # indices of evidence that differentiate hypotheses
    explanation: str = ""


def detect_conflicts(findings: list[dict]) -> list[dict]:
    """Detect contradictions in findings that warrant ACH analysis.

    Looks for findings that mention different values for the same dimension
    (e.g., different employers, different roles, different locations) from
    different sources.

    Returns list of conflict dicts: {"dimension", "hypotheses": [str], "evidence": [dict]}
    """
    claims: list[dict] = []
    for f in findings:
        content = f.get("content", "")  # keep original case for regex capital-letter anchors
        source = f.get("source", "unknown")

        companies = _extract_companies(content)
        for company in companies:
            # Normalise to lowercase for comparison
            claims.append({"dimension": "employer", "value": company.lower(), "source": source, "finding": f})

    conflicts = []
    dimension_groups: dict[str, list[dict]] = {}
    for claim in claims:
        dimension_groups.setdefault(claim["dimension"], []).append(claim)

    for dimension, group in dimension_groups.items():
        value_sources: dict[str, set[str]] = {}
        value_findings: dict[str, list[dict]] = {}
        for claim in group:
            value_sources.setdefault(claim["value"], set()).add(claim["source"])
            value_findings.setdefault(claim["value"], []).append(claim["finding"])

        unique_values = list(value_sources.keys())
        if len(unique_values) >= 2:
            all_sources: set[str] = set()
            for sources in value_sources.values():
                all_sources.update(sources)

            if len(all_sources) >= 2:
                hypotheses = [f"Works at {v.title()}" for v in unique_values[:3]]
                evidence = []
                for v, findings_list in value_findings.items():
                    for finding in findings_list:
                        evidence.append({
                            "description": finding.get("content", "")[:200],
                            "source": finding.get("source", "unknown"),
                            "supports_value": v,
                        })
                conflicts.append({
                    "dimension": dimension,
                    "hypotheses": hypotheses,
                    "evidence": evidence,
                })

    return conflicts


def _extract_companies(text: str) -> list[str]:
    """Extract company/organization names from text using patterns.

    Strategy:
    1. Suffix-anchored: match 1-3 tokens that start with an uppercase letter,
       immediately followed by a legal-entity suffix (Corp, Inc, ...).
       The name capture uses true uppercase anchors (no IGNORECASE on the
       character class) to avoid greedily absorbing preceding lowercase words.
    2. Preposition-anchored: capture the 1-3 capitalised tokens that follow a
       preposition word.  Only group 1 is kept (the preposition is non-capturing).

    After extraction any name whose lowercased form is a proper substring of
    another candidate is dropped so "acme" and "acme corp" don't become two
    distinct values.
    """
    _ROLE_WORDS = {"vp", "ceo", "cto", "coo", "cfo", "director", "founder",
                   "as", "since", "the", "and", "for", "with", "of", "at", "a"}
    candidates: set[str] = set()

    # Pattern 1: Suffix-anchored.
    # Name part: starts with an uppercase letter (no IGNORECASE on [A-Z] here).
    # Suffix part: case-insensitive via (?i) inline flag applied only to the suffix group.
    suffix_pattern = r'([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})\s+(?i:Corp|Inc|Ltd|LLC|Company|Group|Startup)\b'
    for match in re.finditer(suffix_pattern, text):
        full = match.group(0).strip().lower()
        candidates.add(full)

    # Pattern 2: Preposition-anchored — group 1 is the name only (preposition not captured).
    # Require the first token after the preposition to start with uppercase.
    prep_pattern = r'(?i:at|for|of|with)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})\b'
    for match in re.finditer(prep_pattern, text):
        tokens = match.group(1).strip().lower().split()
        # Trim trailing role/stopwords that bled in
        while tokens and tokens[-1] in _ROLE_WORDS:
            tokens.pop()
        name = " ".join(tokens)
        if len(name) > 2 and name not in _ROLE_WORDS:
            candidates.add(name)

    # Deduplicate: drop any name whose lowercased form is a proper substring of another
    result: list[str] = []
    for name in sorted(candidates, key=len, reverse=True):
        if not any(name != other and name in other for other in candidates):
            result.append(name)

    return result


def build_ach_matrix(
    hypotheses: list[str],
    evidence: list[dict],
) -> list[dict]:
    """Build the ACH evidence matrix.

    For each hypothesis, score each evidence item:
    ++ = strongly supports
    +  = supports
    0  = neutral
    -  = contradicts
    -- = strongly contradicts
    """
    matrix = []
    for hyp in hypotheses:
        scores = []
        hyp_lower = hyp.lower()

        for ev in evidence:
            desc = ev.get("description", "").lower()
            supports = ev.get("supports_value", "").lower()

            if supports and supports in hyp_lower:
                scores.append("++")
            elif supports and supports not in hyp_lower:
                scores.append("-")
            else:
                hyp_words = set(hyp_lower.split()) - {"works", "at", "is", "the", "a"}
                desc_words = set(desc.split())
                overlap = hyp_words & desc_words
                if len(overlap) >= 2:
                    scores.append("+")
                elif len(overlap) == 0 and len(hyp_words) > 1:
                    scores.append("0")
                else:
                    scores.append("0")

        matrix.append({"hypothesis": hyp, "scores": scores})

    return matrix


def evaluate_hypotheses(matrix: list[dict]) -> ACHResult:
    """Evaluate the ACH matrix. Winner = hypothesis with LEAST disconfirming evidence.

    This is the key ACH insight: we eliminate hypotheses with the most
    negative evidence, rather than selecting the one with the most positive.
    """
    _SCORE_VALUES = {"++": 2, "+": 1, "0": 0, "-": -1, "--": -2}

    scored = []
    for row in matrix:
        negatives = sum(1 for s in row["scores"] if s in ("-", "--"))
        total = sum(_SCORE_VALUES.get(s, 0) for s in row["scores"])
        scored.append({
            "hypothesis": row["hypothesis"],
            "negatives": negatives,
            "total": total,
            "scores": row["scores"],
        })

    scored.sort(key=lambda x: (x["negatives"], -x["total"]))

    winner = scored[0]
    runner_up = scored[1] if len(scored) > 1 else None

    if runner_up is None:
        confidence = "high"
    elif winner["negatives"] < runner_up["negatives"]:
        confidence = "high"
    elif winner["negatives"] == runner_up["negatives"] and winner["total"] > runner_up["total"] + 2:
        confidence = "moderate"
    else:
        confidence = "low"

    diagnostic: list[int] = []
    if len(matrix) >= 2:
        for i in range(len(matrix[0]["scores"])):
            values = [row["scores"][i] for row in matrix if i < len(row["scores"])]
            if len(set(values)) > 1:
                diagnostic.append(i)

    return ACHResult(
        winner=winner["hypothesis"],
        confidence=confidence,
        matrix=matrix,
        diagnostic_evidence=diagnostic,
        explanation=(
            f"{winner['hypothesis']} has {winner['negatives']} disconfirming evidence items"
            f" vs {runner_up['negatives'] if runner_up else 0} for the next best."
        ),
    )
