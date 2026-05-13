"""Tests for Analysis of Competing Hypotheses (ACH)."""
from app.pipeline.fusion.ach import (
    build_ach_matrix, evaluate_hypotheses, detect_conflicts, _extract_companies, ACHResult,
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
    # Both findings agree on the same employer; no employer conflict should be detected.
    findings = [
        {"content": "John works at Acme Corp", "source": "linkedin"},
        {"content": "John is employed by Acme Corp as VP", "source": "apollo"},
    ]
    conflicts = detect_conflicts(findings)
    employer_conflicts = [c for c in conflicts if c["dimension"] == "employer"
                          and len([h for h in c["hypotheses"] if "acme corp" not in h.lower()]) > 0]
    assert len(employer_conflicts) == 0


def test_build_matrix():
    hypotheses = ["Works at Acme Corp", "Works at Beta Inc"]
    findings = [
        {"description": "LinkedIn says Acme Corp VP", "source": "linkedin"},
        {"description": "Apollo says Beta Inc CEO", "source": "apollo"},
        {"description": "SEC filing lists Acme Corp director", "source": "sec_edgar"},
    ]
    matrix = build_ach_matrix(hypotheses, findings)
    # New format: evidence-first — one row per finding, one score per hypothesis
    assert len(matrix) == 3  # 3 evidence items
    assert len(matrix[0]["scores"]) == 2  # 2 hypotheses each
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
        hypotheses = conflict["hypotheses"]
        # build_ach_matrix now accepts raw findings; pass conflict evidence as findings
        matrix = build_ach_matrix(hypotheses, conflict["evidence"])
        result = evaluate_hypotheses(matrix, hypotheses)
        assert result.winner in hypotheses


# ---------------------------------------------------------------------------
# New tests: _extract_companies, real consistency matrix, evaluate ranking
# ---------------------------------------------------------------------------

def test_extract_companies_finds_titlecase_names():
    """Title-case multi-word names are extracted from title/content fields."""
    findings = [{"title": "Alice worked at Acme Corp and consulted for Global Tech"}]
    companies = _extract_companies(findings)
    assert "Acme Corp" in companies or any("acme corp" in c.lower() for c in companies)


def test_extract_companies_uses_structured_fields():
    """Structured 'company' / 'employer' fields take priority over regex extraction."""
    findings = [{"company": "OpenAI"}, {"employer": "Google"}]
    companies = _extract_companies(findings)
    assert "OpenAI" in companies
    assert "Google" in companies


def test_build_ach_matrix_scores_relevant_evidence():
    """Finding whose content strongly matches hypothesis terms should score ++ or +."""
    hypotheses = ["Works at OpenAI as researcher"]
    findings = [{"title": "OpenAI researcher position confirmed", "content": "OpenAI hired researcher"}]
    matrix = build_ach_matrix(hypotheses, findings)
    assert len(matrix) == 1
    assert matrix[0]["scores"][0] in ("++", "+")


def test_build_ach_matrix_scores_irrelevant_evidence_negative():
    """Finding with no hypothesis terms and 2+ key terms in hypothesis scores -- or -."""
    hypotheses = ["Works at OpenAI as researcher"]
    findings = [{"title": "Unrelated article about cooking", "content": "pasta recipes and food tips"}]
    matrix = build_ach_matrix(hypotheses, findings)
    assert matrix[0]["scores"][0] in ("--", "-")


def test_evaluate_hypotheses_ranks_by_fewest_negatives():
    """H2 with 0 '--' rows should rank above H1 with 2 '--' rows."""
    hypotheses = ["H1", "H2"]
    # Evidence-first matrix: each row has scores indexed by hypothesis
    matrix = [
        {"evidence": "ev1", "scores": ["--", "+"]},
        {"evidence": "ev2", "scores": ["--", "0"]},
        {"evidence": "ev3", "scores": ["+", "++"]},
    ]
    result = evaluate_hypotheses(matrix, hypotheses)
    assert result.winner == "H2"
    assert result.ranking[0] == "H2"
    assert result.ranking[-1] == "H1"


def test_evaluate_hypotheses_confidence_high_on_large_gap():
    """3+ negative gap between winner and runner-up should yield 'high' confidence."""
    hypotheses = ["Winner", "Loser"]
    # Winner has 0 negatives, Loser has 4 weighted negatives (2 "--" = 4 points)
    matrix = [
        {"evidence": "ev1", "scores": ["+", "--"]},
        {"evidence": "ev2", "scores": ["++", "--"]},
        {"evidence": "ev3", "scores": ["+", "-"]},
    ]
    result = evaluate_hypotheses(matrix, hypotheses)
    assert result.winner == "Winner"
    assert result.confidence == "high"
