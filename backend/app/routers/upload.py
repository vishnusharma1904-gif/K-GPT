"""Fast document upload and background knowledge-base ingestion."""
from __future__ import annotations

import asyncio
import os
import tempfile
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status, BackgroundTasks

from app.core.config import get_settings
from app.core.security import current_user
from app.db import qdrant_client, queue_client
from app.db import supabase_client as db
from app.services import embeddings, extract, figures, moderation

settings = get_settings()
router = APIRouter(prefix="/api/upload", tags=["upload"])

MAX_CHUNKS = 500
SPOOL_CHUNK_BYTES = 1024 * 1024
INLINE_UPLOAD_MAX_BYTES = 2 * 1024 * 1024


def _suggested_category(filename: str | None) -> str:
    ext = ("." + (filename or "").rsplit(".", 1)[-1].lower()) if "." in (filename or "") else ""
    if ext in {".py", ".js", ".ts", ".html", ".css", ".java", ".c", ".cpp", ".sql"}:
        return "coding"
    if ext in {".csv", ".xlsx", ".xls"}:
        return "reasoning"
    return "long_context"


def _validate_supported_type(filename: str | None) -> None:
    ext = ("." + (filename or "").rsplit(".", 1)[-1].lower()) if "." in (filename or "") else ""
    if ext not in extract.SUPPORTED:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported file type '{ext or '?'}'. Upload PDF, DOCX, PPTX, XLSX, CSV, TXT, MD, or an image.",
        )


def _ext(filename: str | None) -> str:
    return ("." + (filename or "").rsplit(".", 1)[-1].lower()) if "." in (filename or "") else ""


def _should_process_inline(filename: str | None, file_size_bytes: int, shared: bool,
                            needs_ocr: bool = False) -> bool:
    """Keep common/small docs fast and immediately usable in chat.

    Background OCR/indexing is reserved for uploads that are more likely to be
    slow or operationally fragile. A 20-30 page handwritten/scanned PDF easily
    fits under the small-file size threshold below (JPEG-compressed scans
    compress well), but vision OCR can take tens of seconds PER PAGE — so file
    size alone is not a safe signal. Anything that needs vision OCR always goes
    to the background path, however small it is.
    """
    ext = _ext(filename)
    if shared:
        return False
    if ext in extract.IMAGE_EXTS:
        return False
    if needs_ocr:
        return False
    if ext in {".txt", ".md", ".csv"}:
        return True
    return file_size_bytes <= INLINE_UPLOAD_MAX_BYTES


def _store_chunks(
    user_id: str,
    chunks: list[str],
    filename: str | None,
    project_id: str | None,
    shared: bool = False,
    scope: dict | None = None,
    document_id: str | None = None,
) -> tuple[int, str | None]:
    """Persist chunks to Qdrant when configured, else fall back to pgvector."""
    vectors = embeddings.embed_many(chunks)

    if settings.qdrant_host:
        try:
            # Re-uploading the same filename must REPLACE its previous chunks,
            # not stack on top of them (see qdrant_client.delete_chunks_by_source).
            qdrant_client.delete_chunks_by_source(user_id, filename or "", shared=shared)
            chunk_dicts = [
                {
                    "index": i,
                    "content": c,
                    "embedding": vectors[i],
                    "source": filename,
                    "metadata": {"length": len(c)},
                }
                for i, c in enumerate(chunks)
            ]
            stored = qdrant_client.upsert_chunks(
                document_id=document_id or str(uuid.uuid4()),
                chunks=chunk_dicts,
                user_id=user_id,
                project_id=project_id,
                shared=shared,
                scope=scope,
            )
            return stored, None
        except Exception as e:  # noqa: BLE001
            return 0, str(e)

    stored, last_err = 0, None
    for i, c in enumerate(chunks):
        try:
            if shared:
                db.insert_shared_memory(c, vectors[i], filename, user_id, scope=scope)
            else:
                db.insert_memory_scoped(
                    user_id,
                    c,
                    vectors[i],
                    kind="document",
                    source=filename,
                    project_id=project_id,
                )
            stored += 1
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            continue
    return stored, last_err


def _async_ingest_available() -> bool:
    return bool(
        settings.async_document_uploads_enabled
        and settings.supabase_url
        and settings.supabase_service_key
        and queue_client.available()
    )


def _spool_file(document_id: str, filename: str | None, data: bytes) -> tuple[str, str]:
    safe_name = os.path.basename(filename or "upload.bin")
    spool_dir = os.path.join(tempfile.gettempdir(), "kgpt_uploads")
    os.makedirs(spool_dir, exist_ok=True)
    local_path = os.path.join(spool_dir, f"{document_id}__{safe_name}")
    with open(local_path, "wb") as f:
        f.write(data)
    return safe_name, local_path


