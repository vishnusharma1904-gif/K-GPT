"""Account self-service — profile, %-only usage, weekly-bonus, preferences,
privacy (export / delete), billing history (P12 / P25 / P31 / P40 / P41 / P17)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import current_user
from app.db import supabase_client as db
from app.schemas import PrefsReq
from app.services import entitlements, prompting

router = APIRouter(prefix="/api/account", tags=["account"])

_VALID_STYLES = set(prompting.STYLES.keys())


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
    return {
        "response_style": u.get("response_style", "balanced"),
        "custom_instructions": u.get("custom_instructions"),
        "exam_mode": bool(u.get("exam_mode")),
        "memory_enabled": bool(u.get("memory_enabled", True)),
        "web_search_enabled": bool(u.get("web_search_enabled")),
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
    if patch:
        db.update_user(claims["user_id"], patch)
    return {"ok": True, **patch}


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
