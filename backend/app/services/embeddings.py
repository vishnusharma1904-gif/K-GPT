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
        response = httpx.post(
            _API_URL,
            headers={
                "Authorization": f"Bearer {settings.fireworks_api_key}",
                "Content-Type": "application/json",
            },
            json={"model": _MODEL_NAME, "input": [text], "dimensions": _DIM},
            timeout=10.0,
        )
        response.raise_for_status()
        embedding = response.json()["data"][0]["embedding"]
        if len(embedding) == _DIM:
            redis_client.cache_set_json(_CACHE_PREFIX, text, embedding, _CACHE_TTL)
        return embedding
    except Exception as e:
        print(f"[warn] Fireworks embedding failed, using zero vector: {e}")
        return [0.0] * _DIM


def warm() -> None:
    """Pre-load the model. (No-op since we are using a remote API)."""
    pass
