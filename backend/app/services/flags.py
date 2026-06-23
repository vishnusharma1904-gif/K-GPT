"""Feature flags (P4).

A thin, cached wrapper over the ``feature_flags`` table so request paths can ask
``flags.is_enabled("voice")`` cheaply. Flags are admin-toggleable; the cache has
a short TTL so changes take effect within a minute without a restart. Falls back
to a safe default when the DB is unavailable (dev / tests).
"""
from __future__ import annotations

import time

from app.db import supabase_client as db

_CACHE: dict[str, bool] = {}
_FETCHED_AT: float = 0.0
_TTL = 60.0  # seconds


def _refresh() -> None:
    global _CACHE, _FETCHED_AT
    try:
        rows = db.list_feature_flags()
        _CACHE = {r["key"]: bool(r.get("enabled")) for r in rows}
        _FETCHED_AT = time.time()
    except Exception:
        # leave stale cache in place on failure
        _FETCHED_AT = time.time()


def is_enabled(key: str, default: bool = False) -> bool:
    if time.time() - _FETCHED_AT > _TTL:
        _refresh()
    return _CACHE.get(key, default)


def invalidate() -> None:
    global _FETCHED_AT
    _FETCHED_AT = 0.0
