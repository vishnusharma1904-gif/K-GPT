"""College SSO — Google Workspace (P3).

Uses Google Identity Services: the frontend renders the Google button and sends
the resulting **ID token** (a JWT) here. We verify it against Google's tokeninfo
endpoint, enforce the hosted-domain (`ksrmce.ac.in`) restriction, then link or
create the `app_users` row and issue our own JWT. No password, no redirect dance,
and no extra Python dependency (httpx is already used).

Non-college Google accounts are rejected (admins in ADMIN_EMAILS are exempt).
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.security import create_access_token
from app.db import supabase_client as db

settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["auth"])

_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"


class GoogleAuthReq(BaseModel):
    credential: str   # Google ID token (JWT) from the GIS button


def _public(u: dict) -> dict:
    return {k: u.get(k) for k in (
        "id", "email", "full_name", "roll_no", "role", "sub_status",
        "sub_expires_at", "email_verified", "tier", "exam_mode",
        "response_style", "avatar_url", "auth_provider",
    )}


def _roll_from_email(email: str) -> str | None:
    local = email.split("@", 1)[0]
    return local.upper() if any(c.isdigit() for c in local) else None


@router.get("/google/config")
async def google_config():
    """Expose the client id so the frontend can render the button (or hide it)."""
    return {"enabled": bool(settings.google_client_id),
            "client_id": settings.google_client_id,
            "hosted_domain": settings.allowed_email_domain}


@router.post("/google")
async def google_login(req: GoogleAuthReq):
    if not settings.google_client_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Google sign-in is not configured.")
    # Verify the ID token with Google.
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(_TOKENINFO, params={"id_token": req.credential})
        if r.status_code != 200:
            raise ValueError("token rejected")
        info = r.json()
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Google token.")

    # Audience must be our client id; email must be verified.
    if info.get("aud") != settings.google_client_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token audience mismatch.")
    if info.get("email_verified") not in ("true", True):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google email not verified.")

    email = (info.get("email") or "").lower()
    sub = info.get("sub")
    domain = email.split("@", 1)[1] if "@" in email else ""
    is_admin = email in settings.admin_set
    hd_ok = (info.get("hd") == settings.allowed_email_domain
             or domain == settings.allowed_email_domain)
    if not is_admin and not hd_ok:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Use your @{settings.allowed_email_domain} college Google account.")

    # Link by provider sub, else by email, else create.
    user = db.get_user_by_provider_sub("google", sub) or db.get_user_by_email(email)
    if user:
        patch = {"auth_provider": "google", "provider_sub": sub,
                 "email_verified": True}
        if info.get("picture"):
            patch["avatar_url"] = info["picture"]
        user = db.update_user(user["id"], patch)
    else:
        user = db.create_user({
            "email": email,
            "full_name": info.get("name") or email.split("@")[0],
            "roll_no": _roll_from_email(email),
            "password_hash": "",                     # SSO-only account
            "role": "admin" if is_admin else "student",
            "sub_status": "active" if is_admin else "inactive",
            "email_verified": True,
            "auth_provider": "google",
            "provider_sub": sub,
            "avatar_url": info.get("picture"),
            "quota_tokens": settings.default_quota_tokens,
            "daily_msg_limit": settings.default_daily_msgs,
        })

    token = create_access_token(user["id"], user["role"])
    return {"access_token": token, "token_type": "bearer", "user": _public(user)}
