"""RAG orchestration — Qdrant-first retrieval with a pgvector fallback, plus a
semantic response cache that lets repeated / near-duplicate questions skip the
LLM entirely.

Two efficiency wins live here:

  1. Retrieval cutover — when Qdrant is configured the chat layer grounds answers
     in uploaded documents (dense search + cross-encoder rerank) and user memory
     facts. When it isn't, we fall back to the legacy pgvector `match_memory`
     path so nothing breaks during the migration.

  2. Semantic cache — generic questions (no personalisation, no web/image/project
     context) are answered straight from Qdrant's `pp_semantic_cache` collection
     when a previously-answered question is ~identical. That returns a high-quality
     answer with ZERO LLM tokens, which is the single biggest lever for cutting
     both cost and load.

Everything degrades to a no-op when the relevant service is unconfigured.
"""
from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.db import qdrant_client
from app.db import supabase_client as db
from app.services import embeddings, reranker

# --- Retrieval tuning --------------------------------------------------------
DOC_FETCH_K = 12        # candidates pulled from Qdrant before reranking
DOC_TOP_K = 4           # document chunks kept after rerank
MEM_TOP_K = 3           # memory facts kept
DOC_SNIPPET_CHARS = 700  # cap each doc chunk injected into the prompt (token control)

# --- Semantic cache tuning ---------------------------------------------------
# Cosine similarity must be very high to serve a cached answer — we only want
# near-identical questions, never merely "related" ones.
CACHE_THRESHOLD = 0.97
_CACHE_MIN_REPLY_CHARS = 40

SHARED_TOP_K = 4        # institution-wide verified docs pulled per query


def qdrant_enabled() -> bool:
    return bool(get_settings().qdrant_host)


def retrieve_shared(vec: list[float]) -> list[dict[str, Any]]:
    """Institution-wide, admin-verified knowledge base — visible to ALL users.
    Qdrant when configured, else legacy pgvector. Never raises."""
    try:
        if qdrant_enabled():
            return qdrant_client.search_shared_documents(vec, limit=SHARED_TOP_K)
        return db.match_shared_memory(vec, limit=SHARED_TOP_K)
    except Exception:
        return []


def embed_query(query: str) -> list[float]:
    """Single, Redis-cached embedding for the whole request (reused by retrieval
    and the semantic cache so we never embed the same query twice)."""
    return embeddings.embed(query)


def retrieve(user_id: str, query: str, vec: list[float],
             project_id: str | None = None) -> tuple[list[str], list[dict[str, Any]]]:
    """Return (context_lines, citations) grounding the answer.

    Qdrant-first: reranked document chunks + memory facts. Falls back to the
    legacy pgvector memory match when Qdrant isn't configured. `vec` is the
    pre-computed query embedding, passed in to avoid re-embedding.
    """
    lines: list[str] = []
    citations: list[dict[str, Any]] = []

    # --- Institution knowledge base FIRST: admin-verified docs every user sees.
    #     Ranked at the top so the model grounds its answer on them before
    #     anything else. ---
    for h in retrieve_shared(vec):
        src = h.get("source") or "knowledge base"
        snippet = (h.get("content") or "")[:DOC_SNIPPET_CHARS]
        if not snippet:
            continue
        lines.append(f"- [VERIFIED · {src}] {snippet}")
        citations.append({"type": "knowledge", "source": src,
                          "id": h.get("id"), "snippet": snippet[:160]})

    if qdrant_enabled():
        # --- Uploaded documents: dense retrieve, then cross-encoder rerank ---
        candidates = qdrant_client.search_documents(
            query_embedding=vec, user_id=user_id, project_id=project_id,
            limit=DOC_FETCH_K, score_threshold=0.3,
        )
        if candidates:
            scored = reranker.rerank(query, [c["content"] for c in candidates],
                                     top_k=DOC_TOP_K)
            for idx, score in scored:
                d = candidates[idx]
                src = d.get("source") or "document"
                snippet = (d.get("content") or "")[:DOC_SNIPPET_CHARS]
                if not snippet:
                    continue
                lines.append(f"- ({src}) {snippet}")
                citations.append({"type": "document", "source": src,
                                  "id": d.get("id"), "snippet": snippet[:160]})

        # --- User memory facts: dense search only (facts are short) ---
        for h in qdrant_client.search_memory(vec, user_id, limit=MEM_TOP_K):
            src = h.get("source") or "memory"
            lines.append(f"- ({src}) {h['content']}")
            citations.append({"type": "memory", "source": src, "id": h.get("id"),
                              "snippet": h["content"][:160]})
    else:
        # --- Legacy pgvector fallback ---
        for h in db.match_memory(user_id, vec, limit=5):
            src = h.get("source") or "memory"
            lines.append(f"- ({src}) {h['content']}")
            citations.append({"type": "memory", "source": src, "id": h.get("id"),
                              "snippet": h["content"][:160]})

    return lines, citations


def cache_lookup(vec: list[float]) -> dict | None:
    """Return a cached {response, model, ...} for a near-identical question, or
    None. No-op without Qdrant."""
    if not qdrant_enabled():
        return None
    return qdrant_client.cache_search(vec, threshold=CACHE_THRESHOLD)


def cache_store(vec: list[float], reply: str, model: str,
                institution_id: str = "ksrmce") -> None:
    """Persist a generic answer for future cache hits. Callers must only pass
    NON-personalised answers (see chat._cache_eligible)."""
    if not qdrant_enabled() or not reply or len(reply) < _CACHE_MIN_REPLY_CHARS:
        return
    qdrant_client.cache_store(vec, reply, model, institution_id)
