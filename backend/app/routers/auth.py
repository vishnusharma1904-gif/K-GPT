"""Signup / login — college-gated, with email verification, password reset,
and brute-force lockout (P2)."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import get_settings
from app.core.security import (create_access_token, current_user, hash_password,
                               verify_password)
from app.db import supabase_client as db
from app.schemas import (AuthResp, ForgotReq, LoginReq, ResendOtpReq, ResetReq,
                         SignupReq, TokenResp, VerifyOtpReq, VerifyReq)
from app.services import mailer

settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _public(u: dict) -> dict:
    from app.services import cohort, safety
    data = {k: u.get(k) for k in (
        "id", "email", "full_name", "roll_no", "role", "sub_status",
        "sub_expires_at", "quota_tokens", "used_tokens", "email_verified",
        "tier", "exam_mode", "response_style", "plan",
        "course", "branch", "section", "admission_year", "department",
    )}
    # Year + semester are DERIVED from admission_year so they advance with time.
    data["year"], data["semester"] = cohort.derive(u.get("admission_year"), u.get("course"))
    # Whether the user has filled the mandatory profile (admins exempt; faculty
    # use a different required set — department instead of cohort).
    role = u.get("role")
    if role in ("admin",):
        complete = True
    elif role == "faculty":
        complete = all(u.get(k) not in (None, "") for k in ("full_name", "department"))
    else:
        _required = ("full_name", "roll_no", "course", "branch", "admission_year", "section")
        complete = all(u.get(k) not in (None, "") for k in _required)
    data["profile_complete"] = complete
    data["monitored"] = safety.is_monitored(u)
    return data


def _roll_from_email(email: str) -> str | None:
    local = email.split("@", 1)[0]
    return local.upper() if any(c.isdigit() for c in local) else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _issue_token(user_id: str, kind: str) -> str:
    raw = secrets.token_urlsafe(24)
    expires = (_now() + timedelta(hours=settings.token_ttl_hours)).isoformat()
    db.insert_auth_token(user_id, kind, _hash_token(raw), expires)
    return raw


def _issue_otp(user_id: str) -> str:
    """Generate a 6-digit email OTP, store its hash with a short TTL, return the
    plain code (to be emailed — never stored in clear)."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = (_now() + timedelta(minutes=settings.otp_ttl_minutes)).isoformat()
    db.insert_auth_token(user_id, "otp", _hash_token(code), expires)
    return code


def _send_signup_otp(user: dict) -> None:
    code = _issue_otp(user["id"])
    mailer.send_otp(user["email"], code, settings.otp_ttl_minutes)


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


