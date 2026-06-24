"""Core Retrieval Pipeline (RAG Phase 2).

Implements a Multi-Stage retrieval process:
  1. Dense Vector Search (Qdrant) — retrieves top N candidate chunks based on
     semantic similarity.
  2. Reranking (Cross-Encoder) — re-scores the top N candidates against the
     exact query to catch keyword nuances and exact matches.

This dramatically improves hit-rate over single-stage vector search.
"""
from __future__ import annotations

from typing import Any

from app.db import qdrant_client
from app.services import embeddings, reranker


def retrieve_documents(
    query: str,
    user_id: str | None = None,
    institution_id: str = "ksrmce",
    project_id: str | None = None,
    top_k: int = 5,
    fetch_k: int = 20,
) -> list[dict[str, Any]]:
    """Retrieve and rerank document chunks for a query.

    1. Embeds the query using nomic-embed-text-v1.5 (Fireworks).
    2. Fetches `fetch_k` (e.g. 20) candidates from Qdrant.
    3. Reranks the candidates using qwen3-reranker (Fireworks).
    4. Returns the top `top_k` (e.g. 5) chunks.
    """
    if not query:
        return []

    # 1. Embed Query
    query_vector = embeddings.embed(query)
    
    # 2. Dense Retrieval (Qdrant)
    # We fetch a larger pool of candidates (fetch_k) for the reranker to evaluate
    candidates = qdrant_client.search_documents(
        query_embedding=query_vector,
        user_id=user_id,
        institution_id=institution_id,
        project_id=project_id,
        limit=fetch_k,
        score_threshold=0.3, # low threshold to catch more candidates
    )
    
    if not candidates:
        return []
        
    if len(candidates) <= 1:
        return candidates

    # 3. Cross-Encoder Reranking
    chunks_text = [c["content"] for c in candidates]
    reranked_scores = reranker.rerank(query, chunks_text, top_k=top_k)

    # 4. Re-order and threshold. The Fireworks reranker returns a normalised
    #    relevance_score in [0, 1]; the dense stage already applied a similarity
    #    floor, so we keep a permissive rerank floor and rely on the reordering
    #    (and top_k) to surface the best chunks.
    _RERANK_FLOOR = 0.02
    final_results = []
    for orig_idx, score in reranked_scores:
        if score >= _RERANK_FLOOR:
            candidate = candidates[orig_idx].copy()
            candidate["rerank_score"] = float(score)
            final_results.append(candidate)

    # Never return nothing just because the floor was too strict — if everything
    # was filtered, fall back to the top reranked candidate.
    if not final_results and reranked_scores:
        idx, score = reranked_scores[0]
        candidate = candidates[idx].copy()
        candidate["rerank_score"] = float(score)
        final_results.append(candidate)

    return final_results


def retrieve_memory(
    query: str,
    user_id: str,
    top_k: int = 5
) -> list[dict[str, Any]]:
    """Retrieve relevant facts from the user's memory."""
    query_vector = embeddings.embed(query)
    
    # For memory, we usually just need dense search as facts are short
    results = qdrant_client.search_memory(
        query_embedding=query_vector,
        user_id=user_id,
        limit=top_k,
        score_threshold=0.4,
    )
    return results
