"""Rule-based deception detection for research findings."""

from __future__ import annotations
from collections import Counter

# Minimum number of extra fields (beyond title/content/source) for "too perfect"
_PERFECT_THRESHOLD = 7

# Minimum substring length for "copied content" detection
_COPY_MIN_LEN = 50

# Fields that are considered standard / not counted toward "too perfect"
_STANDARD_FIELDS = frozenset({"title", "content", "source", "url", "confidence", "error_flagged"})


def detect_deception(findings: list[dict]) -> list[dict]:
    """Analyze findings for deception indicators.

    Returns findings enriched with:
      - deception_risk: float in [0.0, 1.0]
      - deception_flags: list of triggered flag names
    """
    if not findings:
        return []

    source_counts = Counter(f.get("source", "unknown") for f in findings)
    content_map = _build_content_map(findings)

    results = []
    for i, finding in enumerate(findings):
        flags: list[str] = []
        risk = 0.0

        # Flag: too_perfect — suspiciously many non-standard fields
        extra_fields = len([k for k in finding if k not in _STANDARD_FIELDS])
        if extra_fields >= _PERFECT_THRESHOLD:
            flags.append("too_perfect")
            risk += 0.2

        # Flag: source_echo — identical title+content from different sources
        if _check_source_echo(finding, content_map):
            flags.append("source_echo")
            risk += 0.3

        # Flag: copied_content — long shared substring with another finding
        if _check_copied_content(finding, findings, i):
            flags.append("copied_content")
            risk += 0.2

        # Flag: low_source_diversity — all findings come from a single tool
        if len(source_counts) == 1 and len(findings) >= 3:
            flags.append("low_source_diversity")
            risk += 0.15

        results.append({
            **finding,
            "deception_risk": min(round(risk, 2), 1.0),
            "deception_flags": flags,
        })

    return results


# ---------------------------------------------------------------------------
# Helpers (exported so tests can unit-test them directly)
# ---------------------------------------------------------------------------

def _build_content_map(findings: list[dict]) -> dict[tuple, list[str]]:
    """Map (title, content) -> list of sources that produced it."""
    content_map: dict[tuple, list[str]] = {}
    for f in findings:
        key = (f.get("title", ""), f.get("content", ""))
        source = f.get("source", "unknown")
        content_map.setdefault(key, []).append(source)
    return content_map


def _check_source_echo(finding: dict, content_map: dict[tuple, list[str]]) -> bool:
    """Return True if this finding's (title, content) appears from multiple distinct sources."""
    key = (finding.get("title", ""), finding.get("content", ""))
    sources = content_map.get(key, [])
    return len(sources) > 1 and len(set(sources)) > 1


def _check_copied_content(finding: dict, all_findings: list[dict], self_index: int) -> bool:
    """Return True if this finding shares a long verbatim substring with another finding."""
    content = finding.get("content", "")
    if len(content) < _COPY_MIN_LEN:
        return False

    for j, other in enumerate(all_findings):
        if j == self_index:
            continue
        other_content = other.get("content", "")
        # Slide a window of _COPY_MIN_LEN chars; step by 20 for efficiency
        for start in range(0, len(content) - _COPY_MIN_LEN + 1, 20):
            substr = content[start : start + _COPY_MIN_LEN]
            if substr in other_content:
                return True

    return False