@router.post("/signup", response_model=AuthResp)
async def signup(req: SignupReq):
    email = req.email.lower()
    domain = email.split("@", 1)[1]
    is_admin = email in settings.admin_set
    if not is_admin and domain != settings.allowed_email_domain:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Sign up with your @{settings.allowed_email_domain} college email.",
        )
    if db.get_user_by_email(email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Account already exists. Please log in.")

    user = db.create_user({
        "email": email,
        "full_name": req.full_name.strip(),
        "roll_no": _roll_from_email(email),
        "password_hash": hash_password(req.password),
        "role": "admin" if is_admin else "student",
        "sub_status": "active" if is_admin else "inactive",
        "email_verified": is_admin,   # admins are trusted by config
        "quota_tokens": settings.default_quota_tokens,
        "daily_msg_limit": settings.default_daily_msgs,
    })

    # Mandatory email-OTP verification for every new (non-admin) user. No access
    # token is issued until the OTP is confirmed via /verify-otp.
    if not is_admin:
        _send_signup_otp(user)
        return AuthResp(otp_required=True, email=email)

    token = create_access_token(user["id"], user["role"])
    return AuthResp(access_token=token, user=_public(user))


@router.post("/login", response_model=AuthResp)
async def login(req: LoginReq):
    user = db.get_user_by_email(req.email.lower())
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")

    locked = _dt(user.get("locked_until"))
    if locked and locked > _now():
        mins = int((locked - _now()).total_seconds() // 60) + 1
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Too many attempts. Try again in {mins} minute(s).")

    if not verify_password(req.password, user["password_hash"]):
        fails = (user.get("failed_logins") or 0) + 1
        patch: dict = {"failed_logins": fails}
        if fails >= settings.max_failed_logins:
            patch["locked_until"] = (_now() + timedelta(minutes=settings.lockout_minutes)).isoformat()
            patch["failed_logins"] = 0
        db.update_user(user["id"], patch)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")

    if user.get("failed_logins"):
        db.update_user(user["id"], {"failed_logins": 0, "locked_until": None})

    # Mandatory verification gate: an unverified account can't get a session —
    # re-issue an OTP and route them to the verification screen instead.
    if not user.get("email_verified") and user.get("role") != "admin":
        _send_signup_otp(user)
        return AuthResp(otp_required=True, email=user["email"])

    token = create_access_token(user["id"], user["role"])
    return AuthResp(access_token=token, user=_public(user))


@router.post("/verify-otp", response_model=TokenResp)
async def verify_otp(req: VerifyOtpReq):
    user = db.get_user_by_email(req.email.lower())
    if not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid code.")
    if user.get("email_verified"):
        token = create_access_token(user["id"], user["role"])
        return TokenResp(access_token=token, user=_public(user))

    code = (req.code or "").strip()
    row = db.get_auth_token_for_user(user["id"], _hash_token(code), "otp")
    if not row or _dt(row["expires_at"]) < _now():
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Invalid or expired code. Request a new one.")

    db.consume_auth_token(row["id"])
    db.update_user(user["id"], {"email_verified": True})
    user["email_verified"] = True
    token = create_access_token(user["id"], user["role"])
    return TokenResp(access_token=token, user=_public(user))


@router.post("/resend-otp")
async def resend_otp(req: ResendOtpReq):
    user = db.get_user_by_email(req.email.lower())
    # Never reveal whether the account exists / is already verified.
    if user and not user.get("email_verified"):
        _send_signup_otp(user)
    return {"ok": True}


@router.get("/me")
async def me(claims: dict = Depends(current_user)):
    user = db.get_user(claims["user_id"])
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return _public(user)


# --- Email verification -----------------------------------------------------
@router.post("/verify")
async def verify_email(req: VerifyReq):
    row = db.get_auth_token(_hash_token(req.token), "verify")
    if not row or _dt(row["expires_at"]) < _now():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired link.")
    db.consume_auth_token(row["id"])
    db.update_user(row["user_id"], {"email_verified": True})
    return {"ok": True, "email_verified": True}


@router.post("/resend-verification")
async def resend_verification(claims: dict = Depends(current_user)):
    user = db.get_user(claims["user_id"])
    if not user or user.get("email_verified"):
        return {"ok": True}
    raw = _issue_token(user["id"], "verify")
    link = f"{settings.frontend_url}/verify?token={raw}"
    mailer.send_verification(user["email"], link)
    return {"ok": True}


# --- Password reset ---------------------------------------------------------
@router.post("/forgot")
async def forgot(req: ForgotReq):
    user = db.get_user_by_email(req.email.lower())
    # Always return ok — never reveal whether an email exists.
    if user:
        raw = _issue_token(user["id"], "reset")
        link = f"{settings.frontend_url}/reset?token={raw}"
        mailer.send_reset(user["email"], link)
    return {"ok": True}


@router.post("/reset")
async def reset(req: ResetReq):
    row = db.get_auth_token(_hash_token(req.token), "reset")
    if not row or _dt(row["expires_at"]) < _now():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired link.")
    db.consume_auth_token(row["id"])
    db.update_user(row["user_id"],
                   {"password_hash": hash_password(req.password),
                    "failed_logins": 0, "locked_until": None})
    return {"ok": True}
