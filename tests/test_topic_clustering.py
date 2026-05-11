from app.pipeline.fusion.topic_clustering import cluster_findings


def test_empty_for_few_findings():
    assert cluster_findings([{"title": "a", "content": "b"}] * 3) == []


def test_clusters_returned():
    findings = [
        {"title": "LinkedIn profile search", "content": "Found employment history on LinkedIn for John Smith at Google"},
        {"title": "LinkedIn employment", "content": "John Smith worked at Google as Software Engineer per LinkedIn"},
        {"title": "GitHub repositories", "content": "GitHub repos found for john-smith username, Python projects"},
        {"title": "GitHub code search", "content": "Code search on GitHub returns john-smith repositories"},
        {"title": "Email discovery", "content": "SMTP verification found john.smith@gmail.com active"},
        {"title": "Email enumeration", "content": "Email patterns for John Smith: jsmith@google.com verified"},
    ]
    clusters = cluster_findings(findings, similarity_threshold=0.1)
    assert isinstance(clusters, list)
    # Each cluster has required fields
    for c in clusters:
        assert "label" in c
        assert "finding_indices" in c
        assert len(c["finding_indices"]) >= 2
