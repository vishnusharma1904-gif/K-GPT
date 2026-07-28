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
            # Without this, qdrant-client assumes HTTPS as soon as an api_key is
            # set, which fails ([SSL: WRONG_VERSION_NUMBER]) against the plain-HTTP
            # Docker Qdrant. Set QDRANT_HTTPS=true only for a TLS cloud endpoint.
            https=settings.qdrant_https,
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
            # Per-cohort scoping of shared-KB chunks (NULL/absent = Everyone).
            ("scope_branch", PayloadSchemaType.KEYWORD),
            ("scope_year", PayloadSchemaType.INTEGER),
            ("scope_section", PayloadSchemaType.KEYWORD),
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

def _scope_payload(scope: dict | None) -> dict:
    """Normalise a {branch, year, section} scope into payload keys, OMITTING any
    dimension that's a wildcard. Absent key = "Everyone for that dimension", which
    the retrieval filter treats as IsEmpty. So an unscoped (Everyone) doc carries
    no scope_* keys — keeping old chunks valid without a backfill."""
    out: dict = {}
    if not scope:
        return out
    b = (scope.get("branch") or "").strip().upper()
    s = (scope.get("section") or "").strip().upper()
    y = scope.get("year")
    if b:
        out["scope_branch"] = b
    if s:
        out["scope_section"] = s
    if y not in (None, "", 0):
        try:
            out["scope_year"] = int(y)
        except (TypeError, ValueError):
            pass
    return out


def upsert_chunks(
    document_id: str,
    chunks: list[dict],
    user_id: str,
    institution_id: str = "ksrmce",
    project_id: str | None = None,
    shared: bool = False,
    scope: dict | None = None,
) -> int:
    """Store document chunks with embeddings in Qdrant.

    Each chunk dict must have: 'content', 'embedding' (list[float]), 'index' (int).
    Optional: 'metadata' (dict with topic, subject, keywords, etc.)
    When `shared=True`, the chunk is part of the shared knowledge base. `scope`
    (a {branch, year, section} dict, any subset) targets it to a cohort; omit /
    leave blank for an institution-wide ("Everyone") document.
    Returns the number of chunks stored.
    """
    c = _client()
    if not c or not chunks:
        return 0

    from qdrant_client.models import PointStruct
    import uuid

    scope_payload = _scope_payload(scope) if shared else {}

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
                **scope_payload,
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
    scope: dict | None = None,
) -> list[dict[str, Any]]:
    """Search the shared knowledge base (shared=true), ignoring user_id so every
    user sees admin/faculty-verified documents — but HARD-SCOPED to the caller's
    cohort when `scope` is given.

    `scope` = {branch, year, section} (any subset). A chunk is visible iff, for
    each dimension the chunk SETS, it equals the student's value; a dimension the
    chunk leaves unset is "Everyone". Pass `scope=None` (faculty/admin) to bypass
    scoping and see every shared document."""
    c = _client()
    if not c:
        return []

    from qdrant_client.models import (Filter, FieldCondition, MatchValue,
                                      IsEmptyCondition, PayloadField)

    conditions: list = [FieldCondition(key="shared", match=MatchValue(value=True))]
    if institution_id:
        conditions.append(FieldCondition(key="institution_id", match=MatchValue(value=institution_id)))

    # Hard cohort boundary: for each dimension, the chunk must be unset (Everyone)
    # OR match the student's value. Unset is matched via IsEmpty so old, unscoped
    # chunks stay visible to everyone without a backfill.
    if scope is not None:
        b = (scope.get("branch") or "").strip().upper()
        s = (scope.get("section") or "").strip().upper()
        y = scope.get("year")
        for key, val in (("scope_branch", b), ("scope_section", s), ("scope_year", y)):
            shoulds: list = [IsEmptyCondition(is_empty=PayloadField(key=key))]
            if key == "scope_year":
                if val not in (None, "", 0):
                    try:
                        shoulds.append(FieldCondition(key=key, match=MatchValue(value=int(val))))
                    except (TypeError, ValueError):
                        pass
            elif val:
                shoulds.append(FieldCondition(key=key, match=MatchValue(value=val)))
            conditions.append(Filter(should=shoulds))

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


