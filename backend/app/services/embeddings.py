"""API-based embeddings (Qwen3-Embedding-8B) via Fireworks AI.

Uses the Qwen3 embedding model and asks Fireworks for 768-dim output via the
`dimensions` parameter (the model's native size is 4096, but it supports
Matryoshka truncation down to any size). 768 keeps vectors compatible with the
existing Qdrant collections and the Supabase pgvector schema — and stays under
pgvector's 2000-dim index limit.

Shifted from local CPU embeddings to a hosted API to save RAM and dramatically
increase concurrent throughput. Results are cached in Redis (keyed by a hash of
the text) so repeated embeds of the same string skip the network round-trip.
The cache degrades to a no-op when Redis is off.
"""
from __future__ import annotations

import httpx

from app.core.config import get_settings

_MODEL_NAME = "accounts/fireworks/models/qwen3-embedding-8b"
_DIM = 768  # requested via the `dimensions` param (Matryoshka); must match the vector store
_API_URL = "https://api.fireworks.ai/inference/v1/embeddings"
_CACHE_PREFIX = "emb"
_CACHE_TTL = 7 * 24 * 3600  # a week — embeddings are deterministic for a model
_BATCH_SIZE = 64  # texts per Fireworks request (keeps the payload well under limits)
_ZERO = [0.0] * _DIM


def _post(inputs: list[str], timeout: float) -> list[list[float]]:
    """One Fireworks embeddings call for a list of inputs. Raises on failure."""
    settings = get_settings()
    response = httpx.post(
        _API_URL,
        headers={
            "Authorization": f"Bearer {settings.fireworks_api_key}",
            "Content-Type": "application/json",
        },
        json={"model": _MODEL_NAME, "input": inputs, "dimensions": _DIM},
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()["data"]
    # The API may return items out of order — sort by the `index` it echoes back.
    data = sorted(data, key=lambda d: d.get("index", 0))
    return [d["embedding"] for d in data]


def embed(text: str) -> list[float]:
    """Return a 768-dim embedding via Fireworks API.

    On any failure (missing key, empty text, network error) a zero vector is
    returned so callers can still persist the text — semantic recall is skipped,
    but the always-on profile and document storage don't need the vector.
    """
    settings = get_settings()

    if not text or not text.strip() or not settings.fireworks_api_key:
        if text and text.strip() and not settings.fireworks_api_key:
            print("[warn] FIREWORKS_API_KEY is not set. Using zero vector for embedding.")
        return [0.0] * _DIM

    # --- Redis cache lookup (best-effort) ---
    from app.db import redis_client
    cached = redis_client.cache_get_json(_CACHE_PREFIX, text)
    if isinstance(cached, list) and len(cached) == _DIM:
        return cached

    try:
        embedding = _post([text], timeout=10.0)[0]
        if len(embedding) == _DIM:
            redis_client.cache_set_json(_CACHE_PREFIX, text, embedding, _CACHE_TTL)
        return embedding
    except Exception as e:
        print(f"[warn] Fireworks embedding failed, using zero vector: {e}")
        return list(_ZERO)


def embed_many(texts: list[str]) -> list[list[float]]:
    """Embed many texts with the fewest possible network round-trips.

    Cache hits are served from Redis; only the misses are sent to Fireworks, and
    those go out in batches of ``_BATCH_SIZE`` per request instead of one call
    per chunk. This is the big win for large uploads — ingesting a 120-chunk PDF
    drops from 120 sequential calls to ~2. Order is preserved and any failure
    degrades to a zero vector for the affected items (so storage still succeeds).
    """
    if not texts:
        return []

    settings = get_settings()
    results: list[list[float] | None] = [None] * len(texts)

    from app.db import redis_client
    # 1) Resolve from cache; collect the indices that still need embedding.
    misses: list[int] = []
    for i, t in enumerate(texts):
        if not t or not t.strip():
            results[i] = list(_ZERO)
            continue
        cached = redis_client.cache_get_json(_CACHE_PREFIX, t)
        if isinstance(cached, list) and len(cached) == _DIM:
            results[i] = cached
        else:
            misses.append(i)

    if misses and not settings.fireworks_api_key:
        print("[warn] FIREWORKS_API_KEY is not set. Using zero vectors for embeddings.")
        for i in misses:
            results[i] = list(_ZERO)
        misses = []

    # 2) Embed the misses in batches, one network call per batch.
    for start in range(0, len(misses), _BATCH_SIZE):
        batch_idx = misses[start:start + _BATCH_SIZE]
        inputs = [texts[i] for i in batch_idx]
        try:
            vectors = _post(inputs, timeout=30.0)
            if len(vectors) != len(inputs):
                raise ValueError(
                    f"embedding count mismatch ({len(vectors)} != {len(inputs)})")
            for i, vec in zip(batch_idx, vectors):
                results[i] = vec
                if len(vec) == _DIM:
                    redis_client.cache_set_json(_CACHE_PREFIX, texts[i], vec, _CACHE_TTL)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] Fireworks batch embedding failed, using zero vectors: {e}")
            for i in batch_idx:
                results[i] = list(_ZERO)

    return [r if r is not None else list(_ZERO) for r in results]


def warm() -> None:
    """Pre-load the model. (No-op since we are using a remote API)."""
    pass
