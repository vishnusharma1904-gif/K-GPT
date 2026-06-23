"""File upload → per-user RAG memory (P29).

Extracts text from PDF/DOCX/PPTX/XLSX/CSV/TXT, chunks it, embeds each chunk
locally (MiniLM), and stores it in the user's pgvector memory as kind='document'.
The existing chat RAG path then grounds answers in the uploaded material.
Optionally scope the document to a Project so it's shared across that Project's
chats (P30).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.security import current_user
from app.db import supabase_client as db
from app.services import embeddings, extract, moderation

router = APIRouter(prefix="/api/upload", tags=["upload"])

MAX_CHUNKS = 120  # cap ingestion per file to protect the embedding budget


@router.post("")
async def upload(
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    claims: dict = Depends(current_user),
):
    data = await file.read()
    try:
        text = extract.extract_text(file.filename or "file", data)
    except extract.ExtractError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    # Treat document content as untrusted: strip obvious injection lines (P43).
    text = moderation.sanitize_untrusted(text, max_chars=200_000)
    chunks = extract.chunk(text)
    if not chunks:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "No readable text found in that file.")
    chunks = chunks[:MAX_CHUNKS]

    if project_id and not db.get_project(project_id, claims["user_id"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found.")

    import traceback
    stored = 0
    last_err = None
    for c in chunks:
        try:
            db.insert_memory_scoped(
                claims["user_id"], c, embeddings.embed(c),
                kind="document", source=file.filename, project_id=project_id,
            )
            stored += 1
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            continue
            
    if stored == 0 and chunks:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Memory insertion failed: {last_err or 'Unknown error'}")

    # Auto-routing mapping based on extension
    ext = ("." + (file.filename or "").rsplit(".", 1)[-1].lower()) if "." in (file.filename or "") else ""
    suggested = "long_context"  # default for docs
    if ext in {".py", ".js", ".ts", ".html", ".css", ".java", ".c", ".cpp", ".sql"}:
        suggested = "coding"
    elif ext in {".csv", ".xlsx", ".xls"}:
        suggested = "reasoning"

    return {
        "ok": True,
        "filename": file.filename,
        "chunks_stored": stored,
        "project_id": project_id,
        "truncated": len(chunks) >= MAX_CHUNKS,
        "suggested_category": suggested,
    }
