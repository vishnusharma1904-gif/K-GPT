"""Local CPU embeddings (SentenceTransformers MiniLM, 384-dim) for per-user RAG.

Lazy-loaded and pre-warmed at startup. The model cache is pinned to a local
folder next to the backend so a stray HF_HOME (e.g. pointing at a non-existent
drive) can't break it, and embedding failures degrade gracefully to a zero
vector so memory text is still persisted (the always-on profile doesn't need the
vector, only semantic recall does).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_DIM = 384
# backend/.hfcache  (this file is backend/app/services/embeddings.py)
_CACHE = str(Path(__file__).resolve().parents[2] / ".hfcache")


@lru_cache
def _model():
    # Force all HF/sentence-transformers caches to a local, definitely-existing
    # folder BEFORE importing, so a bad HF_HOME (e.g. 'E:\\') can't be used.
    Path(_CACHE).mkdir(parents=True, exist_ok=True)
    for var in ("HF_HOME", "HUGGINGFACE_HUB_CACHE", "TRANSFORMERS_CACHE",
                "SENTENCE_TRANSFORMERS_HOME"):
        os.environ[var] = _CACHE
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(_MODEL_NAME, cache_folder=_CACHE)


def embed(text: str) -> list[float]:
    """Return a 384-dim embedding. On any failure, return a zero vector so the
    caller can still persist the text (semantic recall is skipped, profile isn't)."""
    try:
        return _model().encode(text, normalize_embeddings=True).tolist()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] embedding failed, using zero vector: {e}")
        return [0.0] * _DIM


def warm() -> None:
    """Pre-load the model so the first real request doesn't pay the cold start."""
    try:
        _model().encode("warmup")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] embedding warmup skipped: {e}")
