"""Direct PostgreSQL client via asyncpg — replaces Supabase client over time.

WHY move from Supabase to direct PostgreSQL:
  1. No vendor lock-in — Supabase wraps Postgres but adds SDK overhead and
     REST-over-HTTP latency for every query
  2. Connection pooling — asyncpg pools connections properly; Supabase client
     creates a new HTTP request per query
  3. Full extension control — pg_trgm, pg_cron, custom functions without
     waiting for Supabase to support them
  4. Cost — Supabase free tier has limits (500MB, 2 connections); self-hosted
     PG has no limits

MIGRATION STRATEGY:
  The existing supabase_client.py stays working during the transition. New code
  should use this module. Old code is migrated gradually (one router at a time).
  Both clients can coexist because they connect to the same schema.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.config import get_settings

_pool = None  # Will be set during app startup


async def init_pool() -> None:
    """Initialize the asyncpg connection pool. Call once during FastAPI startup."""
    global _pool
    settings = get_settings()
    if not settings.database_url:
        print("[warn] DATABASE_URL not set, postgres_client disabled")
        return
    try:
        import asyncpg
        # asyncpg needs the raw postgres:// URL (not postgresql+asyncpg://)
        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        _pool = await asyncpg.create_pool(
            dsn,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        print("[ok] PostgreSQL pool initialized")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] PostgreSQL pool init failed: {e}")


async def close_pool() -> None:
    """Close the pool on shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def available() -> bool:
    return _pool is not None


# === Query Helpers ===========================================================

async def fetch(query: str, *args) -> list[dict[str, Any]]:
    """Execute a SELECT and return rows as list of dicts."""
    if not _pool:
        return []
    rows = await _pool.fetch(query, *args)
    return [dict(r) for r in rows]


async def fetchrow(query: str, *args) -> dict[str, Any] | None:
    """Execute a SELECT and return a single row as dict, or None."""
    if not _pool:
        return None
    row = await _pool.fetchrow(query, *args)
    return dict(row) if row else None


async def fetchval(query: str, *args) -> Any:
    """Execute a SELECT and return a single scalar value."""
    if not _pool:
        return None
    return await _pool.fetchval(query, *args)


async def execute(query: str, *args) -> str:
    """Execute a write query (INSERT, UPDATE, DELETE). Returns status string."""
    if not _pool:
        return "no_pool"
    return await _pool.execute(query, *args)


async def executemany(query: str, args: list) -> None:
    """Execute a write query with multiple parameter sets (batch insert)."""
    if not _pool:
        return
    await _pool.executemany(query, args)


# === Transaction Helper ======================================================

class transaction:
    """Async context manager for transactions.

    Usage:
        async with postgres_client.transaction() as conn:
            await conn.execute("INSERT ...")
            await conn.execute("UPDATE ...")
    """
    async def __aenter__(self):
        if not _pool:
            raise RuntimeError("PostgreSQL pool not initialized")
        self._conn = await _pool.acquire()
        self._tx = self._conn.transaction()
        await self._tx.start()
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        try:
            if exc_type:
                await self._tx.rollback()
            else:
                await self._tx.commit()
        finally:
            await _pool.release(self._conn)


# === Convenience: User Operations (mirrors supabase_client.py signatures) ====

async def get_user_by_id(user_id: str) -> dict | None:
    return await fetchrow(
        "SELECT * FROM app_users WHERE id = $1", user_id
    )


async def get_user_by_email(email: str) -> dict | None:
    return await fetchrow(
        "SELECT * FROM app_users WHERE email = $1", email
    )


async def log_usage(user_id: str, model: str, prompt_tokens: int,
                    completion_tokens: int, cost_usd: float) -> None:
    await execute(
        "INSERT INTO usage_log (user_id, model, prompt_tokens, completion_tokens, cost_usd) "
        "VALUES ($1, $2, $3, $4, $5)",
        user_id, model, prompt_tokens, completion_tokens, cost_usd,
    )


async def increment_user_tokens(user_id: str, tokens: int) -> None:
    await execute(
        "UPDATE app_users SET used_tokens = used_tokens + $2, daily_used = daily_used + $2 "
        "WHERE id = $1",
        user_id, tokens,
    )


# === Health ==================================================================

async def health() -> dict:
    if not _pool:
        return {"status": "not_configured"}
    try:
        version = await fetchval("SELECT version()")
        size = await fetchval(
            "SELECT pg_size_pretty(pg_database_size(current_database()))"
        )
        return {"status": "ok", "version": version, "size": size,
                "pool_size": _pool.get_size(), "pool_free": _pool.get_idle_size()}
    except Exception as e:
        return {"status": "error", "error": str(e)}
