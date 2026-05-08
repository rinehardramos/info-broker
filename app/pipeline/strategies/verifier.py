# app/pipeline/strategies/verifier.py
"""Rule-based finding verifier for the Universal Research Engine (Phase A)."""

from __future__ import annotations

_MIN_CONTENT_LEN = 10
_CONFIDENCE_OVERREACH_THRESHOLD = 50  # > 50 triggers when error_flagged=True
_UNVERIFIED_CONFIDENCE_THRESHOLD = 70  # > 70 triggers when source is empty/unknown


def verify_findings(findings: list[dict]) -> dict:
    """Run rule-based quality checks on a list of research findings.

    Args:
        findings: List of finding dicts. Each may contain ``source``,
            ``content``, ``confidence``, and ``error_flagged`` keys.

    Returns:
        A dict with keys:
            ``status``  — "PASS", "PASS_WITH_NOTES", or "BLOCKED"
            ``issues``  — list of issue dicts, each with
                          ``type``, ``finding_index``, ``message``
    """
    if not findings:
        return {"status": "PASS", "issues": []}

    issues: list[dict] = []

    for idx, finding in enumerate(findings):
        source: str = finding.get("source", "") or ""
        content: str = finding.get("content", "") or ""
        confidence: int | float = finding.get("confidence", 0)
        error_flagged: bool = finding.get("error_flagged", False)

        # Check 1: missing_source
        if not source:
            issues.append(
                {
                    "type": "missing_source",
                    "finding_index": idx,
                    "message": f"Finding {idx} has no source or an empty source.",
                }
            )

        # Check 2: empty_content
        if len(content) < _MIN_CONTENT_LEN:
            issues.append(
                {
                    "type": "empty_content",
                    "finding_index": idx,
                    "message": (
                        f"Finding {idx} has missing or very short content "
                        f"(got {len(content)} chars, minimum {_MIN_CONTENT_LEN})."
                    ),
                }
            )

        # Check 3: confidence_overreach
        if error_flagged and confidence > _CONFIDENCE_OVERREACH_THRESHOLD:
            issues.append(
                {
                    "type": "confidence_overreach",
                    "finding_index": idx,
                    "message": (
                        f"Finding {idx} is error-flagged but reports confidence "
                        f"{confidence} (> {_CONFIDENCE_OVERREACH_THRESHOLD})."
                    ),
                }
            )

        # Check 4: unverified_high_confidence
        source_is_unverified = (not source) or ("unknown" in source.lower())
        if source_is_unverified and confidence > _UNVERIFIED_CONFIDENCE_THRESHOLD:
            issues.append(
                {
                    "type": "unverified_high_confidence",
                    "finding_index": idx,
                    "message": (
                        f"Finding {idx} has an unverified/unknown source but reports "
                        f"confidence {confidence} (> {_UNVERIFIED_CONFIDENCE_THRESHOLD})."
                    ),
                }
            )

    status = "PASS_WITH_NOTES" if issues else "PASS"
    return {"status": status, "issues": issues}
