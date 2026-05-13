"""Topic clustering for investigation findings — pure Python, no external ML deps."""
from __future__ import annotations
import re
import math
from collections import Counter

STOPWORDS = {
    "the","a","an","and","or","but","in","on","at","to","for","of","with",
    "is","was","are","were","be","been","has","have","had","this","that",
    "it","its","by","from","as","about","which","who","what","when","where",
    "not","no","if","so","than","then","there","their","they","we","our",
    "you","your","he","she","his","her","him","us","all","more","also",
    "can","will","would","could","should","may","might","do","did","does",
    "been","being","i","my","me","am","up","out","into","over","after",
    "into","through","during","per","via","etc","n/a","na","source","reason",
}

def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    return [w for w in words if w not in STOPWORDS]

def _tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    tf = Counter(tokens)
    total = max(len(tokens), 1)
    return {t: (count / total) * idf.get(t, 1.0) for t, count in tf.items()}

def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    shared = set(a) & set(b)
    if not shared:
        return 0.0
    dot = sum(a[t] * b[t] for t in shared)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)

def cluster_findings(findings: list[dict], similarity_threshold: float = 0.25, max_clusters: int = 8) -> list[dict]:
    """Group findings by topic. Returns [{label, finding_indices}] or []."""
    if len(findings) < 5:
        return []

    # Build corpus text per finding
    texts = [
        f"{f.get('title', '')} {f.get('content', '')} {f.get('branch', '')}"
        for f in findings
    ]
    token_lists = [_tokenize(t) for t in texts]

    # Compute IDF over corpus
    n = len(texts)
    df: Counter = Counter()
    for tokens in token_lists:
        df.update(set(tokens))
    idf = {term: math.log(n / (1 + count)) + 1 for term, count in df.items()}

    vectors = [_tfidf_vector(tl, idf) for tl in token_lists]

    # Greedy agglomerative: assign each finding to the closest existing cluster centroid
    clusters: list[list[int]] = []  # list of finding-index lists
    centroids: list[dict[str, float]] = []

    for i, vec in enumerate(vectors):
        if not vec:
            continue
        best_sim, best_c = 0.0, -1
        for ci, centroid in enumerate(centroids):
            sim = _cosine(vec, centroid)
            if sim > best_sim:
                best_sim, best_c = sim, ci
        if best_sim >= similarity_threshold and len(clusters) <= max_clusters:
            clusters[best_c].append(i)
            # Update centroid: average of all vectors in cluster
            members = clusters[best_c]
            new_centroid: dict[str, float] = {}
            for mi in members:
                for term, score in vectors[mi].items():
                    new_centroid[term] = new_centroid.get(term, 0.0) + score / len(members)
            centroids[best_c] = new_centroid
        else:
            if len(clusters) < max_clusters:
                clusters.append([i])
                centroids.append(dict(vec))

    # Filter clusters with < 2 members; label each
    result = []
    for cluster_indices, centroid in zip(clusters, centroids):
        if len(cluster_indices) < 2:
            continue
        # Top 3 most distinctive terms in centroid (by TF-IDF weight)
        top_terms = sorted(centroid.items(), key=lambda x: -x[1])[:3]
        label = " ".join(t for t, _ in top_terms).title()
        result.append({"label": label, "finding_indices": sorted(cluster_indices)})

    return result[:max_clusters]
