"""API-based Reranker via Fireworks AI (qwen3-reranker-8b).

WHY Reranking:
  Vector search (Qdrant) only checks semantic similarity, which often misses
  exact keyword matches or nuances in the query. By retrieving the top 20
  chunks from Qdrant, and then passing them through a Reranker, the 
  attention mechanism considers the query and the chunk TOGETHER, vastly 
  improving retrieval accuracy (hit rate).

Shifted from local CPU embeddings to a hosted API to save RAM and dramatically
increase concurrent performance without blocking CPU.
"""
from __future__ import annotations

import httpx
from app.core.config import get_settings

_MODEL_NAME = "accounts/fireworks/models/qwen3-reranker-8b"
_API_URL = "https://api.fireworks.ai/inference/v1/rerank"


def rerank(query: str, chunks: list[str], top_k: int = 5) -> list[tuple[int, float]]:
    """Score chunks against the query via Fireworks AI.
    
    Returns a list of tuples: (original_index, score), sorted by score descending.
    Higher is better.
    """
    if not query or not chunks:
        return []

    settings = get_settings()
    if not settings.fireworks_api_key:
        print("[warn] FIREWORKS_API_KEY is not set. Skipping reranking.")
        return [(i, 0.0) for i in range(min(top_k, len(chunks)))]

    try:
        response = httpx.post(
            _API_URL,
            headers={
                "Authorization": f"Bearer {settings.fireworks_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": _MODEL_NAME,
                "query": query,
                "documents": chunks
            },
            timeout=10.0
        )
        response.raise_for_status()
        data = response.json()

        # Fireworks /rerank returns results as a list of
        #   {"index": 0, "relevance_score": 0.92, ...}
        # Different API versions key it as "results" (Cohere-style) or "data",
        # so accept either.
        results = data.get("results") or data.get("data") or []

        scored = []
        for item in results:
            idx = item.get("index")
            score = item.get("relevance_score", item.get("score", 0.0))
            if idx is not None:
                scored.append((idx, float(score)))
        # Usually pre-sorted by the API, but sort defensively.
        scored.sort(key=lambda x: x[1], reverse=True)

        return scored[:top_k]
    except Exception as e:
        print(f"[warn] Fireworks Reranking failed: {e}")
        # Fallback to returning them in the original order
        return [(i, 0.0) for i in range(min(top_k, len(chunks)))]


def warm() -> None:
    """Pre-load the reranker model. (No-op since we are using a remote API)."""
    pass
