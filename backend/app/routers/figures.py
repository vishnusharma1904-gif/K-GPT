"""Read-only serving of extracted document figures (backlog §6.1).

Figures are public-by-obscurity: the URL contains an unguessable document id, so
a shared-KB figure is viewable by any logged-in user (which is the intent), while
a private upload's figures aren't enumerable. Path components are sanitised in
``figures.figure_path`` so the route can't be used for directory traversal.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.services import figures

router = APIRouter(prefix="/api/figures", tags=["figures"])


@router.get("/{doc_id}/{name}")
async def get_figure(doc_id: str, name: str):
    path = figures.figure_path(doc_id, name)
    if not path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Figure not found.")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})
