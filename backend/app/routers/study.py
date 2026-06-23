"""Study-aid endpoints (P38) — flashcards / quiz / summary, saved per user."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.security import current_user
from app.db import supabase_client as db
from app.services import entitlements, study

settings = get_settings()
router = APIRouter(prefix="/api/study", tags=["study"])


class GenerateReq(BaseModel):
    kind: str = Field(pattern="^(flashcards|quiz|summary)$")
    session_id: str | None = None
    text: str | None = Field(default=None, max_length=12000)
    title: str | None = Field(default=None, max_length=120)


def _material_from_session(session_id: str, user_id: str) -> str:
    msgs = db.get_messages(session_id, user_id, limit=40)
    parts = [f"{m['role']}: {m['content']}" for m in msgs
             if m.get("role") in ("user", "assistant")]
    return "\n\n".join(parts)


@router.post("/generate")
async def generate(body: GenerateReq, claims: dict = Depends(current_user)):
    user = db.get_user(claims["user_id"])
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    material = body.text or ""
    if body.session_id:
        if not db.get_session(body.session_id, user["id"]):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
        material = material or _material_from_session(body.session_id, user["id"])
    if not material.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Provide text or a session with messages to generate from.")

    is_admin = user.get("role") == "admin"
    allow_premium = settings.premium_models_for_students or is_admin
    out = await study.generate(body.kind, material, allow_premium=allow_premium)

    # Meter the generation like any other model call.
    if out.get("model"):
        entitlements.record_usage(user["id"], out["model"],
                                  out.get("prompt_tokens", 0),
                                  out.get("completion_tokens", 0),
                                  out.get("cost_usd", 0.0))

    saved = db.create_study_aid(user["id"], out["kind"],
                                body.title or out["kind"].title(),
                                out["payload"], body.session_id)
    return {"id": saved["id"], "kind": out["kind"], "payload": out["payload"],
            "model": out.get("model")}


@router.get("")
async def my_aids(claims: dict = Depends(current_user)):
    return db.list_study_aids(claims["user_id"])


@router.delete("/{aid_id}")
async def delete_aid(aid_id: str, claims: dict = Depends(current_user)):
    db.delete_study_aid(aid_id, claims["user_id"])
    return {"ok": True}
