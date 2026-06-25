"""Redis client — caching, rate limiting, shared state.

Follows the same pattern as supabase_client.py: module-level singleton via
@lru_cache, thin wrapper functions the rest of the codebase calls.

WHY Redis:
  1. Response caching — identical/similar queries return cached answers (saves LLM $)
  2. Embedding caching — skip re-embedding the same text (saves CPU)
  3. Rate limiting — fairuse.py currently uses process-local dicts; with 2+ backend
     replicas those dicts diverge, letting users exceed limits. Redis is shared.
  4. Circuit breaker state — smart_router.py _fail_counts/_open_until are in-memory;
     Redis makes them consistent across replicas.
  5. Session memory — ephemeral key-value store for Layer 1 of the memory system.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from typing import Any

from app.core.config import get_settings


@lru_cache
def _pool():
    """Lazy Redis connection pool. Returns None if Redis is not configured,
    so the app degrades gracefully to in-memory fallbacks."""
    settings = get_settings()
    if not settings.redis_url:
        return None
    try:
        import redis
        return redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,       # strings, not bytes
            socket_connect_timeout=3,
            socket_timeout=2,
            retry_on_timeout=True,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[warn] Redis not available: {e}")
        return None


def available() -> bool:
    """Check if Redis is connected and responding."""
    r = _pool()
    if not r:
        return False
    try:
        return r.ping()
    except Exception:
        return False


def configured() -> bool:
    """Whether a Redis URL is set (used to decide if cross-process coordination
    like the scheduler leader lock is even possible)."""
    return bool(get_settings().redis_url)


# === Distributed leader lock ===============================================

def try_acquire_lock(name: str, ttl_seconds: int = 900) -> bool:
    """Best-effort distributed lock via SET NX EX. Returns True only for the
    single caller that wins the lock; False for everyone else (and when Redis is
    unavailable, since coordination isn't possible). Holders should periodically
    call ``refresh_lock`` so leadership survives but is reclaimable if they die."""
    r = _pool()
    if not r:
        return False
    try:
        return bool(r.set(f"lock:{name}", "1", nx=True, ex=ttl_seconds))
    except Exception:
        return False


def refresh_lock(name: str, ttl_seconds: int = 900) -> None:
    """Extend a held leader lock's TTL. Fails silently."""
    r = _pool()
    if not r:
        return
    try:
        r.expire(f"lock:{name}", ttl_seconds)
    except Exception:
        pass


# === Caching ================================================================

def _cache_key(prefix: str, text: str) -> str:
    return f"{prefix}:{hashlib.sha256(text.encode()).hexdigest()[:24]}"


def cache_get(prefix: str, key_text: str) -> str | None:
    """Get a cached value by (prefix, text). Returns None on miss or error."""
    r = _pool()
    if not r:
        return None
    try:
        return r.get(_cache_key(prefix, key_text))
    except Exception:
        return None


def cache_set(prefix: str, key_text: str, value: str, ttl_seconds: int = 3600) -> None:
    """Store a value in cache with TTL. Fails silently."""
    r = _pool()
    if not r:
        return
    try:
        r.setex(_cache_key(prefix, key_text), ttl_seconds, value)
    except Exception:
        pass


def cache_get_json(prefix: str, key_text: str) -> Any | None:
    """Get a cached JSON value, deserialized."""
    raw = cache_get(prefix, key_text)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def cache_set_json(prefix: str, key_text: str, value: Any, ttl_seconds: int = 3600) -> None:
    """Store a JSON-serializable value in cache."""
    try:
        cache_set(prefix, key_text, json.dumps(value, default=str), ttl_seconds)
    except Exception:
        pass


# === Rate Limiting (replaces fairuse.py in-memory counters) =================

def rate_check(user_id: str, window_key: str, limit: int, window_seconds: int = 60) -> bool:
    """Increment a sliding-window counter. Returns True if UNDER the limit."""
    r = _pool()
    if not r:
        return True  # degrade open (allow) if Redis is down
    key = f"rate:{user_id}:{window_key}"
    try:
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds)
        results = pipe.execute()
        return results[0] <= limit
    except Exception:
        return True  # degrade open


