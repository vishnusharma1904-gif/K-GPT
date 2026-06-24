"""Qdrant vector database client — replaces pgvector for RAG at scale.

Follows the same pattern as supabase_client.py: module-level singleton via
@lru_cache, thin wrapper functions.

WHY Qdrant over pgvector:
  1. HNSW index — no rebuild required (pgvector IVFFlat blocks during rebuild)
  2. Payload filtering — filter by user_id, project_id, kind, institution_id
     during vector search (pgvector needs a separate WHERE + ANN scan)
  3. Quantization — 4x memory savings at minimal quality loss
  4. Performance — sub-50ms p99 at 1M vectors (pgvector degrades past 500K)
  5. Dedicated service — doesn't compete with PG for memory/CPU

The existing pgvector memory_chunks table is kept for backward compatibility.
New documents go to Qdrant; the migration moves old chunks in a background job.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.config import get_settings

# Collection names — matching the Prompt Pulse architecture
COLLECTION_DOCUMENTS = "pp_documents"       # document chunks for RAG
COLLECTION_MEMORY = "pp_memory"             # user memory (facts, notes, conversation)
COLLECTION_CACHE = "pp_semantic_cache"      # semantic response cache

# Embedding dimensions — nomic-embed-text-v1.5 = 768 (upgrade from MiniLM 384).
# Must stay in sync with embeddings._DIM.
VECTOR_DIM = 768


@lru_cache
def _client():
    """Lazy Qdrant client. Returns None if not configured."""
    settings = get_settings()
    if not settings.qdrant_host:
        return None
    try:
        from qdrant_client import QdrantClient
        return QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key or None,
            timeout=10,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[warn] Qdrant not available: {e}")
        return None


def available() -> bool:
    """Check if Qdrant is connected."""
    c = _client()
    if not c:
        return False
    try:
        c.get_collections()
        return True
    except Exception:
        return False


def ensure_collections() -> None:
    """Create collections if they don't exist. Safe to call on every startup.

    Never raises: if Qdrant is configured but unreachable, we log and return so a
    down vector DB can't crash the API/worker startup (retrieval just falls back).
    """
    c = _client()
    if not c:
        return
    try:
        _ensure_collections(c)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] Qdrant ensure_collections skipped (unreachable?): {e}")


def _ensure_collections(c) -> None:
    from qdrant_client.models import (
        Distance,
        VectorParams,
        PayloadSchemaType,
    )

    existing = {col.name for col in c.get_collections().collections}

    # --- Documents collection (RAG chunks) ---
    if COLLECTION_DOCUMENTS not in existing:
        c.create_collection(
            collection_name=COLLECTION_DOCUMENTS,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        # Payload indexes for filtered search
        for field, schema in [
            ("user_id", PayloadSchemaType.KEYWORD),
            ("institution_id", PayloadSchemaType.KEYWORD),
            ("project_id", PayloadSchemaType.KEYWORD),
            ("document_id", PayloadSchemaType.KEYWORD),
            ("kind", PayloadSchemaType.KEYWORD),
            ("subject", PayloadSchemaType.KEYWORD),
        ]:
            try:
                c.create_payload_index(COLLECTION_DOCUMENTS, field, schema)
            except Exception:
                pass  # index may already exist

    # --- Memory collection (user facts, notes, conversation summaries) ---
    if COLLECTION_MEMORY not in existing:
        c.create_collection(
            collection_name=COLLECTION_MEMORY,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        for field, schema in [
            ("user_id", PayloadSchemaType.KEYWORD),
            ("kind", PayloadSchemaType.KEYWORD),
            ("layer", PayloadSchemaType.KEYWORD),
        ]:
            try:
                c.create_payload_index(COLLECTION_MEMORY, field, schema)
            except Exception:
                pass

    # --- Semantic cache collection ---
    if COLLECTION_CACHE not in existing:
        c.create_collection(
            collection_name=COLLECTION_CACHE,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        for field, schema in [
            ("institution_id", PayloadSchemaType.KEYWORD),
        ]:
            try:
                c.create_payload_index(COLLECTION_CACHE, field, schema)
            except Exception:
                pass

    print("[ok] Qdrant collections ensured")


# === Document Operations ====================================================

def upsert_chunks(
    document_id: str,
    chunks: list[dict],
    user_id: str,
    institution_id: str = "ksrmce",
    project_id: str | None = None,
    shared: bool = False,
) -> int:
    """Store document chunks with embeddings in Qdrant.

    Each chunk dict must have: 'content', 'embedding' (list[float]), 'index' (int).
    Optional: 'metadata' (dict with topic, subject, keywords, etc.)
    When `shared=True`, the chunk is part of the institution-wide knowledge base
    and is retrievable by every user (see search_shared_documents).
    Returns the number of chunks stored.
    """
    c = _client()
    if not c or not chunks:
        return 0

    from qdrant_client.models import PointStruct
    import uuid

    points = []
    for chunk in chunks:
        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=chunk["embedding"],
            payload={
                "user_id": user_id,
                "institution_id": institution_id,
                "project_id": project_id,
                "document_id": document_id,
                "chunk_index": chunk.get("index", 0),
                "kind": "institution" if shared else "document",
                "shared": shared,
                "verified": shared,
                "content": chunk["content"],
                "source": chunk.get("source", ""),
                **(chunk.get("metadata") or {}),
            },
        ))

    c.upsert(collection_name=COLLECTION_DOCUMENTS, points=points)
    return len(points)


def search_shared_documents(
    query_embedding: list[float],
    institution_id: str = "ksrmce",
    limit: int = 6,
    score_threshold: float = 0.3,
) -> list[dict[str, Any]]:
    """Search ONLY the institution-wide shared knowledge base (shared=true),
    ignoring user_id so every user sees admin-verified documents."""
    c = _client()
    if not c:
        return []

    from qdrant_client.models import Filter, FieldCondition, MatchValue

    conditions = [FieldCondition(key="shared", match=MatchValue(value=True))]
    if institution_id:
        conditions.append(FieldCondition(key="institution_id", match=MatchValue(value=institution_id)))

    try:
        results = c.search(
            collection_name=COLLECTION_DOCUMENTS,
            query_vector=query_embedding,
            query_filter=Filter(must=conditions),
            limit=limit,
            score_threshold=score_threshold,
        )
        return [
            {"id": str(r.id), "content": r.payload.get("content", ""),
             "source": r.payload.get("source", ""), "score": r.score}
            for r in results
        ]
    except Exception as e:
        print(f"[warn] Qdrant shared search failed: {e}")
        return []


def search_documents(
    query_embedding: list[float],
    user_id: str | None = None,
    institution_id: str | None = None,
    project_id: str | None = None,
    kind: str | None = None,
    limit: int = 20,
    score_threshold: float = 0.3,
) -> list[dict[str, Any]]:
    """Search document chunks by vector similarity with payload filtering.

    Returns list of dicts with: content, source, score, metadata.
    """
    c = _client()
    if not c:
        return []

    from qdrant_client.models import Filter, FieldCondition, MatchValue

    # Build filter conditions
    conditions = []
    if user_id:
        conditions.append(FieldCondition(key="user_id", match=MatchValue(value=user_id)))
    if institution_id:
        conditions.append(FieldCondition(key="institution_id", match=MatchValue(value=institution_id)))
    if project_id:
        conditions.append(FieldCondition(key="project_id", match=MatchValue(value=project_id)))
    if kind:
        conditions.append(FieldCondition(key="kind", match=MatchValue(value=kind)))

    query_filter = Filter(must=conditions) if conditions else None

    try:
        results = c.search(
            collection_name=COLLECTION_DOCUMENTS,
            query_vector=query_embedding,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
        )
        return [
            {
                "id": str(r.id),
                "content": r.payload.get("content", ""),
                "source": r.payload.get("source", ""),
                "score": r.score,
                "document_id": r.payload.get("document_id"),
                "chunk_index": r.payload.get("chunk_index", 0),
                "metadata": {k: v for k, v in r.payload.items()
                             if k not in ("content", "source", "user_id",
                                          "institution_id", "project_id",
                                          "document_id", "chunk_index", "kind")},
            }
            for r in results
        ]
    except Exception as e:
        print(f"[warn] Qdrant search failed: {e}")
        return []


def delete_document_chunks(document_id: str) -> None:
    """Delete all chunks belonging to a document."""
    c = _client()
    if not c:
        return

    from qdrant_client.models import Filter, FieldCondition, MatchValue

    try:
        c.delete(
            collection_name=COLLECTION_DOCUMENTS,
            points_selector=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
            ),
        )
    except Exception as e:
        print(f"[warn] Qdrant delete failed: {e}")


def list_shared_documents() -> list[dict[str, Any]]:
    """List shared-KB docs grouped by source filename, with chunk counts."""
    c = _client()
    if not c:
        return []

    from qdrant_client.models import Filter, FieldCondition, MatchValue

    grouped: dict[str, dict] = {}
    try:
        offset = None
        while True:
            points, offset = c.scroll(
                collection_name=COLLECTION_DOCUMENTS,
                scroll_filter=Filter(must=[FieldCondition(key="shared", match=MatchValue(value=True))]),
                with_payload=True, with_vectors=False, limit=256, offset=offset,
            )
            for p in points:
                src = (p.payload or {}).get("source") or "(untitled)"
                g = grouped.setdefault(src, {"source": src, "chunks": 0, "created_at": None})
                g["chunks"] += 1
            if offset is None:
                break
    except Exception as e:
        print(f"[warn] Qdrant shared list failed: {e}")
    return sorted(grouped.values(), key=lambda x: x["chunks"], reverse=True)


def delete_shared_document(source: str) -> int:
    """Delete every shared chunk for a source filename. Returns -1 if unknown count."""
    c = _client()
    if not c:
        return 0

    from qdrant_client.models import Filter, FieldCondition, MatchValue

    try:
        c.delete(
            collection_name=COLLECTION_DOCUMENTS,
            points_selector=Filter(must=[
                FieldCondition(key="shared", match=MatchValue(value=True)),
                FieldCondition(key="source", match=MatchValue(value=source)),
            ]),
        )
        return -1  # Qdrant delete doesn't return a count
    except Exception as e:
        print(f"[warn] Qdrant shared delete failed: {e}")
        return 0


# === Memory Operations (Layer 2-5) ==========================================

def upsert_memory(
    memory_id: str,
    content: str,
    embedding: list[float],
    user_id: str,
    kind: str = "fact",
    layer: str = "longterm",
    source: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Store a memory chunk in the memory collection."""
    c = _client()
    if not c:
        return

    from qdrant_client.models import PointStruct

    c.upsert(
        collection_name=COLLECTION_MEMORY,
        points=[PointStruct(
            id=memory_id,
            vector=embedding,
            payload={
                "user_id": user_id,
                "kind": kind,
                "layer": layer,
                "content": content,
                "source": source,
                **(metadata or {}),
            },
        )],
    )


