"""Projects — group chats + shared per-project knowledge & instructions (P20/P30)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import current_user
from app.db import supabase_client as db
from app.schemas import ProjectPatch, ProjectReq

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
async def list_projects(claims: dict = Depends(current_user)):
    return db.list_projects(claims["user_id"])


@router.post("")
async def create_project(req: ProjectReq, claims: dict = Depends(current_user)):
    return db.create_project(claims["user_id"], req.name, req.instructions, req.color)


@router.get("/{project_id}")
async def get_project(project_id: str, claims: dict = Depends(current_user)):
    p = db.get_project(project_id, claims["user_id"])
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    p["sessions"] = db.list_sessions_in_project(claims["user_id"], project_id)
    p["knowledge"] = db.list_memory(claims["user_id"], project_id)
    return p


@router.patch("/{project_id}")
async def update_project(project_id: str, body: ProjectPatch, claims: dict = Depends(current_user)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = db.update_project(project_id, claims["user_id"], patch)
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return updated


@router.delete("/{project_id}")
async def delete_project(project_id: str, claims: dict = Depends(current_user)):
    db.delete_project(project_id, claims["user_id"])
    return {"ok": True}
