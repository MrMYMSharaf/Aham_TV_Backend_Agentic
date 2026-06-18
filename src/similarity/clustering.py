import numpy as np
from typing import List, Dict, Any


def cosine_sim(a, b):
    a = np.array(a)
    b = np.array(b)

    return np.dot(a, b) / (
        np.linalg.norm(a) * np.linalg.norm(b)
    )


def cluster_articles(articles: List[Dict[str, Any]], threshold: float = 0.65):
    clusters = []
    used = set()

    for i in range(len(articles)):
        if i in used:
            continue

        base = articles[i]
        base_emb = np.array(base["embedding"])

        cluster = [base]
        used.add(i)

        for j in range(i + 1, len(articles)):
            if j in used:
                continue

            compare_emb = np.array(articles[j]["embedding"])
            score = cosine_sim(base_emb, compare_emb)

            if score >= threshold:
                cluster.append(articles[j])
                used.add(j)

        clusters.append(cluster)

    return clusters