"""Password hashing + JWT issue/verify + FastAPI auth dependencies."""
from __future__ import annotations

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


def create_access_token(user_id: str, role: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + settings.access_token_ttl_min * 60,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


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
    return {"user_id": claims["sub"], "role": claims.get("role", "student")}


async def require_admin(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user
