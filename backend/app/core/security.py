"""Password hashing + JWT issue/verify + FastAPI auth dependencies."""
from __future__ import annotations

import asyncio
import time

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
_pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)


def hash_password(raw: str) -> str:
    return _pwd.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return _pwd.verify(raw, hashed)
    except Exception:
        return False


async def verify_password_async(raw: str, hashed: str) -> bool:
    """Run the CPU-bound password verification in a thread pool so it doesn't
    block the async event loop (prevents stalling all concurrent requests)."""
    return await asyncio.to_thread(verify_password, raw, hashed)


def create_access_token(user_id: str, role: str, token_version: int = 0) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "role": role,
        "tv": int(token_version),   # revocation epoch; checked in current_user
        "iat": now,
        "exp": now + settings.access_token_ttl_min * 60,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


# --- Token revocation kill-switch -------------------------------------------
# A user's current token_version is the source of truth in Postgres, hot-cached
# in Redis (and a tiny in-process TTL cache as a Redis-down fallback) so the
# per-request check stays ~O(1) and never hammers the DB.
_tv_cache: dict[str, tuple[int, float]] = {}
_TV_LOCAL_TTL = 60       # seconds — max revocation delay if Redis is unavailable
_TV_REDIS_TTL = 300


def current_token_version(user_id: str) -> int:
    from app.db import redis_client
    cached = redis_client.cache_get("tv", user_id)
    if cached is not None:
        try:
            return int(cached)
        except (TypeError, ValueError):
            pass
    ent = _tv_cache.get(user_id)
    nowt = time.time()
    if ent and nowt - ent[1] < _TV_LOCAL_TTL:
        return ent[0]
    from app.db import supabase_client as db
    try:
        v = db.get_token_version(user_id)
    except Exception:
        # Never lock everyone out if the DB read fails — treat as version 0.
        v = ent[0] if ent else 0
    redis_client.cache_set("tv", user_id, str(v), _TV_REDIS_TTL)
    _tv_cache[user_id] = (v, nowt)
    return v


def bump_token_version(user_id: str) -> int:
    """Revoke ALL of a user's outstanding tokens immediately."""
    from app.db import redis_client
    from app.db import supabase_client as db
    v = db.bump_token_version(user_id)
    redis_client.cache_set("tv", user_id, str(v), _TV_REDIS_TTL)
    _tv_cache[user_id] = (v, time.time())
    return v


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")


async def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Returns the decoded claims {sub, role}. Raises 401 if missing/invalid."""
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    claims = decode_token(creds.credentials)
    user_id = claims["sub"]
    # Revocation check: a token minted before the user's current version (logout /
    # password reset / suspend bumps it) is rejected even though it hasn't expired.
    if int(claims.get("tv", 0)) < current_token_version(user_id):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Session ended. Please log in again.")
    return {"user_id": user_id, "role": claims.get("role", "student")}


async def require_admin(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user
