"""Analysis of Competing Hypotheses (ACH) — CIA technique for resolving conflicting findings."""

from __future__ import annotations
import re
from dataclasses import dataclass, field


@dataclass
class ACHResult:
    winner: str
    confidence: str  # "high", "moderate", "low"
    matrix: list[dict]
    diagnostic_evidence: list[str]  # evidence labels that differentiate hypotheses
    ranking: list[str] = field(default_factory=list)
    negatives: list[int] = field(default_factory=list)
    positives: list[int] = field(default_factory=list)
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
        source = f.get("source", "unknown")
        companies = _extract_companies([f])
        for company in companies:
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


def _extract_companies(findings: list[dict]) -> list[str]:
    """Extract company/entity names from findings using entity value fields."""
    companies: set[str] = set()
    for f in findings:
        # Use structured entity fields if present
        for field_name in ("entity", "company", "organization", "employer", "value"):
            val = f.get(field_name) or (f.get("metadata") or {}).get(field_name, "")
            if val and isinstance(val, str) and len(val) > 1:
                companies.add(val.strip())
        # Fall back to content/title extraction for named entities
        for text_field in ("content", "title"):
            text = f.get(text_field) or ""
            # Capitalize-word pattern: 2+ consecutive Title-case words
            for match in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', text):
                companies.add(match.group(0))
    return sorted(companies)


def build_ach_matrix(
    hypotheses: list[str],
    findings: list[dict],
) -> list[dict]:
    """Build ACH consistency matrix. Each row = one piece of evidence.

    Cell values: ++ (strongly consistent), + (consistent), 0 (neutral/irrelevant),
    - (inconsistent), -- (strongly inconsistent).
    Hypothesis ranked by fewest -- marks (Heuer's principle).
    """
    matrix = []
    for finding in findings:
        content = " ".join([
            str(finding.get("title") or ""),
            str(finding.get("summary") or ""),
            str(finding.get("content") or ""),
            str(finding.get("description") or ""),
        ]).lower()

        row = {"evidence": finding.get("title") or finding.get("url") or finding.get("description") or "", "scores": []}
        for hyp in hypotheses:
            hyp_lower = hyp.lower()
            # Extract key terms from hypothesis
            hyp_terms = [w for w in re.findall(r'\b[a-z]{3,}\b', hyp_lower)
                        if w not in {"the", "and", "for", "with", "that", "this", "from", "has",
                                     "works", "at", "is", "a"}]

            # Check supports_value field for legacy evidence dicts
            supports = finding.get("supports_value", "").lower()
            if supports and supports in hyp_lower:
                row["scores"].append("++")
                continue
            if supports and supports not in hyp_lower:
                row["scores"].append("-")
                continue

            # Score: how many hypothesis terms appear in the evidence?
            matches = sum(1 for t in hyp_terms if t in content)
            ratio = matches / max(len(hyp_terms), 1)

            if ratio >= 0.6:
                score = "++"
            elif ratio >= 0.3:
                score = "+"
            elif ratio > 0:
                score = "0"
            else:
                # Evidence doesn't mention hypothesis terms — inconsistent
                score = "--" if len(hyp_terms) >= 2 else "-"

            row["scores"].append(score)
        matrix.append(row)
    return matrix


