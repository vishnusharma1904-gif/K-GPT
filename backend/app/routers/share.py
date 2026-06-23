"""Shareable read-only conversation links (P27).

A share is a public, unguessable token mapping to a session. The public read
endpoint returns messages only (no usage, no account data) and respects revoke.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import current_user
from app.db import supabase_client as db

router = APIRouter(prefix="/api/share", tags=["share"])


@router.post("/{session_id}")
async def create_share(session_id: str, claims: dict = Depends(current_user)):
    if not db.get_session(session_id, claims["user_id"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    token = secrets.token_urlsafe(12)
    db.create_share(token, session_id, claims["user_id"])
    return {"token": token}


@router.get("/mine")
async def my_shares(claims: dict = Depends(current_user)):
    return db.list_shares(claims["user_id"])


@router.delete("/{token}")
async def revoke(token: str, claims: dict = Depends(current_user)):
    db.revoke_share(token, claims["user_id"])
    return {"ok": True}


# --- Public (no auth) -------------------------------------------------------
@router.get("/public/{token}")
async def public_view(token: str):
    share = db.get_share(token)
    if not share:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This shared chat is unavailable.")
    session = db.get_session_public(share["session_id"])
    msgs = db.get_messages_public(share["session_id"])
    return {"session": session, "messages": msgs}