def rate_current(user_id: str, window_key: str) -> int:
    """Current count for a rate window. 0 if Redis unavailable."""
    r = _pool()
    if not r:
        return 0
    try:
        val = r.get(f"rate:{user_id}:{window_key}")
        return int(val) if val else 0
    except Exception:
        return 0


def incr_by(user_id: str, window_key: str, amount: int, window_seconds: int) -> int:
    """Add `amount` to a counter and (re)set its TTL atomically. Returns the new
    total, or 0 if Redis is unavailable. Used for token accounting where each
    request adds a weighted token count rather than a single hit."""
    r = _pool()
    if not r or amount <= 0:
        return 0
    key = f"rate:{user_id}:{window_key}"
    try:
        pipe = r.pipeline()
        pipe.incrby(key, amount)
        pipe.expire(key, window_seconds)
        results = pipe.execute()
        return int(results[0])
    except Exception:
        return 0


# === Circuit Breaker (replaces smart_router.py in-memory state) =============

def circuit_trip(model: str, cooldown_seconds: int = 120) -> None:
    """Mark a model's circuit as open (tripped)."""
    r = _pool()
    if not r:
        return
    try:
        r.setex(f"circuit:{model}", cooldown_seconds, "open")
    except Exception:
        pass


def circuit_is_open(model: str) -> bool:
    """Check if a model's circuit breaker is tripped. False if Redis unavailable."""
    r = _pool()
    if not r:
        return False
    try:
        return r.exists(f"circuit:{model}") > 0
    except Exception:
        return False


def list_open_circuits() -> list[str]:
    """Return the model ids whose circuit is currently tripped. Empty if Redis
    is unavailable. Used by smart_router.health()."""
    r = _pool()
    if not r:
        return []
    try:
        return [k.split("circuit:", 1)[1] for k in r.scan_iter(match="circuit:*")]
    except Exception:
        return []


def circuit_reset(model: str) -> None:
    """Manually close a circuit breaker."""
    r = _pool()
    if not r:
        return
    try:
        r.delete(f"circuit:{model}")
    except Exception:
        pass


# === Concurrency Tracking ===================================================

def concurrency_acquire(user_id: str, max_concurrent: int = 3, ttl: int = 30) -> bool:
    """Try to acquire a concurrency slot. Returns True if allowed."""
    r = _pool()
    if not r:
        return True
    key = f"conc:{user_id}"
    try:
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl)
        results = pipe.execute()
        return results[0] <= max_concurrent
    except Exception:
        return True


def concurrency_release(user_id: str) -> None:
    """Release a concurrency slot."""
    r = _pool()
    if not r:
        return
    key = f"conc:{user_id}"
    try:
        r.decr(key)
    except Exception:
        pass


# === Session Memory (Layer 1 — ephemeral, per-conversation) =================

def session_memory_set(session_id: str, data: dict, ttl: int = 7200) -> None:
    """Store session memory (ephemeral working context). TTL = 2 hours default."""
    r = _pool()
    if not r:
        return
    try:
        r.setex(f"session:{session_id}", ttl, json.dumps(data, default=str))
    except Exception:
        pass


def session_memory_get(session_id: str) -> dict | None:
    """Retrieve session memory."""
    r = _pool()
    if not r:
        return None
    try:
        raw = r.get(f"session:{session_id}")
        return json.loads(raw) if raw else None
    except Exception:
        return None


# === Health ==================================================================

def health() -> dict:
    """Health check info for /api/health."""
    r = _pool()
    if not r:
        return {"status": "not_configured"}
    try:
        info = r.info(section="memory")
        return {
            "status": "ok",
            "used_memory_human": info.get("used_memory_human", "?"),
            "connected_clients": r.info(section="clients").get("connected_clients", 0),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