def list_document_chunks(user_id: str, source: str, limit: int = 24) -> list[dict[str, Any]]:
    """Fetch a specific user document's chunks BY SOURCE (filename), ordered by
    chunk index — used to force an explicitly attached file into chat context
    without any similarity threshold. Returns up to `limit` chunks from the start."""
    c = _client()
    if not c or not source:
        return []
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    out: list[dict[str, Any]] = []
    try:
        offset = None
        while len(out) < limit:
            points, offset = c.scroll(
                collection_name=COLLECTION_DOCUMENTS,
                scroll_filter=Filter(must=[
                    FieldCondition(key="source", match=MatchValue(value=source)),
                    Filter(should=[
                        FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                        FieldCondition(key="shared", match=MatchValue(value=True)),
                    ]),
                ]),
                with_payload=True, with_vectors=False, limit=64, offset=offset,
            )
            for p in points:
                pl = p.payload or {}
                out.append({"id": str(p.id), "content": pl.get("content", ""),
                            "source": pl.get("source", ""),
                            "chunk_index": pl.get("chunk_index", 0)})
            if offset is None:
                break
    except Exception as e:  # noqa: BLE001
        print(f"[warn] Qdrant list_document_chunks failed: {e}")
        return []
    out.sort(key=lambda x: x.get("chunk_index", 0))
    return out[:limit]


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


def delete_chunks_by_source(user_id: str, source: str, shared: bool = False) -> None:
    """Delete all EXISTING chunks matching this (user, source) — or (source,
    shared) for institution docs — before a re-upload writes fresh ones.

    Without this, re-uploading a file with the same name only ADDS a new
    document_id's worth of chunks on top of whatever was stored the last time.
    `list_document_chunks` (the explicit-attach path) and similarity search both
    match by filename, not document_id, so old chunks — including partial/garbled
    text from a prior failed or lower-quality OCR pass — silently pile up forever
    and get mixed into every future answer's context and citations for that
    filename. Calling this immediately before storing new chunks makes a
    re-upload properly supersede the previous version instead of stacking with
    it."""
    c = _client()
    if not c or not source:
        return
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    try:
        conditions = [FieldCondition(key="source", match=MatchValue(value=source))]
        if shared:
            conditions.append(FieldCondition(key="shared", match=MatchValue(value=True)))
        else:
            conditions.append(FieldCondition(key="user_id", match=MatchValue(value=user_id)))
            conditions.append(FieldCondition(key="shared", match=MatchValue(value=False)))
        c.delete(
            collection_name=COLLECTION_DOCUMENTS,
            points_selector=Filter(must=conditions),
        )
    except Exception as e:
        print(f"[warn] Qdrant delete_chunks_by_source failed: {e}")


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
                pl = p.payload or {}
                src = pl.get("source") or "(untitled)"
                g = grouped.setdefault(src, {
                    "source": src, "chunks": 0, "created_at": None,
                    "scope_branch": pl.get("scope_branch"),
                    "scope_year": pl.get("scope_year"),
                    "scope_section": pl.get("scope_section"),
                })
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


def cache_search_related(
    query_embedding: list[float],
    limit: int = 3,
    min_score: float = 0.72,
) -> list[dict]:
    """Return several RELATED past answers (question + response) above a moderate
    similarity — used to reuse prior knowledge for the overlapping part of a new
    question rather than re-asking the LLM from scratch. Empty list on miss."""
    c = _client()
    if not c:
        return []
    try:
        results = c.search(
            collection_name=COLLECTION_CACHE,
            query_vector=query_embedding,
            limit=limit,
            score_threshold=min_score,
        )
        return [{
            "question": r.payload.get("question", ""),
            "response": r.payload.get("response", ""),
            "score": r.score,
        } for r in results]
    except Exception:
        return []


def cache_store(
    query_embedding: list[float],
    response: str,
    model: str,
    institution_id: str = "ksrmce",
    question: str = "",
) -> None:
    """Store a response in the semantic cache (with the originating question so it
    can be reused for the overlapping part of future, related questions)."""
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
                    "question": question,
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
