"""Prompt library & slash commands (P24).

Per-user saved prompts plus shared starter templates (seeded in migration 004).
The composer's `/` menu lists these; selecting one inserts ``body`` (with simple
``{placeholder}`` slots the student fills in).
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import current_user
from app.db import supabase_client as db

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


class PromptReq(BaseModel):
    slug: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=4000)


def _norm_slug(slug: str) -> str:
    s = slug.strip().lower()
    if not s.startswith("/"):
        s = "/" + s
    s = re.sub(r"[^a-z0-9/_-]", "", s)
    return s[:40] or "/prompt"


@router.get("")
async def list_prompts(claims: dict = Depends(current_user)):
    return db.list_prompts(claims["user_id"])


@router.post("")
async def create_prompt(body: PromptReq, claims: dict = Depends(current_user)):
    return db.create_prompt(claims["user_id"], _norm_slug(body.slug),
                            body.title.strip(), body.body)


@router.delete("/{prompt_id}")
async def delete_prompt(prompt_id: str, claims: dict = Depends(current_user)):
    db.delete_prompt(prompt_id, claims["user_id"])
    return {"ok": True}