async def _spool_upload_stream(
    file: UploadFile,
    *,
    document_id: str,
    max_bytes: int | None,
) -> tuple[str, str, int]:
    safe_name = os.path.basename(file.filename or "upload.bin")
    spool_dir = os.path.join(tempfile.gettempdir(), "kgpt_uploads")
    os.makedirs(spool_dir, exist_ok=True)
    local_path = os.path.join(spool_dir, f"{document_id}__{safe_name}")
    total = 0
    try:
        with open(local_path, "wb") as out:
            while True:
                chunk = await file.read(SPOOL_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if max_bytes is not None and total > max_bytes:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        f"File too large - max {settings.max_upload_mb} MB.",
                    )
                out.write(chunk)
    except Exception:
        try:
            os.remove(local_path)
        except Exception:
            pass
        raise
    return safe_name, local_path, total


def _queue_upload_sync(
    *,
    user_id: str,
    filename: str,
    content_type: str | None,
    local_path: str,
    file_size_bytes: int,
    project_id: str | None,
    shared: bool,
    scope: dict | None,
) -> dict:
    """Persist the raw file and enqueue ingestion when async infra is ready.

    Plain sync function — both `db.create_document` (Supabase REST call) and
    `queue_client.publish_document_process` (blocking RabbitMQ connection) are
    real network I/O, so this must run in a thread (see the async wrapper
    below), never directly on the event loop.
    """
    document_id = os.path.basename(local_path).split("__", 1)[0]

    metadata = {"project_id": project_id, "shared": shared, "scope": scope}
    try:
        db.create_document({
            "id": document_id,
            "user_id": user_id,
            "filename": filename,
            "file_type": content_type or "application/octet-stream",
            "file_size_bytes": file_size_bytes,
            "s3_key": local_path,
            "metadata": metadata,
        })
        queued = queue_client.publish_document_process(
            document_id=document_id,
            user_id=user_id,
            filename=filename,
            s3_key=local_path,
        )
        if not queued:
            raise RuntimeError("queue publish failed")
    except Exception as e:
        try:
            db.delete_document(document_id)
        except Exception:
            pass
        try:
            os.remove(local_path)
        except Exception:
            pass
        # Previously returned None here, which FastAPI serialised as a plain
        # `null` 200 OK response — the frontend only treats non-2xx as an
        # error, so a failed queue publish (e.g. RabbitMQ hiccup) looked like
        # a silent no-op: no error shown, attachment state never updates, and
        # the upload just appears to hang forever ("still not uploading").
        # Raising here turns it into a real 500 the frontend surfaces.
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Could not queue document for processing: {e}",
        )

    return {
        "ok": True,
        "queued": True,
        "document_id": document_id,
        "status": "pending",
        "filename": filename,
        "chunks_stored": 0,
        "project_id": project_id,
        "shared": shared,
        "scope": scope,
        "truncated": False,
        "suggested_category": _suggested_category(filename),
        "figures": [],
    }


async def _queue_upload(**kwargs) -> dict:
    return await asyncio.to_thread(_queue_upload_sync, **kwargs)


def _extract_and_store_now(
    *,
    user_id: str,
    filename: str | None,
    data: bytes,
    project_id: str | None,
    shared: bool,
    scope: dict | None,
) -> dict:
    text = extract.extract_text(filename or "file", data)
    text = moderation.sanitize_untrusted(text, max_chars=200_000)
    chunks = extract.chunk(text)
    if not chunks:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No readable text found in that file.")
    chunks = chunks[:MAX_CHUNKS]

    stored, last_err = _store_chunks(
        user_id,
        chunks,
        filename,
        project_id,
        shared=shared,
        scope=scope,
    )
    if stored == 0 and chunks:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Memory insertion failed: {last_err or 'Unknown error'}",
        )

    gallery: list[dict] = []
    try:
        figs = extract.extract_figures(filename or "file", data)
        if figs:
            gallery = figures.save_figures(uuid.uuid4().hex, figs)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] figure gallery skipped: {e}")

    return _sync_upload_response(
        filename=filename,
        stored=stored,
        project_id=project_id,
        shared=shared,
        scope=scope,
        truncated=len(chunks) >= MAX_CHUNKS,
        gallery=gallery,
    )


async def _background_extract_and_store(
    document_id: str,
    user_id: str,
    filename: str | None,
    data: bytes,
    project_id: str | None,
    shared: bool,
    scope: dict | None,
) -> None:
    """Run extraction in a thread pool and update the document status."""
    try:
        res = await asyncio.to_thread(
            _extract_and_store_now,
            user_id=user_id,
            filename=filename,
            data=data,
            project_id=project_id,
            shared=shared,
            scope=scope,
        )
        db.update_document(document_id, {
            "status": "ready",
            "chunk_count": res.get("chunks_stored", 0),
        })
    except Exception as e:
        meta = {
            "project_id": project_id,
            "shared": shared,
            "scope": scope,
            "error": str(e),
        }
        db.update_document(document_id, {
            "status": "failed",
            "metadata": meta,
        })



def _sync_upload_response(
    *,
    filename: str | None,
    stored: int,
    project_id: str | None,
    shared: bool,
    scope: dict | None,
    truncated: bool,
    gallery: list[dict],
) -> dict:
    return {
        "ok": True,
        "queued": False,
        "document_id": None,
        "status": "ready",
        "filename": filename,
        "chunks_stored": stored,
        "project_id": project_id,
        "shared": shared,
        "scope": scope,
        "truncated": truncated,
        "suggested_category": _suggested_category(filename),
        "figures": gallery,
    }


