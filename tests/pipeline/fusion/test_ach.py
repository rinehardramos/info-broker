"""Tests for Analysis of Competing Hypotheses (ACH)."""
from app.pipeline.fusion.ach import (
    build_ach_matrix, evaluate_hypotheses, detect_conflicts, ACHResult,
)


def test_detect_conflicts_finds_contradictions():
    findings = [
        {"content": "John works at Acme Corp as VP Sales", "source": "linkedin"},
        {"content": "John is CEO of Beta Inc since 2024", "source": "apollo"},
        {"content": "John listed at Acme Corp", "source": "sec_edgar"},
    ]
    conflicts = detect_conflicts(findings)
    assert len(conflicts) >= 1
    assert any("employer" in c["dimension"] or "company" in c["dimension"].lower() for c in conflicts)


def test_detect_conflicts_no_contradictions():
    findings = [
        {"content": "John works at Acme Corp", "source": "linkedin"},
        {"content": "John Doe at Acme Corp as VP", "source": "apollo"},
    ]
    conflicts = detect_conflicts(findings)
    assert len(conflicts) == 0


def test_build_matrix():
    hypotheses = ["Works at Acme Corp", "Works at Beta Inc"]
    evidence = [
        {"description": "LinkedIn says Acme Corp VP", "source": "linkedin"},
        {"description": "Apollo says Beta Inc CEO", "source": "apollo"},
        {"description": "SEC filing lists Acme Corp director", "source": "sec_edgar"},
    ]
    matrix = build_ach_matrix(hypotheses, evidence)
    assert len(matrix) == 2  # 2 hypotheses
    assert len(matrix[0]["scores"]) == 3  # 3 evidence items each
    assert all(s in ("++", "+", "0", "-", "--") for row in matrix for s in row["scores"])


def test_evaluate_selects_least_disconfirmed():
    matrix = [
        {"hypothesis": "Acme Corp", "scores": ["+", "0", "++"]},  # 0 negatives
        {"hypothesis": "Beta Inc", "scores": ["-", "+", "--"]},  # 2 negatives
    ]
    result = evaluate_hypotheses(matrix)
    assert result.winner == "Acme Corp"
    assert result.confidence == "high"  # Clear winner


def test_evaluate_low_confidence_when_close():
    matrix = [
        {"hypothesis": "A", "scores": ["+", "-"]},  # 1 negative
        {"hypothesis": "B", "scores": ["-", "+"]},  # 1 negative
    ]
    result = evaluate_hypotheses(matrix)
    assert result.confidence in ("low", "moderate")  # Tied or close


def test_evaluate_returns_diagnostics():
    matrix = [
        {"hypothesis": "A", "scores": ["+", "0", "-"]},
        {"hypothesis": "B", "scores": ["-", "+", "0"]},
    ]
    result = evaluate_hypotheses(matrix)
    assert hasattr(result, "winner")
    assert hasattr(result, "confidence")
    assert hasattr(result, "matrix")
    assert hasattr(result, "diagnostic_evidence")


def test_full_ach_flow():
    """Full flow: findings -> detect conflicts -> build matrix -> evaluate."""
    findings = [
        {"content": "John works at Acme Corp as VP Sales since 2020", "source": "linkedin"},
        {"content": "John is founder and CEO of Beta Startup since 2023", "source": "crunchbase"},
        {"content": "Acme Corp lists John Doe as active director", "source": "sec_edgar"},
        {"content": "John's LinkedIn shows current position at Acme", "source": "web_crawl"},
    ]
    conflicts = detect_conflicts(findings)
    if conflicts:
        conflict = conflicts[0]
        matrix = build_ach_matrix(conflict["hypotheses"], conflict["evidence"])
        result = evaluate_hypotheses(matrix)
        assert result.winner in ("Works at Acme Corp", "Works at Beta Startup",
                                  conflict["hypotheses"][0], conflict["hypotheses"][1])
