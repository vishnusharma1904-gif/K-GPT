"""File upload → per-user RAG memory (P29).

Extracts text from PDF/DOCX/PPTX/XLSX/CSV/TXT, chunks it, embeds each chunk
(nomic-embed-text-v1.5 via Fireworks), and stores it in the user's pgvector
memory as kind='document'. The existing chat RAG path then grounds answers in
the uploaded material.
Optionally scope the document to a Project so it's shared across that Project's
chats (P30).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.config import get_settings
from app.core.security import current_user
from app.db import qdrant_client
from app.db import supabase_client as db
from app.services import embeddings, extract, figures, moderation

settings = get_settings()
router = APIRouter(prefix="/api/upload", tags=["upload"])

MAX_CHUNKS = 120  # cap ingestion per file to protect the embedding budget


def _store_chunks(user_id: str, chunks: list[str], filename: str | None,
                  project_id: str | None, shared: bool = False) -> tuple[int, str | None]:
    """Persist chunks to Qdrant when configured (so the new RAG retrieval path
    finds them), else fall back to the legacy pgvector memory store.

    When `shared=True` the chunks go into the institution-wide knowledge base
    (admin-verified, retrievable by every user). Returns (stored_count, last_error)."""
    # Embed every chunk up front in batched calls (≈2 requests for a 120-chunk
    # file instead of 120 sequential ones).
    vectors = embeddings.embed_many(chunks)

    if settings.qdrant_host:
        try:
            document_id = str(uuid.uuid4())
            chunk_dicts = [
                {"index": i, "content": c, "embedding": vectors[i],
                 "source": filename, "metadata": {"length": len(c)}}
                for i, c in enumerate(chunks)
            ]
            stored = qdrant_client.upsert_chunks(
                document_id=document_id, chunks=chunk_dicts,
                user_id=user_id, project_id=project_id, shared=shared,
            )
            return stored, None
        except Exception as e:  # noqa: BLE001
            return 0, str(e)

    # --- legacy pgvector fallback ---
    stored, last_err = 0, None
    for i, c in enumerate(chunks):
        try:
            if shared:
                db.insert_shared_memory(c, vectors[i], filename, user_id)
            else:
                db.insert_memory_scoped(
                    user_id, c, vectors[i],
                    kind="document", source=filename, project_id=project_id,
                )
            stored += 1
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            continue
    return stored, last_err


@router.post("")
async def upload(
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    shared: bool = Form(False),
    claims: dict = Depends(current_user),
):
    # Storing into the institution-wide knowledge base is an admin-only action
    # (the "verified by admin" step). Regular uploads stay private to the user.
    if shared and claims.get("role") != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Only an admin can add to the shared knowledge base.")

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

    stored, last_err = _store_chunks(claims["user_id"], chunks, file.filename,
                                     project_id, shared=shared)

    if stored == 0 and chunks:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Memory insertion failed: {last_err or 'Unknown error'}")

    # Figure gallery (§6.1): pull embedded images so the UI can show them under
    # answers grounded in this document. Best-effort — never fails the upload.
    gallery: list[dict] = []
    try:
        figs = extract.extract_figures(file.filename or "file", data)
        if figs:
            gallery = figures.save_figures(uuid.uuid4().hex, figs)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] figure gallery skipped: {e}")

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
        "shared": shared,
        "truncated": len(chunks) >= MAX_CHUNKS,
        "suggested_category": suggested,
        "figures": gallery,
    }