def evaluate_hypotheses(matrix: list[dict], hypotheses: list[str] | None = None) -> ACHResult:
    """Rank hypotheses by fewest inconsistencies (Heuer's ACH principle).

    The hypothesis with the fewest -- marks is most consistent with all evidence.
    Ties broken by total ++ count.

    Accepts both new-style (matrix is evidence-first rows with "scores" list indexed
    by hypothesis) and legacy-style (matrix is hypothesis-first rows with "hypothesis"
    key and "scores" list indexed by evidence).
    """
    if not matrix:
        return ACHResult(
            winner="",
            confidence="low",
            matrix=matrix,
            diagnostic_evidence=[],
            ranking=[],
            negatives=[],
            positives=[],
            explanation="No evidence matrix provided.",
        )

    # Detect legacy format: rows have a "hypothesis" key
    is_legacy = "hypothesis" in matrix[0]

    if is_legacy:
        # Legacy format: each row is a hypothesis with scores per evidence item
        hyp_names = [row["hypothesis"] for row in matrix]
        n_hyp = len(hyp_names)
        negatives = [0] * n_hyp
        positives = [0] * n_hyp

        for i, row in enumerate(matrix):
            for score in row.get("scores", []):
                if score == "--":
                    negatives[i] += 2
                elif score == "-":
                    negatives[i] += 1
                elif score == "++":
                    positives[i] += 2
                elif score == "+":
                    positives[i] += 1

        ranking_idx = sorted(range(n_hyp), key=lambda i: (negatives[i], -positives[i]))
        winner_idx = ranking_idx[0]
        runner_up_idx = ranking_idx[1] if len(ranking_idx) > 1 else None

        # Determine confidence
        if runner_up_idx is None:
            confidence = "high"
        elif negatives[winner_idx] < negatives[runner_up_idx]:
            confidence = "high"
        elif negatives[winner_idx] == negatives[runner_up_idx] and positives[winner_idx] > positives[runner_up_idx] + 2:
            confidence = "moderate"
        else:
            confidence = "low"

        # Diagnostic evidence: evidence indices where scores differ between winner and runner-up
        diagnostic_indices: list[int] = []
        if runner_up_idx is not None and len(matrix) >= 2:
            w_scores = matrix[winner_idx].get("scores", [])
            r_scores = matrix[runner_up_idx].get("scores", [])
            for i in range(min(len(w_scores), len(r_scores))):
                if w_scores[i] != r_scores[i]:
                    diagnostic_indices.append(i)

        return ACHResult(
            winner=hyp_names[winner_idx],
            confidence=confidence,
            matrix=matrix,
            diagnostic_evidence=diagnostic_indices,  # type: ignore[arg-type]
            ranking=[hyp_names[i] for i in ranking_idx],
            negatives=negatives,
            positives=positives,
            explanation=(
                f"{hyp_names[winner_idx]} has {negatives[winner_idx]} disconfirming evidence items"
                f" vs {negatives[runner_up_idx] if runner_up_idx is not None else 0} for the next best."
            ),
        )

    # New format: each row is evidence with "scores" list indexed by hypothesis position
    if not hypotheses:
        return ACHResult(
            winner="",
            confidence="low",
            matrix=matrix,
            diagnostic_evidence=[],
            ranking=[],
            negatives=[],
            positives=[],
            explanation="No hypotheses provided for new-format matrix.",
        )

    n_hyp = len(hypotheses)
    negatives = [0] * n_hyp
    positives = [0] * n_hyp

    for row in matrix:
        for i, score in enumerate(row.get("scores", [])[:n_hyp]):
            if score == "--":
                negatives[i] += 2
            elif score == "-":
                negatives[i] += 1
            elif score == "++":
                positives[i] += 2
            elif score == "+":
                positives[i] += 1

    ranking_idx = sorted(range(n_hyp), key=lambda i: (negatives[i], -positives[i]))
    winner_idx = ranking_idx[0]
    runner_up_idx = ranking_idx[1] if len(ranking_idx) > 1 else None

    confidence = "low"
    if runner_up_idx is not None:
        neg_gap = negatives[runner_up_idx] - negatives[winner_idx]
        if neg_gap >= 3:
            confidence = "high"
        elif neg_gap >= 1:
            confidence = "moderate"
    elif len(hypotheses) == 1:
        confidence = "high"

    # Diagnostic evidence: rows where scores differ between winner and runner-up
    diagnostic: list[str] = []
    if runner_up_idx is not None:
        for row in matrix:
            scores = row.get("scores", [])
            if (len(scores) > winner_idx and len(scores) > runner_up_idx and
                    scores[winner_idx] != scores[runner_up_idx]):
                diagnostic.append(row.get("evidence", ""))

    return ACHResult(
        winner=hypotheses[winner_idx],
        confidence=confidence,
        matrix=matrix,
        diagnostic_evidence=diagnostic[:5],
        ranking=[hypotheses[i] for i in ranking_idx],
        negatives=negatives,
        positives=positives,
        explanation=(
            f"{hypotheses[winner_idx]} has fewest inconsistencies ({negatives[winner_idx]}) "
            f"vs runner-up ({negatives[runner_up_idx] if runner_up_idx is not None else 0})."
        ),
    )
