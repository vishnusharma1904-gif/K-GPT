"""Background Worker Process (Prompt Pulse).

Runs completely decoupled from the FastAPI request path.
Consumes tasks from RabbitMQ and runs heavy processing pipelines:
  - Document OCR/parsing -> Chunking -> Embedding -> Qdrant
  - Memory extraction and aging
  - Analytics processing
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from datetime import datetime

from app.core.config import get_settings
from app.db import postgres_client, qdrant_client, queue_client
from app.db import supabase_client as db
from app.services import embeddings, extract, knowledge_graph, memory_extractor, moderation

settings = get_settings()
MAX_CHUNKS = 500

_SHUTDOWN_EVENT = asyncio.Event()

def _signal_handler(sig, frame):
    print(f"\n[worker] Received exit signal {sig}, shutting down gracefully...")
    _SHUTDOWN_EVENT.set()

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def _store_worker_chunks(
    *,
    document_id: str,
    user_id: str,
    filename: str | None,
    chunks: list[str],
    project_id: str | None,
    shared: bool,
    scope: dict | None,
) -> int:
    vectors = embeddings.embed_many(chunks)

    if settings.qdrant_host:
        # Re-uploading the same filename must REPLACE its previous chunks, not
        # stack on top of them — otherwise stale/partial text from an earlier
        # (possibly pre-fix, lower-quality OCR) attempt keeps polluting context
        # and citations for this filename forever.
        qdrant_client.delete_chunks_by_source(user_id, filename or "", shared=shared)
        chunk_dicts = [
            {
                "index": i,
                "content": chunk_text,
                "embedding": vectors[i],
                "source": filename,
                "metadata": {"length": len(chunk_text)},
            }
            for i, chunk_text in enumerate(chunks)
        ]
        return qdrant_client.upsert_chunks(
            document_id=document_id,
            chunks=chunk_dicts,
            user_id=user_id,
            institution_id="ksrmce",
            project_id=project_id,
            shared=shared,
            scope=scope,
        )

    stored = 0
    for i, chunk_text in enumerate(chunks):
        if shared:
            db.insert_shared_memory(chunk_text, vectors[i], filename, user_id, scope=scope)
        else:
            db.insert_memory_scoped(
                user_id,
                chunk_text,
                vectors[i],
                kind="document",
                source=filename,
                project_id=project_id,
            )
        stored += 1
    return stored


async def process_document(data: dict) -> None:
    """The complete RAG ingestion pipeline."""
    document_id = data.get("document_id")
    user_id = data.get("user_id")
    filename = data.get("filename")
    s3_key = data.get("s3_key")
    
    if not document_id or not user_id:
        print("[worker] Missing document_id or user_id in task data")
        return

    print(f"[worker] Processing document {document_id} ({filename})")
    
    try:
        # Mark as processing
        db.update_document(document_id, {"status": "processing"})
        doc = db.get_document(document_id)
        metadata = (doc or {}).get("metadata") or {}
        shared = bool(metadata.get("shared"))
        project_id = metadata.get("project_id")
        scope = metadata.get("scope")

        # Resolve the spooled source file. The API stores a local path in s3_key
        # for now so uploads can return immediately while OCR/embedding happen in
        # the worker.
        file_path = s3_key if s3_key and os.path.exists(s3_key) else None
        if not file_path and doc:
            stored_path = doc.get("s3_key")
            if stored_path and os.path.exists(stored_path):
                file_path = stored_path
        if not file_path and filename and os.path.exists(filename):
            file_path = filename
        if not file_path and filename and os.path.exists(f"/tmp/{filename}"):
            file_path = f"/tmp/{filename}"
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(
                f"Source file not available for document {document_id} "
                f"(filename={filename!r}, s3_key={s3_key!r})."
            )

        with open(file_path, "rb") as f:
            raw = f.read()

        text = extract.extract_text(filename or os.path.basename(file_path), raw)
        text = moderation.sanitize_untrusted(text, max_chars=200_000)
        if not text.strip():
            raise ValueError("Extracted text is empty.")

        chunks = extract.chunk(text)[:MAX_CHUNKS]
        print(f"[worker] Document split into {len(chunks)} chunks.")
        if not chunks:
            raise ValueError("No readable text found after OCR/extraction.")

        stored_count = _store_worker_chunks(
            document_id=document_id,
            user_id=user_id,
            filename=filename,
            chunks=chunks,
            project_id=project_id,
            shared=shared,
            scope=scope,
        )

        # Mark as ready
        db.update_document(document_id, {"status": "ready", "chunk_count": stored_count})
        print(f"[worker] Successfully processed {document_id}. Stored {stored_count} chunks.")
        try:
            os.remove(file_path)
        except Exception:
            pass

    except Exception as e:
        print(f"[worker] Failed to process document {document_id}: {e}")
        doc = db.get_document(document_id) or {}
        metadata = dict((doc.get("metadata") or {}))
        metadata["error"] = str(e)
        db.update_document(document_id, {"status": "failed", "metadata": metadata})


async def process_memory_extraction(data: dict) -> None:
    user_id = data.get("user_id")
    message = data.get("message")
    session_id = data.get("session_id")
    if user_id and message:
        await memory_extractor.extract_and_store(user_id, message, session_id)


async def process_graph_update(data: dict) -> None:
    entity_type = data.get("entity_type")
    entity_id = data.get("entity_id")
    payload = data.get("data", {})
    
    # E.g. analyzing chat history for mastery
    if entity_type == "mastery_analysis":
        chat_history = payload.get("chat_history")
        user_id = entity_id
        if user_id and chat_history:
            await knowledge_graph.extract_mastery(user_id, chat_history)


async def consume_queues() -> None:
    """Poll RabbitMQ queues and process messages."""
    conn, ch = queue_client._get_channel()
    if not ch:
        print("[worker] Could not connect to RabbitMQ. Retrying in 5s...")
        await asyncio.sleep(5)
        return

    try:
        # We use a non-blocking poll here so we can respect _SHUTDOWN_EVENT
        while not _SHUTDOWN_EVENT.is_set():
            processed_any = False
            
            # 1. Document Processing Queue
            method_frame, header_frame, body = ch.basic_get(queue=queue_client.Q_DOCUMENTS_PROCESS)
            if method_frame:
                try:
                    data = json.loads(body)
                    await process_document(data)
                    ch.basic_ack(delivery_tag=method_frame.delivery_tag)
                except Exception as e:
                    print(f"[worker] Error processing document message: {e}")
                    ch.basic_reject(delivery_tag=method_frame.delivery_tag, requeue=False)
                processed_any = True

            # 2. Memory Extraction Queue
            method_frame, header_frame, body = ch.basic_get(queue=queue_client.Q_MEMORY_EXTRACT)
            if method_frame:
                try:
                    data = json.loads(body)
                    await process_memory_extraction(data)
                    ch.basic_ack(delivery_tag=method_frame.delivery_tag)
                except Exception as e:
                    print(f"[worker] Error processing memory message: {e}")
                    ch.basic_reject(delivery_tag=method_frame.delivery_tag, requeue=False)
                processed_any = True

            # 3. Knowledge Graph Update Queue
            method_frame, header_frame, body = ch.basic_get(queue=queue_client.Q_GRAPH_UPDATE)
            if method_frame:
                try:
                    data = json.loads(body)
                    await process_graph_update(data)
                    ch.basic_ack(delivery_tag=method_frame.delivery_tag)
                except Exception as e:
                    print(f"[worker] Error processing graph message: {e}")
                    ch.basic_reject(delivery_tag=method_frame.delivery_tag, requeue=False)
                processed_any = True

            if not processed_any:
                await asyncio.sleep(1)  # No messages, wait before polling again
    finally:
        try:
            conn.close()
        except Exception:
            pass


async def main() -> None:
    print("[worker] Starting Prompt Pulse Background Worker...")
    
    # Warm up models
    embeddings.warm()
    
    # Initialize DB pools
    await postgres_client.init_pool()
    qdrant_client.ensure_collections()
    queue_client.ensure_queues()

    print("[worker] Ready. Listening for tasks...")
    
    # Run consumer loop
    while not _SHUTDOWN_EVENT.is_set():
        await consume_queues()
        if not _SHUTDOWN_EVENT.is_set():
             await asyncio.sleep(2)
             
    print("[worker] Shutting down...")
    await postgres_client.close_pool()
    print("[worker] Exited safely.")


if __name__ == "__main__":
    # Workaround for Windows asyncio loop policy if tested locally
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