def search_memory(
    query_embedding: list[float],
    user_id: str,
    layer: str | None = None,
    limit: int = 6,
    score_threshold: float = 0.40,
) -> list[dict[str, Any]]:
    """Search user memories by vector similarity."""
    c = _client()
    if not c:
        return []

    from qdrant_client.models import Filter, FieldCondition, MatchValue

    conditions = [FieldCondition(key="user_id", match=MatchValue(value=user_id))]
    if layer:
        conditions.append(FieldCondition(key="layer", match=MatchValue(value=layer)))

    try:
        results = c.search(
            collection_name=COLLECTION_MEMORY,
            query_vector=query_embedding,
            query_filter=Filter(must=conditions),
            limit=limit,
            score_threshold=score_threshold,
        )
        return [
            {
                "id": str(r.id),
                "content": r.payload.get("content", ""),
                "source": r.payload.get("source"),
                "similarity": r.score,
                "kind": r.payload.get("kind"),
                "layer": r.payload.get("layer"),
            }
            for r in results
        ]
    except Exception:
        return []


# === Semantic Cache ==========================================================

def cache_search(
    query_embedding: list[float],
    threshold: float = 0.95,
) -> dict | None:
    """Find a semantically similar cached response. Returns None on miss."""
    c = _client()
    if not c:
        return None

    try:
        results = c.search(
            collection_name=COLLECTION_CACHE,
            query_vector=query_embedding,
            limit=1,
            score_threshold=threshold,
        )
        if results:
            return results[0].payload
        return None
    except Exception:
        return None


def cache_store(
    query_embedding: list[float],
    response: str,
    model: str,
    institution_id: str = "ksrmce",
) -> None:
    """Store a response in the semantic cache."""
    c = _client()
    if not c:
        return

    from qdrant_client.models import PointStruct
    import uuid

    try:
        c.upsert(
            collection_name=COLLECTION_CACHE,
            points=[PointStruct(
                id=str(uuid.uuid4()),
                vector=query_embedding,
                payload={
                    "response": response,
                    "model": model,
                    "institution_id": institution_id,
                },
            )],
        )
    except Exception:
        pass


# === Health ==================================================================

def health() -> dict:
    """Health check for /api/health."""
    c = _client()
    if not c:
        return {"status": "not_configured"}
    try:
        collections = c.get_collections().collections
        return {
            "status": "ok",
            "collections": {col.name: col.points_count for col in collections},
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
