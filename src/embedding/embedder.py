import json
from typing import Dict, Any, List

from embedding.model import model


def embed_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    embedded_articles = []

    for article in articles:
        text = f"{article.get('title','')} {article.get('content','')}"

        embedding = model.encode(text, normalize_embeddings=True)

        embedded_articles.append({
            "title": article.get("title"),
            "content": article.get("content"),
            "source": article.get("source"),
            "link": article.get("link"),
            "embedding": embedding.tolist()
        })

    return embedded_articles