@router.post("")
async def upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    shared: bool = Form(False),
    scope_branch: str | None = Form(None),
    scope_year: int | None = Form(None),
    scope_section: str | None = Form(None),
    claims: dict = Depends(current_user),
):
    is_admin = claims.get("role") == "admin"

    if shared:
        role = claims.get("role")
        if role == "faculty":
            u = db.get_user(claims["user_id"]) or {}
            if not u.get("faculty_approved"):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    "Your faculty account isn't approved for shared uploads yet.",
                )
        elif role != "admin":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Only an admin or approved faculty can add to the shared knowledge base.",
            )

    _validate_supported_type(file.filename)

    if project_id and not db.get_project(project_id, claims["user_id"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found.")

    scope = None
    if shared:
        scope = {"branch": scope_branch, "year": scope_year, "section": scope_section}

    # _async_ingest_available() can open a blocking RabbitMQ connection (now
    # cached, but a cache miss still blocks) — never run that directly on the
    # event loop, or every concurrent request stalls until it resolves.
    if await asyncio.to_thread(_async_ingest_available):
        document_id = str(uuid.uuid4())
        max_bytes = None if is_admin else settings.max_upload_mb * 1024 * 1024
        safe_name, local_path, total = await _spool_upload_stream(
            file,
            document_id=document_id,
            max_bytes=max_bytes,
        )
        needs_ocr = False
        if _ext(safe_name) == ".pdf":
            needs_ocr = await asyncio.to_thread(extract.pdf_needs_ocr, path=local_path)
        if _should_process_inline(safe_name, total, shared, needs_ocr=needs_ocr):
            try:
                with open(local_path, "rb") as f:
                    data = f.read()
                # Run off the event loop: extraction (especially vision OCR) can
                # take tens of seconds and must never block other requests.
                return await asyncio.to_thread(
                    _extract_and_store_now,
                    user_id=claims["user_id"],
                    filename=safe_name,
                    data=data,
                    project_id=project_id,
                    shared=shared,
                    scope=scope,
                )
            finally:
                try:
                    os.remove(local_path)
                except Exception:
                    pass

        return await _queue_upload(
            user_id=claims["user_id"],
            filename=safe_name,
            content_type=file.content_type,
            local_path=local_path,
            file_size_bytes=total,
            project_id=project_id,
            shared=shared,
            scope=scope,
        )

    if is_admin:
        data = await file.read()
    else:
        max_bytes = settings.max_upload_mb * 1024 * 1024
        data = await file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"File too large - max {settings.max_upload_mb} MB.",
            )

    needs_ocr = False
    if _ext(file.filename) == ".pdf":
        needs_ocr = await asyncio.to_thread(extract.pdf_needs_ocr, data)

    if _should_process_inline(file.filename, len(data), shared, needs_ocr=needs_ocr):
        try:
            # Run off the event loop: extraction (especially vision OCR) can take
            # tens of seconds and must never block other requests.
            return await asyncio.to_thread(
                _extract_and_store_now,
                user_id=claims["user_id"],
                filename=file.filename,
                data=data,
                project_id=project_id,
                shared=shared,
                scope=scope,
            )
        except extract.ExtractError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    else:
        # Fallback to FastAPI background task when RabbitMQ is unavailable
        document_id = str(uuid.uuid4())
        metadata = {}
        if project_id:
            metadata["project_id"] = project_id
        if shared:
            metadata["shared"] = True
            metadata["scope"] = scope
            
        db.create_document({
            "id": document_id,
            "user_id": claims["user_id"],
            "filename": file.filename,
            "file_type": file.content_type or "application/octet-stream",
            "file_size_bytes": len(data),
            "s3_key": None,
            "metadata": metadata,
            "status": "pending",
        })

        background_tasks.add_task(
            _background_extract_and_store,
            document_id=document_id,
            user_id=claims["user_id"],
            filename=file.filename,
            data=data,
            project_id=project_id,
            shared=shared,
            scope=scope,
        )

        return {
            "ok": True,
            "queued": True,
            "document_id": document_id,
            "status": "pending",
            "filename": file.filename,
            "chunks_stored": 0,
            "project_id": project_id,
            "shared": shared,
            "scope": scope,
            "truncated": False,
            "suggested_category": _suggested_category(file.filename),
            "figures": [],
        }


@router.get("/{document_id}")
async def upload_status(document_id: str, claims: dict = Depends(current_user)):
    if not settings.supabase_url or not settings.supabase_service_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Background upload status is unavailable.")

    row = db.get_document(document_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    if row["user_id"] != claims["user_id"] and claims.get("role") != "admin":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")

    metadata = row.get("metadata") or {}
    return {
        "ok": True,
        "document_id": row["id"],
        "filename": row["filename"],
        "status": row["status"],
        "chunks_stored": row.get("chunk_count") or 0,
        "project_id": metadata.get("project_id"),
        "shared": bool(metadata.get("shared")),
        "scope": metadata.get("scope"),
        "error": metadata.get("error"),
        "suggested_category": _suggested_category(row["filename"]),
    }
