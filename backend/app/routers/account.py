"""Account self-service — profile, %-only usage, weekly-bonus, preferences,
privacy (export / delete), billing history (P12 / P25 / P31 / P40 / P41 / P17)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import current_user
from app.db import supabase_client as db
from app.schemas import PrefsReq
from app.services import cohort, entitlements, prompting

router = APIRouter(prefix="/api/account", tags=["account"])

_VALID_STYLES = set(prompting.STYLES.keys())

# Fields a (non-admin) student must fill before using K-GPT. Year/semester are
# DERIVED from admission_year + the calendar, so they are not collected directly.
_REQUIRED_PROFILE = ("full_name", "roll_no", "course", "branch", "admission_year", "section")


def profile_complete(u: dict) -> bool:
    if u.get("role") == "admin":
        return True
    return all(u.get(k) not in (None, "") for k in _REQUIRED_PROFILE)


@router.get("/usage")
async def usage(claims: dict = Depends(current_user)):
    """Returns PERCENTAGE + state only — never a raw token count."""
    user = db.get_user(claims["user_id"])
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user = entitlements.refresh(user)
    return entitlements.usage_view(user)


@router.post("/claim-bonus")
async def claim_bonus(claims: dict = Depends(current_user)):
    user = db.get_user(claims["user_id"])
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return entitlements.claim_weekly_bonus(user)


# --- Preferences: custom instructions / style / exam mode / memory (P25/P31/P40)
@router.get("/preferences")
async def get_prefs(claims: dict = Depends(current_user)):
    u = db.get_user(claims["user_id"]) or {}
    cy, cs = cohort.derive(u.get("admission_year"), u.get("course"))
    return {
        "response_style": u.get("response_style", "balanced"),
        "custom_instructions": u.get("custom_instructions"),
        "exam_mode": bool(u.get("exam_mode")),
        "memory_enabled": bool(u.get("memory_enabled", True)),
        "web_search_enabled": bool(u.get("web_search_enabled")),
        "full_name": u.get("full_name"),
        "roll_no": u.get("roll_no"),
        "course": u.get("course"),
        "branch": u.get("branch"),
        "section": u.get("section"),
        "admission_year": u.get("admission_year"),
        "year": cy,
        "semester": cs,
        "profile_complete": profile_complete(u),
        "styles": sorted(_VALID_STYLES),
    }


@router.patch("/preferences")
async def set_prefs(req: PrefsReq, claims: dict = Depends(current_user)):
    patch: dict = {}
    if req.response_style is not None:
        if req.response_style not in _VALID_STYLES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown response style.")
        patch["response_style"] = req.response_style
    if req.custom_instructions is not None:
        patch["custom_instructions"] = req.custom_instructions.strip() or None
    if req.exam_mode is not None:
        patch["exam_mode"] = req.exam_mode
    if req.memory_enabled is not None:
        patch["memory_enabled"] = req.memory_enabled
    if req.web_search_enabled is not None:
        patch["web_search_enabled"] = req.web_search_enabled
    # Academic/identity fields: a student may set each ONCE (during onboarding),
    # after which it is locked — only an admin can change it (students contact the
    # admin). So we only accept a value here when the field is currently empty.
    u = db.get_user(claims["user_id"]) or {}
    if req.full_name is not None and not u.get("full_name"):
        patch["full_name"] = req.full_name.strip() or None
    if req.roll_no is not None and not u.get("roll_no"):
        patch["roll_no"] = (req.roll_no.strip().upper() or None)
    if req.course is not None and not u.get("course"):
        patch["course"] = req.course.strip() or None
    if req.branch is not None and not u.get("branch"):
        patch["branch"] = (req.branch.strip().upper() or None)
    if req.admission_year is not None and not u.get("admission_year"):
        patch["admission_year"] = req.admission_year
    if req.section is not None and not u.get("section"):
        patch["section"] = (req.section.strip().upper() or None)
    if patch:
        updated = db.update_user(claims["user_id"], patch)
    else:
        updated = db.get_user(claims["user_id"]) or {}
    return {"ok": True, "profile_complete": profile_complete(updated), **patch}


# --- Billing history (P17) --------------------------------------------------
@router.get("/payments")
async def payments(claims: dict = Depends(current_user)):
    rows = db.list_payments(claims["user_id"])
    # Present rupees, not paise; never expose internal ids beyond receipt no.
    return [{
        "receipt_no": r.get("receipt_no"),
        "amount_inr": round((r.get("amount_inr") or 0) / 100, 2),
        "gst_inr": round((r.get("gst_inr") or 0) / 100, 2),
        "status": r.get("status"), "plan": r.get("plan"),
        "expires_at": r.get("expires_at"), "created_at": r.get("created_at"),
    } for r in rows]


# --- Privacy: export + delete (P41) -----------------------------------------
@router.get("/export")
async def export_data(claims: dict = Depends(current_user)):
    """Download everything K-GPT holds about this account (DPDP/GDPR-style)."""
    return db.export_user_data(claims["user_id"])


@router.delete("/delete-account")
async def delete_account(claims: dict = Depends(current_user)):
    """Irreversibly delete the account and all associated data (cascade)."""
    user = db.get_user(claims["user_id"])
    if user and user.get("role") == "admin":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Admin accounts can't be self-deleted.")
    db.delete_user_account(claims["user_id"])
    return {"ok": True, "deleted": True}
