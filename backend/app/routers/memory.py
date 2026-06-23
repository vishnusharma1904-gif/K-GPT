"""Per-user memory — transparent + editable (add/list/delete), project-scoped (P31/P30)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import current_user
from app.db import supabase_client as db
from app.schemas import MemoryReq
from app.services import embeddings

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.post("")
async def add(req: MemoryReq, claims: dict = Depends(current_user)):
    db.insert_memory_scoped(claims["user_id"], req.content, embeddings.embed(req.content),
                            kind=req.kind, source=req.source, project_id=req.project_id)
    return {"ok": True}


@router.get("")
async def list_notes(project_id: str | None = None, claims: dict = Depends(current_user)):
    return db.list_memory(claims["user_id"], project_id)


@router.delete("/{chunk_id}")
async def delete(chunk_id: str, claims: dict = Depends(current_user)):
    db.delete_memory(chunk_id, claims["user_id"])
    return {"ok": True}
